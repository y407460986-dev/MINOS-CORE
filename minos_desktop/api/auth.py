"""Bearer-token auth for the local desktop API."""

from __future__ import annotations

import os

from fastapi import Header

from .schemas import APIError


def require_api_token(authorization: str | None = Header(default=None)) -> None:
    token = os.getenv("MINOS_DESKTOP_API_TOKEN")
    if not token:
        return
    expected = f"Bearer {token}"
    if authorization != expected:
        raise APIError(
            detail="missing or invalid Authorization bearer token",
            code="UNAUTHORIZED",
            status_code=401,
        )
