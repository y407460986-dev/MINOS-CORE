"""Tests for draft run generation."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_register_input_package_and_generate_draft(
    test_client, demo_package_path, demo_sha256
):
    """Create project → register input → generate draft, verify status transitions."""
    proj = await test_client.post(
        "/api/projects",
        json={"name": "Draft Run Test"},
    )
    project_id = proj.json()["id"]

    pkg = await test_client.post(
        f"/api/projects/{project_id}/input-packages",
        json={
            "input_package_path": demo_package_path,
            "sha256": demo_sha256,
            "redacted": "true",
        },
    )
    assert pkg.status_code == 201
    assert pkg.json()["sha256"] == demo_sha256

    proj_detail = await test_client.get(f"/api/projects/{project_id}")
    assert proj_detail.json()["status"] == "input_registered"

    draft = await test_client.post(f"/api/projects/{project_id}/draft-runs")
    assert draft.status_code == 201
    draft_data = draft.json()
    assert draft_data["run_type"] == "draft"
    assert draft_data["status"] == "draft_ready"

    proj_detail = await test_client.get(f"/api/projects/{project_id}")
    assert proj_detail.json()["status"] == "draft_ready"


async def test_draft_run_blocked_from_wrong_state(test_client, demo_sha256):
    """generate-draft from wrong project state returns 409."""
    proj = await test_client.post(
        "/api/projects",
        json={"name": "Wrong State Test"},
    )
    project_id = proj.json()["id"]

    resp = await test_client.post(f"/api/projects/{project_id}/draft-runs")
    assert resp.status_code == 409
    assert resp.json()["code"] == "INVALID_STATE_TRANSITION"


async def test_draft_run_on_nonexistent_project(test_client):
    """POST /api/projects/{id}/draft-runs for non-existent project returns 404."""
    resp = await test_client.post(
        "/api/projects/00000000-0000-0000-0000-000000000000/draft-runs"
    )
    assert resp.status_code == 404
