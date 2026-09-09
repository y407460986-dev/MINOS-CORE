"""Tests for review patch submission endpoints."""

from __future__ import annotations

import json
import tempfile

import pytest

from minos_core import sha256_json

pytestmark = pytest.mark.asyncio


async def _run_full_chain(client, project_id, demo_package_path, sha256):
    """Helper: run project -> input -> draft -> review_template."""
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


async def test_review_patch_copied_to_artifact_area(test_client, demo_package_path, demo_sha256):
    """After submitting a review patch, verify the stored patch_path starts with out/platform/."""
    proj = await test_client.post("/api/projects", json={"name": "Patch Copied Test"})
    project_id = proj.json()["id"]

    _, template_data = await _run_full_chain(test_client, project_id, demo_package_path, demo_sha256)

    patch_data = {
        **template_data,
        "confirmed_by": "qa.engineer",
        "confirmed_at": "2026-04-25T10:00:00Z",
        "reason": "test approval",
    }
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

    patch_record = submit_resp.json()
    stored_path = patch_record["patch_path"]
    # Verify the stored path is inside the platform artifact directory, not the original user path
    # Normalize backslashes for Windows path comparison
    normalized_path = stored_path.replace("\\", "/")
    assert "out/platform/" in normalized_path, f"Expected path containing 'out/platform/', got: {stored_path}"


async def test_review_patch_sha256_validated(test_client, demo_package_path, demo_sha256):
    """Submitting a review patch with wrong sha256 returns 422."""
    proj = await test_client.post("/api/projects", json={"name": "Patch SHA256 Validation Test"})
    project_id = proj.json()["id"]

    _, template_data = await _run_full_chain(test_client, project_id, demo_package_path, demo_sha256)

    patch_data = {
        **template_data,
        "confirmed_by": "qa.engineer",
        "confirmed_at": "2026-04-25T10:00:00Z",
        "reason": "test approval",
    }
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

    # Use a deliberately wrong SHA256
    wrong_sha256 = "0000000000000000000000000000000000000000000000000000000000000000"

    resp = await test_client.post(
        f"/api/projects/{project_id}/review-patches",
        json={"patch_path": patch_path, "sha256": wrong_sha256},
    )
    assert resp.status_code == 422


async def test_template_patch_rejected(test_client, demo_package_path, demo_sha256):
    """Submitting a raw template JSON (with template_status field) returns 422 with code REVIEW_PATCH_ERROR."""
    proj = await test_client.post("/api/projects", json={"name": "Template Patch Rejected Test"})
    project_id = proj.json()["id"]

    _, template_data = await _run_full_chain(test_client, project_id, demo_package_path, demo_sha256)

    # Include the template_status field (raw template JSON) to simulate the error
    template_data["confirmed_by"] = "qa.engineer"
    template_data["confirmed_at"] = "2026-04-25T10:00:00Z"
    template_data["reason"] = "test approval"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(template_data, f)
        patch_path = f.name

    patch_sha = sha256_json(template_data)

    resp = await test_client.post(
        f"/api/projects/{project_id}/review-patches",
        json={"patch_path": patch_path, "sha256": patch_sha},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "INVALID_PATCH"
