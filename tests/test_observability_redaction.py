"""Tests for sensitive data redaction module."""

from minos_core.observability.redaction import redact_sensitive_data


def test_redacts_api_keys():
    """API keys should be redacted in event dict."""
    event_dict = {
        "message": "API call",
        "api_key": "sk-1234567890",
        "user_token": "secret-token-abc"
    }

    result = redact_sensitive_data(event_dict)

    assert result["api_key"] == "***REDACTED***"
    assert result["user_token"] == "***REDACTED***"
    assert result["message"] == "API call"  # Non-sensitive unchanged


def test_redacts_passwords():
    """Password fields should be redacted."""
    event_dict = {
        "username": "alice",
        "password": "super-secret-123",
        "pwd": "another-secret"
    }

    result = redact_sensitive_data(event_dict)

    assert result["username"] == "alice"
    assert result["password"] == "***REDACTED***"
    assert result["pwd"] == "***REDACTED***"


def test_redacts_nested_dicts():
    """Nested dictionaries should be recursively redacted."""
    event_dict = {
        "request": {
            "headers": {
                "authorization": "Bearer secret-token",
                "content-type": "application/json"
            }
        }
    }

    result = redact_sensitive_data(event_dict)

    assert result["request"]["headers"]["authorization"] == "***REDACTED***"
    assert result["request"]["headers"]["content-type"] == "application/json"


def test_redacts_patterns_in_strings():
    """Sensitive patterns in string values should be redacted."""
    event_dict = {
        "command": "curl -H 'Authorization: Bearer sk-abc123def456ghi789' https://api.example.com",
        "url": "https://user:password@example.com/path"
    }

    result = redact_sensitive_data(event_dict)

    assert "sk-abc123def456ghi789" not in result["command"]
    assert "***REDACTED-API-KEY***" in result["command"]
    assert "user:password" not in result["url"]
    assert "***:***@" in result["url"]


def test_case_insensitive_key_detection():
    """Key detection should be case-insensitive."""
    event_dict = {
        "API_KEY": "secret1",
        "ApiKey": "secret2",
        "api-key": "secret3",
        "BEARER_TOKEN": "secret4"
    }

    result = redact_sensitive_data(event_dict)

    assert result["API_KEY"] == "***REDACTED***"
    assert result["ApiKey"] == "***REDACTED***"
    assert result["api-key"] == "***REDACTED***"
    assert result["BEARER_TOKEN"] == "***REDACTED***"


def test_preserves_non_sensitive_data():
    """Non-sensitive data should remain unchanged."""
    event_dict = {
        "user_id": 12345,
        "timestamp": "2026-05-28T10:00:00Z",
        "level": "info",
        "message": "User logged in",
        "metadata": {
            "ip": "192.168.1.1",
            "user_agent": "Mozilla/5.0"
        }
    }

    result = redact_sensitive_data(event_dict)

    assert result == event_dict  # Should be unchanged


def test_handles_empty_dict():
    """Empty dictionary should be handled gracefully."""
    event_dict = {}

    result = redact_sensitive_data(event_dict)

    assert result == {}


def test_handles_non_string_values():
    """Non-string values should be preserved."""
    event_dict = {
        "count": 42,
        "enabled": True,
        "items": [1, 2, 3],
        "api_key": "secret"
    }

    result = redact_sensitive_data(event_dict)

    assert result["count"] == 42
    assert result["enabled"] is True
    assert result["items"] == [1, 2, 3]
    assert result["api_key"] == "***REDACTED***"


def test_redacts_credentials():
    """Credential-related fields should be redacted."""
    event_dict = {
        "credentials": "user:pass",
        "secret": "my-secret",
        "auth": "Basic dXNlcjpwYXNz"
    }

    result = redact_sensitive_data(event_dict)

    assert result["credentials"] == "***REDACTED***"
    assert result["secret"] == "***REDACTED***"
    assert result["auth"] == "***REDACTED***"
