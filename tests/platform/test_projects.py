"""Tests for project CRUD and status transitions."""

from __future__ import annotations

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


async def test_create_project_empty_name(test_client):
    """POST /api/projects with empty name returns 422."""
    resp = await test_client.post(
        "/api/projects",
        json={"name": "", "project_code": "TPA-002", "part_number": "PN-456"},
    )
    assert resp.status_code == 422


async def test_get_project_rejects_invalid_id(test_client):
    """GET /api/projects/{id} with a valid UUID format but non-existent returns 404."""
    resp = await test_client.get("/api/projects/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
