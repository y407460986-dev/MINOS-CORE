"""Tests for the artifacts router -- list and download endpoints."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_list_artifacts_empty(test_client):
    """List artifacts on a fresh DB returns an empty list."""
    resp = await test_client.get("/api/artifacts")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_download_artifact_not_found(test_client):
    """Downloading a non-existent artifact returns 404 (NotFoundError)."""
    resp = await test_client.get("/api/artifacts/does-not-exist")
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert "artifact" in detail.lower() or "not found" in detail.lower()
