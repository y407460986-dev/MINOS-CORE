"""Health routes for the local desktop API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "status": "ok", "service": "minos-desktop-api", "version": "3.8.6"}
