"""Bearer-token auth for the local desktop API."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

from fastapi import Header, Query

from minos_desktop.security.token_manager import TokenManager

from .schemas import APIError

# Env var written by ``minos_desktop.api.cli`` from the ``--token`` flag.
# Tauri's sidecar generates a fresh token at launch and never touches the
# keyring, so the env value must take precedence here.
_TOKEN_ENV_VAR = "MINOS_DESKTOP_API_TOKEN"

# Global token manager instance
_token_manager = TokenManager()
_STREAM_TOKEN_TTL_SECONDS = 60


def _expected_api_token() -> str:
    expected_token = os.environ.get(_TOKEN_ENV_VAR)
    if expected_token is None:
        expected_token = _token_manager.get_or_create_token()
    return expected_token


def require_api_token(authorization: str | None = Header(default=None)) -> None:
    """
    Require valid Bearer token for API access.

    Args:
        authorization: Authorization header value

    Raises:
        APIError: If token is missing or invalid
    """
    if not authorization:
        raise APIError(
            detail="Missing Authorization header",
            code="UNAUTHORIZED",
            status_code=401,
        )

    if not authorization.startswith("Bearer "):
        raise APIError(
            detail="Invalid Authorization header format",
            code="UNAUTHORIZED",
            status_code=401,
        )

    provided_token = authorization[7:]  # Remove "Bearer " prefix

    # Constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(provided_token, _expected_api_token()):
        raise APIError(
            detail="Invalid token",
            code="UNAUTHORIZED",
            status_code=401,
        )


def create_stream_token(*, now: int | None = None) -> str:
    """Create a short-lived token for EventSource query auth."""
    issued_at = int(time.time() if now is None else now)
    payload = str(issued_at)
    signature = hmac.new(
        _expected_api_token().encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{signature}"


def require_stream_token(
    stream_token: str | None = Query(default=None),
) -> None:
    """Require valid short-lived SSE stream token."""
    if not stream_token:
        raise APIError(
            detail="Missing stream token",
            code="UNAUTHORIZED",
            status_code=401,
        )

    try:
        issued_at_text, provided_signature = stream_token.split(".", 1)
        issued_at = int(issued_at_text)
    except ValueError as exc:
        raise APIError(
            detail="Invalid stream token",
            code="UNAUTHORIZED",
            status_code=401,
        ) from exc

    now = int(time.time())
    if issued_at > now + 5 or now - issued_at > _STREAM_TOKEN_TTL_SECONDS:
        raise APIError(
            detail="Expired stream token",
            code="UNAUTHORIZED",
            status_code=401,
        )

    expected = create_stream_token(now=issued_at).split(".", 1)[1]
    if not secrets.compare_digest(provided_signature, expected):
        raise APIError(
            detail="Invalid token",
            code="UNAUTHORIZED",
            status_code=401,
        )
