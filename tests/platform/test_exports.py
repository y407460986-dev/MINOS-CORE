"""Tests for export endpoints."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from minos_core import sha256_json

pytestmark = pytest.mark.asyncio


async def _run_full_chain(client, project_id, demo_package_path, sha256):
    """Helper: run project -> input -> draft -> review_template -> submit patch -> apply-review."""
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

    patch_data = {**template_data, "confirmed_by": "qa.engineer", "confirmed_at": "2026-04-25T10:00:00Z", "reason": "test"}
    patch_data.pop("template_status", None)
    for item in patch_data.get("items", []):
        item["confirmed_by"] = "qa.engineer"
        item["confirmed_at"] = "2026-04-25T10:00:00Z"
        item["reason"] = "test"
        item["evidence_refs"] = ["EV-DEMO-REQ-001"]
        if "manual_confirmation_event" not in item:
            item["manual_confirmation_event"] = "test-event-001"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(patch_data, f)
        patch_path = f.name

    patch_sha = sha256_json(patch_data)
    await client.post(
        f"/api/projects/{project_id}/review-patches",
        json={"patch_path": patch_path, "sha256": patch_sha},
    )
    await client.post(f"/api/projects/{project_id}/apply-review")

    return draft_result_path, template_data


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


async def test_export_final_sets_final_export_ready(test_client, demo_package_path, demo_sha256):
    """After full chain with apply-review, final export returns 201 and project status is final_export_ready."""
    proj = await test_client.post("/api/projects", json={"name": "Export Final Ready Test"})
    project_id = proj.json()["id"]

    await _run_full_chain(test_client, project_id, demo_package_path, demo_sha256)

    export_resp = await test_client.post(
        f"/api/projects/{project_id}/exports",
        json={"export_mode": "final"},
    )
    assert export_resp.status_code == 201

    proj_detail = await test_client.get(f"/api/projects/{project_id}")
    assert proj_detail.json()["status"] == "final_export_ready"


async def test_draft_export_does_not_change_project_status(test_client, demo_package_path, demo_sha256):
    """After draft export, project status remains at its previous state (e.g., draft_ready), not final_export_ready."""
    proj = await test_client.post("/api/projects", json={"name": "Draft Export Status Test"})
    project_id = proj.json()["id"]

    await test_client.post(
        f"/api/projects/{project_id}/input-packages",
        json={"input_package_path": demo_package_path, "sha256": demo_sha256, "redacted": "true"},
    )
    await test_client.post(f"/api/projects/{project_id}/draft-runs")

    proj_detail_before = await test_client.get(f"/api/projects/{project_id}")
    status_before = proj_detail_before.json()["status"]
    assert status_before == "draft_ready"

    export_resp = await test_client.post(
        f"/api/projects/{project_id}/exports",
        json={"export_mode": "draft"},
    )
    assert export_resp.status_code == 201

    proj_detail_after = await test_client.get(f"/api/projects/{project_id}")
    status_after = proj_detail_after.json()["status"]
    assert status_after == status_before
    assert status_after != "final_export_ready"


async def test_export_final_rejects_when_project_status_is_not_review_applied(
    test_client, demo_package_path, demo_sha256
):
    proj = await test_client.post("/api/projects", json={"name": "Export Final Status Gate Test"})
    project_id = proj.json()["id"]
    draft_result_path, _ = await _run_full_chain(
        test_client, project_id, demo_package_path, demo_sha256
    )

    apply_run_id = "manual-review-run"
    review_result_path = Path(draft_result_path).with_name("manual_review_result.json")
    review_result_path.write_text(
        json.dumps(
            {
                "document_type": "apqp_chain_review_result",
                "patched_chain": {"document_type": "apqp_chain", "process_steps": [], "failure_modes": [], "controls": []},
                "final_export_allowed": True,
            }
        ),
        encoding="utf-8",
    )

    from minos_platform import db
    from sqlalchemy import select
    from datetime import datetime, timezone

    async with db._session_factory() as session:
        project = (
            await session.execute(select(db.Project).where(db.Project.id == project_id))
        ).scalar_one()
        project.status = "review_patch_submitted"
        session.add(
            db.Run(
                id=apply_run_id,
                project_id=project_id,
                run_type="review",
                status="review_applied",
                result_json_path=str(review_result_path),
                manifest_json_path=None,
                created_at=datetime.now(timezone.utc).replace(microsecond=0),
            )
        )
        await session.commit()

    export_resp = await test_client.post(
        f"/api/projects/{project_id}/exports",
        json={"export_mode": "final"},
    )

    assert export_resp.status_code == 409


async def test_export_final_rejects_non_object_patched_chain(
    test_client, demo_package_path, demo_sha256
):
    proj = await test_client.post("/api/projects", json={"name": "Export Final Patched Chain Type Test"})
    project_id = proj.json()["id"]
    draft_result_path, _ = await _run_full_chain(
        test_client, project_id, demo_package_path, demo_sha256
    )

    review_result_path = Path(draft_result_path).with_name("review_result_bad_chain.json")
    review_result_path.write_text(
        json.dumps(
            {
                "document_type": "apqp_chain_review_result",
                "patched_chain": ["bad"],
                "final_export_allowed": True,
            }
        ),
        encoding="utf-8",
    )

    from minos_platform import db
    from sqlalchemy import select

    async with db._session_factory() as session:
        project = (
            await session.execute(select(db.Project).where(db.Project.id == project_id))
        ).scalar_one()
        project.status = "review_applied"
        latest_review_run = (
            await session.execute(
                select(db.Run)
                .where(db.Run.project_id == project_id, db.Run.run_type == "review")
                .order_by(db.Run.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest_review_run is not None:
            latest_review_run.result_json_path = str(review_result_path)
        await session.commit()

    export_resp = await test_client.post(
        f"/api/projects/{project_id}/exports",
        json={"export_mode": "final"},
    )

    assert export_resp.status_code == 422


async def test_export_final_rejects_review_result_when_quality_gate_not_cleared(
    test_client, demo_package_path, demo_sha256
):
    proj = await test_client.post("/api/projects", json={"name": "Export Final Quality Gate Test"})
    project_id = proj.json()["id"]
    await _run_full_chain(
        test_client, project_id, demo_package_path, demo_sha256
    )

    from minos_platform import db
    from sqlalchemy import select

    async with db._session_factory() as session:
        project = (
            await session.execute(select(db.Project).where(db.Project.id == project_id))
        ).scalar_one()
        project.status = "review_applied"
        latest_review_run = (
            await session.execute(
                select(db.Run)
                .where(db.Run.project_id == project_id, db.Run.run_type == "review")
                .order_by(db.Run.created_at.desc())
                .limit(1)
            )
        ).scalar_one()
        review_result_path = Path(latest_review_run.result_json_path)
        review_result = json.loads(review_result_path.read_text(encoding="utf-8"))
        review_result["final_export_allowed"] = False
        blocked_review_result_path = review_result_path.with_name(
            "review_result_gate_blocked.json"
        )
        blocked_review_result_path.write_text(
            json.dumps(review_result),
            encoding="utf-8",
        )
        latest_review_run.result_json_path = str(blocked_review_result_path)
        await session.commit()

    export_resp = await test_client.post(
        f"/api/projects/{project_id}/exports",
        json={"export_mode": "final"},
    )

    assert export_resp.status_code == 409
    assert export_resp.json()["code"] == "EXPORT_GATE_BLOCKED"
