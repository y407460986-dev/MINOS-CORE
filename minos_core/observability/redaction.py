"""Sensitive data redaction for observability logs.

This module provides utilities to redact sensitive information from log event
dictionaries before they are written to logs or sent to external systems.
"""

import re
from typing import Any

# Sensitive key patterns (case-insensitive, ignoring underscores/hyphens)
SENSITIVE_KEYS = {
    "api_key", "apikey", "api-key",
    "token", "auth", "authorization", "bearer",
    "password", "passwd", "pwd", "secret",
    "credential", "credentials",
}

# Regex patterns for sensitive data in string values
# Order matters: more specific patterns should come first
SENSITIVE_PATTERNS = [
    # OpenAI-style API keys (sk-...) - must come before Bearer pattern
    # Matches sk- followed by 15+ alphanumeric characters
    (re.compile(r'sk-[a-zA-Z0-9]{15,}'), '***REDACTED-API-KEY***'),
    # Bearer tokens (but not if already redacted by API key pattern)
    (re.compile(r'Bearer\s+(?![\*]+)[a-zA-Z0-9._-]{20,}'), 'Bearer ***REDACTED***'),
    # URLs with credentials (https://user:pass@host)
    (re.compile(r'https?://[^:]+:[^@]+@'), 'https://***:***@'),
]


def redact_sensitive_data(event_dict: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive information from event dictionary.

    This function recursively processes event dictionaries and redacts:
    - Fields with sensitive key names (api_key, password, token, etc.)
    - Sensitive patterns in string values (API keys, tokens, credentials in URLs)
    - Sensitive data in nested lists and tuples

    Args:
        event_dict: The event dictionary to redact

    Returns:
        A new dictionary with sensitive data redacted

    Examples:
        >>> event = {"api_key": "sk-123", "message": "Hello"}
        >>> redact_sensitive_data(event)
        {"api_key": "***REDACTED***", "message": "Hello"}
    """
    result = {}
    for key, value in event_dict.items():
        if _is_sensitive_key(key):
            result[key] = "***REDACTED***"
        elif isinstance(value, str):
            result[key] = _redact_patterns(value)
        elif isinstance(value, dict):
            result[key] = redact_sensitive_data(value)
        elif isinstance(value, (list, tuple)):
            result[key] = type(value)(_redact_value(item) for item in value)
        else:
            result[key] = value
    return result


def _redact_value(value: Any) -> Any:
    """Redact a single value (used for list/tuple items).

    Args:
        value: The value to redact

    Returns:
        The redacted value
    """
    if isinstance(value, str):
        return _redact_patterns(value)
    elif isinstance(value, dict):
        return redact_sensitive_data(value)
    elif isinstance(value, (list, tuple)):
        return type(value)(_redact_value(item) for item in value)
    else:
        return value


def _is_sensitive_key(key: str) -> bool:
    """Check if key name indicates sensitive data.

    Key detection is case-insensitive and ignores underscores and hyphens.

    Args:
        key: The key name to check

    Returns:
        True if the key is considered sensitive
    """
    key_lower = key.lower().replace("_", "").replace("-", "")
    return any(sensitive in key_lower for sensitive in SENSITIVE_KEYS)


def _redact_patterns(text: str) -> str:
    """Redact sensitive patterns in text.

    Args:
        text: The text to redact

    Returns:
        Text with sensitive patterns replaced
    """
    for pattern, replacement in SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text
