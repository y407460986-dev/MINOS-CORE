"""Tests for export endpoints."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_export_draft_allowed_before_review(test_client, demo_package_path, demo_sha256):
    """export with mode=draft is allowed from draft_ready state."""
    proj = await test_client.post("/api/projects", json={"name": "Export Draft Test"})
    project_id = proj.json()["id"]

    await test_client.post(
        f"/api/projects/{project_id}/input-packages",
        json={"input_package_path": demo_package_path, "sha256": demo_sha256, "redacted": "true"},
    )
    await test_client.post(f"/api/projects/{project_id}/draft-runs")

    export_resp = await test_client.post(
        f"/api/projects/{project_id}/exports",
        json={"export_mode": "draft"},
    )
    assert export_resp.status_code == 201
    export_data = export_resp.json()
    assert "export_path" in export_data


async def test_export_final_blocked_before_review(test_client, demo_package_path, demo_sha256):
    """export with mode=final returns 409 when project has no applied review."""
    proj = await test_client.post("/api/projects", json={"name": "Export Final Blocked Test"})
    project_id = proj.json()["id"]

    await test_client.post(
        f"/api/projects/{project_id}/input-packages",
        json={"input_package_path": demo_package_path, "sha256": demo_sha256, "redacted": "true"},
    )
    await test_client.post(f"/api/projects/{project_id}/draft-runs")

    export_resp = await test_client.post(
        f"/api/projects/{project_id}/exports",
        json={"export_mode": "final"},
    )
    assert export_resp.status_code == 409
