"""Tests for project CRUD and status transitions."""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = pytest.mark.asyncio


async def test_create_and_list_project(test_client):
    """POST /api/projects creates a project; GET /api/projects lists it."""
    resp = await test_client.post(
        "/api/projects",
        json={"name": "Test Project Alpha", "project_code": "TPA-001", "part_number": "PN-123"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Project Alpha"
    assert data["status"] == "created"
    assert "id" in data

    resp = await test_client.get("/api/projects")
    assert resp.status_code == 200
    projects = resp.json()
    assert any(p["name"] == "Test Project Alpha" for p in projects)


async def test_get_project_not_found(test_client):
    """GET /api/projects/{id} returns 404 for unknown id."""
    resp = await test_client.get("/api/projects/does-not-exist")
    assert resp.status_code == 404


async def test_platform_rejects_requests_without_token_by_default(test_client):
    with patch.dict("os.environ", {}, clear=True):
        resp = await test_client.get("/api/projects")

    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHORIZED"


async def test_platform_allows_requests_without_token_when_dev_switch_enabled(test_client):
    with patch.dict("os.environ", {"MINOS_PLATFORM_ALLOW_NO_AUTH": "1"}, clear=True):
        resp = await test_client.get("/api/projects")

    assert resp.status_code == 200
