"""Health routes for the local desktop API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from minos_desktop import __version__

router = APIRouter()


@router.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "status": "ok",
        "service": "minos-desktop-api",
        "version": __version__,
    }
