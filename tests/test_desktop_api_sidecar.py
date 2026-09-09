from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from minos_desktop.api import jobs
from minos_desktop.api.app import create_app
from minos_desktop.app_state import (
    ChainStageStates,
    DesktopProjectState,
    DesktopRunState,
    StageConfirmState,
)
from minos_desktop.services import DesktopProjectStore, DesktopRunService, DesktopSettingsStore

pytestmark = pytest.mark.asyncio

TEST_API_TOKEN = "test-token"


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
                    "confidence": 0.91,
                    "evidence_refs": ["EV-P10"],
                }
            ]
        },
        "pfmea": {"rows": []},
        "control_plan": {"rows": []},
        "linkage_report": {
            "sync_suggestions": [
                {
                    "suggestion_id": "SYNC-PFD-P10-PFMEA",
                    "source": "process_flow:P10",
                    "target_table": "pfmea",
                    "suggested_action": "add",
                    "suggested_fields": {"process_step_id": "P10"},
                }
            ]
        },
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


def _write_test_pdf(tmp_path: Path, name: str = "drawing.pdf") -> str:
    drawing = tmp_path / name
    drawing.write_bytes(b"%PDF-1.7\n% test drawing\n")
    return str(drawing)


async def _create_test_run(
    client: AsyncClient, tmp_path: Path, project_name: str
) -> int:
    project_response = await client.post(
        "/api/projects",
        json={
            "project_name": project_name,
            "drawing_path": _write_test_pdf(tmp_path, f"{project_name}.pdf"),
        },
    )
    assert project_response.status_code == 201
    project_id = int(project_response.json()["id"])
    run_response = await client.post(f"/api/projects/{project_id}/runs")
    assert run_response.status_code == 201
    return int(run_response.json()["id"])


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MINOS_DESKTOP_API_TOKEN", TEST_API_TOKEN)
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
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {TEST_API_TOKEN}"},
    ) as test_client:
        yield test_client


async def test_health_requires_bearer_token_when_env_token_is_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("MINOS_DESKTOP_API_TOKEN", raising=False)
    app = create_app(db_path=tmp_path / "auth.sqlite3", output_dir=tmp_path / "out")
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        response = await test_client.get("/api/health")

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


async def test_tauri_sidecar_lifecycle_has_rust_unit_contracts() -> None:
    rust_source = (
        Path(__file__).resolve().parents[1]
        / "apps"
        / "desktop-tauri"
        / "src-tauri"
        / "src"
        / "lib.rs"
    ).read_text(encoding="utf-8")

    assert "enum SidecarPhase" in rust_source
    assert "Barrier::new(8)" in rust_source
    assert "AtomicUsize" in rust_source
    assert "fn concurrent_ensure_spawns_only_once" in rust_source
    assert "fn terminated_old_pid_does_not_clear_new_pid" in rust_source
    assert "fn readiness_timeout_returns_error_and_cleans_up_registered_pid" in rust_source


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


async def test_tauri_https_origin_preflight_is_allowed(tmp_path, monkeypatch):
    monkeypatch.setenv("MINOS_DESKTOP_API_TOKEN", TEST_API_TOKEN)
    app = create_app(db_path=tmp_path / "cors.sqlite3", output_dir=tmp_path / "out")
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        response = await test_client.options(
            "/api/projects/1/chain-runs",
            headers={
                "Origin": "https://tauri.localhost",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://tauri.localhost"


async def test_patch_ai_config_persists_overrides_without_returning_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("MINOS_DESKTOP_API_TOKEN", TEST_API_TOKEN)
    monkeypatch.delenv("MINOS_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.setenv("MINOS_DISABLE_CODEX_CONFIG", "1")
    db_path = tmp_path / "desktop.sqlite3"
    app = create_app(db_path=db_path, output_dir=tmp_path / "out")
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {TEST_API_TOKEN}"},
    ) as test_client:
        response = await test_client.patch(
            "/api/settings/ai-config",
            json={
                "base_url": "https://user-proxy.example/v1",
                "api_key": "api-secret-from-ui",
                "model": "gpt-user",
            },
        )

    assert response.status_code == 200
    body = response.json()
    ai = body["ai_config"]
    assert ai["base_url"] == "https://user-proxy.example/v1"
    assert ai["model"] == "gpt-user"
    assert ai["api_key_configured"] is True
    assert ai["api_key_source"] == "user_settings"
    assert ai["base_url_override"] == "https://user-proxy.example/v1"
    assert ai["model_override"] == "gpt-user"
    assert ai["api_key_override_set"] is True
    assert "api-secret-from-ui" not in str(body)
    assert DesktopSettingsStore(db_path).get_ai_overrides()["api_key"] == "api-secret-from-ui"


async def test_patch_ai_config_validation_error_does_not_echo_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("MINOS_DESKTOP_API_TOKEN", TEST_API_TOKEN)
    app = create_app(db_path=tmp_path / "desktop.sqlite3", output_dir=tmp_path / "out")
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {TEST_API_TOKEN}"},
    ) as test_client:
        response = await test_client.patch(
            "/api/settings/ai-config",
            json={"api_key": {"plain": "api-secret-from-ui"}},
        )

    assert response.status_code == 422
    assert "api-secret-from-ui" not in response.text


async def test_data_management_api_reports_backup_and_clear(tmp_path, monkeypatch):
    monkeypatch.setenv("MINOS_DESKTOP_API_TOKEN", TEST_API_TOKEN)
    db_path = tmp_path / "desktop.sqlite3"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "artifact.txt").write_text("export", encoding="utf-8")
    app = create_app(db_path=db_path, output_dir=output_dir)
    settings = DesktopSettingsStore(db_path)
    settings.set_default_output_dir(output_dir)
    project = DesktopProjectStore(db_path).create_project(
        DesktopProjectState(
            project_name="数据 API 项目",
            drawing_path="drawing.pdf",
            output_dir=str(output_dir),
        )
    )
    DesktopRunService(db_path).save_result(
        project.id,
        {"status": "needs_review", "manual_review": {"required": False, "items": []}},
        str(output_dir),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {TEST_API_TOKEN}"},
    ) as test_client:
        status = await test_client.get("/api/settings/data-management")
        backup = await test_client.post("/api/settings/data-management/backup")
        rejected = await test_client.post(
            "/api/settings/data-management/clear",
            json={
                "scope": "workspace",
                "delete_outputs": True,
                "confirm_text": "错误确认",
            },
        )
        cleared = await test_client.post(
            "/api/settings/data-management/clear",
            json={
                "scope": "workspace",
                "delete_outputs": True,
                "confirm_text": "清空项目",
            },
        )

    assert status.status_code == 200
    body = status.json()
    assert body["data_dir"] == str(tmp_path)
    assert body["db_path"] == str(db_path)
    assert body["output_dir"] == str(output_dir)
    assert body["project_count"] == 1
    assert body["run_count"] == 1
    assert body["output_size_bytes"] >= 6
    assert backup.status_code == 200
    assert Path(backup.json()["backup_path"]).exists()
    assert rejected.status_code == 422
    assert cleared.status_code == 200
    assert cleared.json()["project_count"] == 0
    assert cleared.json()["run_count"] == 0
    assert not (output_dir / "artifact.txt").exists()


async def test_project_run_recent_restore_edit_and_export_flow(client, tmp_path):
    project_response = await client.post(
        "/api/projects",
        json={
            "project_name": "API 项目",
            "drawing_path": _write_test_pdf(tmp_path),
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
    client, monkeypatch, tmp_path
):
    def fake_generate_pfmea(_drawing_analysis, confirmed_pfd, model=None, on_progress=None):
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
            json={
                "project_name": "链式确认项目",
                "drawing_path": _write_test_pdf(tmp_path),
            },
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


async def test_closure_routes_update_run_metadata(client, tmp_path):
    project = (
        await client.post(
            "/api/projects",
            json={
                "project_name": "闭环项目",
                "drawing_path": _write_test_pdf(tmp_path),
            },
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
            json={
                "project_name": "批量确认项目",
                "drawing_path": _write_test_pdf(tmp_path, "batch-drawing.pdf"),
            },
        )
    ).json()
    run_for_batch = (
        await client.post(f"/api/projects/{project_for_batch['id']}/runs")
    ).json()
    cp_confirmed = await client.post(
        f"/api/runs/{run_for_batch['id']}/chain/cp-confirm",
        json={"confirmed_by": "qe"},
    )
    batch = await client.post(
        f"/api/runs/{run_for_batch['id']}/automation-review/batch-confirm"
    )

    assert cp_confirmed.status_code == 200
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


async def test_linkage_sync_does_not_create_pfmea_placeholder_for_chain_run(client, tmp_path):
    project = (
        await client.post(
            "/api/projects",
            json={
                "project_name": "PFMEA占位防护项目",
                "drawing_path": _write_test_pdf(tmp_path),
            },
        )
    ).json()
    run = (await client.post(f"/api/projects/{project['id']}/runs")).json()

    response = await client.post(
        f"/api/runs/{run['id']}/linkage/apply-sync",
        json={"apply_all": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["current_result"]["pfmea"]["rows"] == []


# ---------------------------------------------------------------------------
#  Error path tests for routes_runs.py
# ---------------------------------------------------------------------------


async def test_recent_runs_empty(client):
    """Test that recent-runs returns an empty list when no runs exist (uses
    a high run_id that can't collide with the fixture's run)."""
    response = await client.get("/api/runs/recent?limit=5")
    assert response.status_code == 200
    assert response.json() == []


async def test_get_run_not_found(client):
    response = await client.get("/api/runs/999999")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "NOT_FOUND"


async def test_drawing_analysis_not_found(client):
    response = await client.get("/api/runs/999999/drawing-analysis")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


async def test_restore_run_not_found(client):
    response = await client.post("/api/runs/999999/restore")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


async def test_edit_patch_run_not_found(client):
    response = await client.patch(
        "/api/runs/999999/edit-patch",
        json={"patch": {}},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


async def test_drawing_confirmations_run_not_found(client):
    response = await client.patch(
        "/api/runs/999999/drawing-confirmations",
        json={},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


async def test_part_family_run_not_found(client):
    response = await client.get("/api/runs/999999/part-family")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


async def test_update_part_family_run_not_found(client):
    response = await client.patch(
        "/api/runs/999999/part-family",
        json={},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


async def test_process_flow_confirmations_run_not_found(client):
    response = await client.patch(
        "/api/runs/999999/process-flow-confirmations",
        json={},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


async def test_chain_state_not_found(client):
    response = await client.get("/api/runs/999999/chain/state")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


async def test_undo_no_operations(client, tmp_path):
    """undo on a run without undo history returns a ValueError (422)."""
    run_id = await _create_test_run(client, tmp_path, "undo-empty")
    response = await client.post(f"/api/runs/{run_id}/undo")
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALUE_ERROR"
    assert "没有可以撤销的操作" in body["detail"]


async def test_redo_no_operations(client, tmp_path):
    """redo on a run without redo history returns a ValueError (422)."""
    run_id = await _create_test_run(client, tmp_path, "redo-empty")
    response = await client.post(f"/api/runs/{run_id}/redo")
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALUE_ERROR"
    assert "没有可以重做的操作" in body["detail"]


# ---------------------------------------------------------------------------
#  Error path tests for routes_closure.py
# ---------------------------------------------------------------------------


async def test_accept_recommendation_not_found(client):
    response = await client.post(
        "/api/runs/999999/recommendations/KR-999/accept",
    )
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


async def test_ignore_recommendation_not_found(client):
    response = await client.post(
        "/api/runs/999999/recommendations/KR-999/ignore",
        json={"reason": "test"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


async def test_resolve_action_not_found(client):
    response = await client.post(
        "/api/runs/999999/actions/ACT-999/resolve",
        json={},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


async def test_resolve_change_impact_not_found(client):
    response = await client.post(
        "/api/runs/999999/change-impacts/CI-999/resolve",
        json={"status": "已处理"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


async def test_closure_tasks_not_found(client):
    response = await client.get("/api/runs/999999/closure-tasks")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


async def test_resolve_closure_tasks_by_type_not_found(client):
    response = await client.post(
        "/api/runs/999999/closure-tasks/resolve-by-type",
        json={"task_type": "drawing_review"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


async def test_resolve_closure_task_not_found(client):
    response = await client.post(
        "/api/runs/999999/closure-tasks/TASK-999/resolve",
        json={},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


async def test_apply_linkage_sync_not_found(client):
    response = await client.post(
        "/api/runs/999999/linkage/apply-sync",
        json={"apply_all": True},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
