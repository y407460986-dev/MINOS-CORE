"""Authentication helper routes for the desktop sidecar."""

from __future__ import annotations

from fastapi import APIRouter

from .auth import create_stream_token

router = APIRouter()


@router.post("/auth/stream-token")
def issue_stream_token() -> dict[str, int | str]:
    return {
        "stream_token": create_stream_token(),
        "expires_in_seconds": 60,
    }
