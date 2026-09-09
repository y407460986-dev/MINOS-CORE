"""Tests for apply-review chain."""

from __future__ import annotations

import json
import tempfile

import pytest

from minos_core import sha256_json

pytestmark = pytest.mark.asyncio


async def _run_full_chain(client, project_id, demo_package_path, sha256):
    """Helper: run project → input → draft → review_template."""
    await client.post(
        f"/api/projects/{project_id}/input-packages",
        json={"input_package_path": demo_package_path, "sha256": sha256, "redacted": "true"},
    )
    draft_resp = await client.post(f"/api/projects/{project_id}/draft-runs")
    draft_data = draft_resp.json()
    draft_result_path = draft_data["result_json_path"]

    template_resp = await client.post(f"/api/projects/{project_id}/review-template")
    template_path = template_resp.json()["template_path"]

    template_data = json.loads(open(template_path, encoding="utf-8").read())
    return draft_result_path, template_data


async def test_apply_review_chain(test_client, demo_package_path, demo_sha256):
    """Full chain: project → input → draft → review-template → review-patch → apply-review."""
    proj = await test_client.post("/api/projects", json={"name": "Apply Review Test"})
    project_id = proj.json()["id"]

    draft_result_path, template_data = await _run_full_chain(
        test_client, project_id, demo_package_path, demo_sha256
    )

    patch_data = {
        **template_data,
        "confirmed_by": "qa.engineer",
        "confirmed_at": "2026-04-25T10:00:00Z",
        "reason": "test approval",
    }
    # Must remove template_status — apply_review_patch rejects templates
    patch_data.pop("template_status", None)
    for item in patch_data.get("items", []):
        item["confirmed_by"] = "qa.engineer"
        item["confirmed_at"] = "2026-04-25T10:00:00Z"
        item["reason"] = "test approval"
        item["evidence_refs"] = ["EV-DEMO-REQ-001"]
        if "manual_confirmation_event" not in item:
            item["manual_confirmation_event"] = "test-event-001"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(patch_data, f)
        patch_path = f.name

    patch_sha = sha256_json(patch_data)

    submit_resp = await test_client.post(
        f"/api/projects/{project_id}/review-patches",
        json={"patch_path": patch_path, "sha256": patch_sha},
    )
    assert submit_resp.status_code == 201

    apply_resp = await test_client.post(f"/api/projects/{project_id}/apply-review")
    assert apply_resp.status_code == 201
    apply_data = apply_resp.json()
    assert "review_result_path" in apply_data
    assert apply_data["final_export_allowed"]

    proj_detail = await test_client.get(f"/api/projects/{project_id}")
    assert proj_detail.json()["status"] == "review_applied"


async def test_apply_review_on_nonexistent_project(test_client):
    """POST /api/projects/{id}/apply-review for non-existent project returns 404."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    apply_resp = await test_client.post(f"/api/projects/{fake_id}/apply-review")
    assert apply_resp.status_code == 404


async def test_apply_review_wrong_state(test_client):
    """POST /api/projects/{project_id}/apply-review for a project in 'created' state returns 409."""
    proj = await test_client.post("/api/projects", json={"name": "Apply Review Wrong State Test"})
    project_id = proj.json()["id"]

    apply_resp = await test_client.post(f"/api/projects/{project_id}/apply-review")
    assert apply_resp.status_code == 409
    apply_data = apply_resp.json()
    assert apply_data.get("code") == "INVALID_STATE_TRANSITION"
