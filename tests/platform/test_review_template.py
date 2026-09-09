"""Tests for review template generation."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_review_template_from_draft(
    test_client, demo_package_path, demo_sha256
):
    """After generate-draft, review-template returns template with correct fields."""
    proj = await test_client.post("/api/projects", json={"name": "Review Template Test"})
    project_id = proj.json()["id"]

    await test_client.post(
        f"/api/projects/{project_id}/input-packages",
        json={"input_package_path": demo_package_path, "sha256": demo_sha256, "redacted": "true"},
    )
    await test_client.post(f"/api/projects/{project_id}/draft-runs")

    tmpl = await test_client.post(f"/api/projects/{project_id}/review-template")
    assert tmpl.status_code == 201
    data = tmpl.json()
    assert "template_path" in data
    assert data["run_id"]

    proj_detail = await test_client.get(f"/api/projects/{project_id}")
    assert proj_detail.json()["status"] == "review_template_ready"


async def test_review_template_blocked_from_wrong_state(test_client):
    """review-template from non-draft_ready state returns 409."""
    proj = await test_client.post("/api/projects", json={"name": "Wrong State"})
    project_id = proj.json()["id"]

    resp = await test_client.post(f"/api/projects/{project_id}/review-template")
    assert resp.status_code == 409


async def test_review_template_on_nonexistent_project(test_client):
    """POST /api/projects/{id}/review-template for non-existent project returns 404."""
    resp = await test_client.post(
        "/api/projects/00000000-0000-0000-0000-000000000000/review-template"
    )
    assert resp.status_code == 404
