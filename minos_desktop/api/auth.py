"""Bearer-token auth for the local desktop API."""

from __future__ import annotations

import secrets

from fastapi import Header

from minos_desktop.security.token_manager import TokenManager

from .schemas import APIError

# Global token manager instance
_token_manager = TokenManager()


def require_api_token(authorization: str | None = Header(default=None)) -> None:
    """
    Require valid Bearer token for API access.

    Args:
        authorization: Authorization header value

    Raises:
        APIError: If token is missing or invalid
    """
    expected_token = _token_manager.get_or_create_token()

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
    if not secrets.compare_digest(provided_token, expected_token):
        raise APIError(
            detail="Invalid token",
            code="UNAUTHORIZED",
            status_code=401,
        )
