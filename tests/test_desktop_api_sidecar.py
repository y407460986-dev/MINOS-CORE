from __future__ import annotations

import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from minos_desktop.api import jobs
from minos_desktop.api.app import create_app
from minos_desktop.app_state import (
    ChainStageStates,
    DesktopRunState,
    StageConfirmState,
)
from minos_desktop.services import DesktopRunService

pytestmark = pytest.mark.asyncio


def _fake_result() -> dict:
    return {
        "document_type": "three_table_generation_result",
        "status": "needs_review",
        "process_flow": {
            "steps": [
                {
                    "process_step_id": "P10",
                    "operation": "来料检验",
                    "review_status": "AI建议确认",
                    "needs_confirmation": True,
                }
            ]
        },
        "pfmea": {"rows": []},
        "control_plan": {"rows": []},
        "metadata": {
            "knowledge_recommendations": [
                {"recommendation_id": "KR-1", "status": "待确认"}
            ],
            "change_impacts": [{"item_id": "CI-1", "status": "待同步"}],
        },
        "manual_review": {"required": True, "items": []},
        "exports": {},
        "manifest": {"run_id": "fake-run", "path": "manifest.json"},
    }


@pytest.fixture
async def client(tmp_path, monkeypatch):
    db_path = tmp_path / "desktop.sqlite3"
    output_dir = tmp_path / "out"
    app = create_app(db_path=db_path, output_dir=output_dir)

    def fake_start_chain_run(db_path, project_id):
        project_output = output_dir / f"project-{project_id}"
        result = _fake_result()
        chain_stages = ChainStageStates(
            pfd=StageConfirmState(status="generated", row_count=1, pending_count=1),
            pipeline_mode="chain",
        )
        state = DesktopRunState(
            status="needs_review",
            status_display="待人工确认",
            blocked_stage="",
            exports=(),
            manifest_path="",
            manifest_run_id="",
            manual_review_required=True,
            manual_review_count=0,
            manual_review_raw_count=0,
            manual_review_items=(),
            chain_stages=chain_stages,
        )
        return DesktopRunService(db_path).save_chain_run(
            project_id,
            state,
            project_output,
            result,
            "",
            chain_stages,
        )

    monkeypatch.setattr(jobs, "start_chain_run", fake_start_chain_run)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


async def test_health_allows_no_token_when_env_token_is_absent(client, monkeypatch):
    monkeypatch.delenv("MINOS_DESKTOP_API_TOKEN", raising=False)

    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_token_auth_requires_bearer_token_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("MINOS_DESKTOP_API_TOKEN", "secret-token")
    app = create_app(db_path=tmp_path / "auth.sqlite3", output_dir=tmp_path / "out")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as authed_client:
        rejected = await authed_client.get("/api/health")
        accepted = await authed_client.get(
            "/api/health",
            headers={"Authorization": "Bearer secret-token"},
        )

    assert rejected.status_code == 401
    assert rejected.json()["code"] == "UNAUTHORIZED"
    assert "failure_message" in rejected.json()
    assert accepted.status_code == 200


async def test_project_run_recent_restore_edit_and_export_flow(client):
    project_response = await client.post(
        "/api/projects",
        json={
            "project_name": "API 项目",
            "drawing_path": "drawing.pdf",
            "context": {"part_no": "A-001"},
        },
    )
    assert project_response.status_code == 201
    project = project_response.json()

    recent_projects = await client.get("/api/projects/recent")
    assert recent_projects.status_code == 200
    assert recent_projects.json()[0]["project_name"] == "API 项目"

    run_response = await client.post(f"/api/projects/{project['id']}/runs")
    assert run_response.status_code == 201
    run = run_response.json()
    assert run["project_id"] == project["id"]
    assert run["status"] == "needs_review"
    assert run["pipeline_mode"] == "chain"
    assert run["chain_stages"]["pfd"]["status"] == "generated"
    assert run["current_result"]["pfmea"]["rows"] == []
    assert run["current_result"]["control_plan"]["rows"] == []

    edit_response = await client.patch(
        f"/api/runs/{run['id']}/edit-patch",
        json={
            "patch": {
                "items": [
                    {
                        "action": "update",
                        "table": "process_flow",
                        "target": "process_step:P10",
                        "row_id": "P10",
                        "changes": {"operation": "来料检验-已复核"},
                    }
                ]
            }
        },
    )
    assert edit_response.status_code == 200
    assert (
        edit_response.json()["current_result"]["process_flow"]["steps"][0]["operation"]
        == "来料检验-已复核"
    )

    table_response = await client.get(f"/api/runs/{run['id']}/tables/process_flow")
    assert table_response.status_code == 200
    assert table_response.json()["rows"][0]["process_step_id"] == "P10"

    recent_runs = await client.get("/api/runs/recent")
    restored = await client.post(f"/api/runs/{run['id']}/restore")
    export_dir = Path(run["output_dir"]) / "exports"
    exported = await client.post(
        f"/api/runs/{run['id']}/exports",
        json={"output_dir": str(export_dir), "export_mode": "draft"},
    )

    assert recent_runs.status_code == 200
    assert recent_runs.json()[0]["id"] == run["id"]
    assert restored.status_code == 200
    assert exported.status_code == 201
    assert exported.json()["export_mode"] == "draft"


async def test_chain_pfd_confirm_applies_edit_patch_before_generating_pfmea(
    client, monkeypatch
):
    def fake_generate_pfmea(_drawing_analysis, confirmed_pfd):
        operation = confirmed_pfd["steps"][0]["operation"]
        return {
            "rows": [
                {
                    "pfmea_id": "F1",
                    "process_step_id": "P10",
                    "operation_seen_by_pfmea": operation,
                    "needs_confirmation": False,
                }
            ]
        }

    monkeypatch.setattr(
        "minos_core.pipeline_chain.generate_pfmea_from_confirmed_pfd",
        fake_generate_pfmea,
    )
    project = (
        await client.post(
            "/api/projects",
            json={"project_name": "链式确认项目", "drawing_path": "drawing.pdf"},
        )
    ).json()
    run = (await client.post(f"/api/projects/{project['id']}/runs")).json()

    response = await client.post(
        f"/api/runs/{run['id']}/chain/pfd-confirm",
        json={
            "confirmed_by": "qe",
            "edit_patch": {
                "items": [
                    {
                        "action": "update",
                        "table": "process_flow",
                        "row_id": "P10",
                        "changes": {"operation": "来料检验-确认时修改"},
                    }
                ]
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    step = body["current_result"]["process_flow"]["steps"][0]
    assert step["operation"] == "来料检验-确认时修改"
    assert step["review_status"] == "已确认"
    assert step["confirmed_by"] == "qe"
    assert body["chain_stages"]["pfd"]["status"] == "confirmed"
    assert body["chain_stages"]["pfmea"]["status"] == "running"
    assert body["edit_patch"]["items"][0]["target_id"] == "P10"

    restored = (await client.get(f"/api/runs/{run['id']}")).json()
    pfmea_row = restored["current_result"]["pfmea"]["rows"][0]
    assert pfmea_row["operation_seen_by_pfmea"] == "来料检验-确认时修改"
    assert restored["chain_stages"]["pfmea"]["status"] == "generated"


async def test_closure_routes_update_run_metadata(client):
    project = (
        await client.post(
            "/api/projects",
            json={"project_name": "闭环项目", "drawing_path": "drawing.pdf"},
        )
    ).json()
    run = (await client.post(f"/api/projects/{project['id']}/runs")).json()

    ignored = await client.post(
        f"/api/runs/{run['id']}/recommendations/KR-1/ignore",
        json={"reason": "已有等效控制"},
    )
    assert ignored.status_code == 200
    assert (
        ignored.json()["current_result"]["metadata"]["knowledge_recommendations"][0][
            "status"
        ]
        == "已忽略"
    )

    project_for_batch = (
        await client.post(
            "/api/projects",
            json={"project_name": "批量确认项目", "drawing_path": "drawing.pdf"},
        )
    ).json()
    run_for_batch = (
        await client.post(f"/api/projects/{project_for_batch['id']}/runs")
    ).json()
    batch = await client.post(
        f"/api/runs/{run_for_batch['id']}/automation-review/batch-confirm"
    )

    assert batch.status_code == 200
    assert batch.json()["current_result"]["process_flow"]["steps"][0]["review_status"] == "已批量确认"

    impact = await client.post(
        f"/api/runs/{run['id']}/change-impacts/CI-1/resolve",
        json={"status": "已处理"},
    )
    assert impact.status_code == 200
    assert impact.json()["current_result"]["metadata"]["change_impacts"][0]["status"] == "已处理"


async def test_missing_run_returns_structured_failure(client):
    response = await client.get("/api/runs/9999")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "NOT_FOUND"
    assert "desktop run not found" in body["detail"]
    assert "failure_message" in body
