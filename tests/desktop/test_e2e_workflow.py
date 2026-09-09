"""End-to-end integration tests for desktop workflow.

Tests the complete workflow from project creation through export:
1. Create desktop app with temp DB
2. Create project via API
3. Upload drawing
4. Run analysis
5. Review draft
6. Export results
7. Verify output files exist
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from minos_desktop.api.app import create_app
from minos_desktop.app_state import ChainStageStates, DesktopRunState, StageConfirmState

pytestmark = pytest.mark.asyncio


def _create_mock_drawing(tmp_path: Path) -> Path:
    """Create a mock PDF drawing file for testing."""
    drawing_path = tmp_path / "test_drawing.pdf"
    drawing_path.write_bytes(b"%PDF-1.4\n%Mock PDF content for testing\n%%EOF")
    return drawing_path


def _create_fake_analysis_result() -> dict:
    """Create a fake three-table generation result for testing."""
    return {
        "document_type": "three_table_generation_result",
        "status": "needs_review",
        "process_flow": {
            "steps": [
                {
                    "process_step_id": "P10",
                    "operation": "来料检验",
                    "equipment": "检验台",
                    "review_status": "AI建议确认",
                    "needs_confirmation": True,
                    "confidence": 0.91,
                    "evidence_refs": ["EV-P10"],
                },
                {
                    "process_step_id": "P20",
                    "operation": "装配",
                    "equipment": "装配线",
                    "review_status": "AI建议确认",
                    "needs_confirmation": True,
                    "confidence": 0.88,
                    "evidence_refs": ["EV-P20"],
                },
            ]
        },
        "pfmea": {
            "rows": [
                {
                    "pfmea_id": "F10",
                    "process_step_id": "P10",
                    "failure_mode": "尺寸超差",
                    "severity": 8,
                    "occurrence": 3,
                    "detection": 2,
                    "rpn": 48,
                    "needs_confirmation": False,
                }
            ]
        },
        "control_plan": {
            "rows": [
                {
                    "control_plan_id": "CP10",
                    "process_step_id": "P10",
                    "control_item": "尺寸",
                    "measurement_method": "卡尺",
                    "sample_size": "5",
                    "frequency": "每批",
                    "needs_confirmation": False,
                }
            ]
        },
        "linkage_report": {
            "sync_suggestions": [
                {
                    "suggestion_id": "SYNC-PFD-P20-PFMEA",
                    "source": "process_flow:P20",
                    "target_table": "pfmea",
                    "suggested_action": "add",
                    "suggested_fields": {"process_step_id": "P20"},
                }
            ]
        },
        "metadata": {
            "knowledge_recommendations": [
                {
                    "recommendation_id": "KR-1",
                    "status": "待确认",
                    "description": "建议添加防错措施",
                }
            ],
            "change_impacts": [
                {
                    "item_id": "CI-1",
                    "status": "待同步",
                    "description": "工艺流程变更",
                }
            ],
        },
        "manual_review": {
            "required": True,
            "items": [
                {
                    "item_id": "MR-1",
                    "table": "process_flow",
                    "row_id": "P10",
                    "reason": "需要确认设备信息",
                }
            ],
        },
        "exports": {},
        "manifest": {"run_id": "test-run-e2e", "path": "manifest.json"},
    }


@pytest.fixture
async def e2e_client(tmp_path, monkeypatch):
    """Create a test client with mocked AI pipeline for E2E testing."""
    db_path = tmp_path / "e2e_desktop.sqlite3"
    output_dir = tmp_path / "e2e_output"
    output_dir.mkdir()

    # Mock the token manager to bypass authentication
    class MockTokenManager:
        def get_or_create_token(self):
            return "test-token"

    from minos_desktop.api import auth
    monkeypatch.setattr(auth, "_token_manager", MockTokenManager())

    app = create_app(db_path=db_path, output_dir=output_dir)

    # Mock the chain run to avoid real AI calls
    def fake_start_chain_run(db_path, project_id):
        from minos_desktop.services import DesktopRunService

        project_output = output_dir / f"project-{project_id}"
        project_output.mkdir(exist_ok=True)

        result = _create_fake_analysis_result()
        chain_stages = ChainStageStates(
            pfd=StageConfirmState(status="generated", row_count=2, pending_count=2),
            pfmea=StageConfirmState(status="not_started", row_count=0, pending_count=0),
            cp=StageConfirmState(status="not_started", row_count=0, pending_count=0),
            pipeline_mode="chain",
        )
        state = DesktopRunState(
            status="needs_review",
            status_display="待人工确认",
            blocked_stage="",
            exports=(),
            manifest_path="",
            manifest_run_id="test-run-e2e",
            manual_review_required=True,
            manual_review_count=1,
            manual_review_raw_count=1,
            manual_review_items=tuple(result["manual_review"]["items"]),
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

    # Mock the PFMEA generation for chain workflow
    def fake_generate_pfmea(_drawing_analysis, confirmed_pfd, model=None, on_progress=None):
        return {
            "rows": [
                {
                    "pfmea_id": "F10",
                    "process_step_id": "P10",
                    "failure_mode": "尺寸超差",
                    "severity": 8,
                    "occurrence": 3,
                    "detection": 2,
                    "rpn": 48,
                    "needs_confirmation": False,
                },
                {
                    "pfmea_id": "F20",
                    "process_step_id": "P20",
                    "failure_mode": "装配错误",
                    "severity": 7,
                    "occurrence": 4,
                    "detection": 3,
                    "rpn": 84,
                    "needs_confirmation": False,
                },
            ]
        }

    # Mock the Control Plan generation for chain workflow
    def fake_generate_cp(_drawing_analysis, confirmed_pfd, confirmed_pfmea, model=None, on_progress=None):
        return {
            "rows": [
                {
                    "control_plan_id": "CP10",
                    "process_step_id": "P10",
                    "control_item": "尺寸",
                    "measurement_method": "卡尺",
                    "sample_size": "5",
                    "frequency": "每批",
                    "needs_confirmation": False,
                },
                {
                    "control_plan_id": "CP20",
                    "process_step_id": "P20",
                    "control_item": "装配质量",
                    "measurement_method": "目视检查",
                    "sample_size": "全检",
                    "frequency": "每件",
                    "needs_confirmation": False,
                },
            ]
        }

    from minos_desktop.api import jobs

    monkeypatch.setattr(jobs, "start_chain_run", fake_start_chain_run)
    monkeypatch.setattr(
        "minos_core.pipeline_chain.generate_pfmea_from_confirmed_pfd",
        fake_generate_pfmea,
    )
    monkeypatch.setattr(
        "minos_core.pipeline_chain.generate_cp_from_confirmed_pfmea",
        fake_generate_cp,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer test-token"},
    ) as client:
        yield client, tmp_path, output_dir


async def test_complete_desktop_workflow_e2e(e2e_client):
    """Test complete desktop workflow from project creation to export.

    This test covers:
    1. Create project with drawing
    2. Start analysis run
    3. Review and edit draft results
    4. Confirm PFD stage (triggers PFMEA generation)
    5. Confirm PFMEA stage (triggers CP generation)
    6. Confirm CP stage
    7. Export final results
    8. Verify all output files exist
    """
    client, tmp_path, output_dir = e2e_client

    # Step 1: Create a mock drawing file
    drawing_path = _create_mock_drawing(tmp_path)
    assert drawing_path.exists()

    # Step 2: Create project via API
    project_response = await client.post(
        "/api/projects",
        json={
            "project_name": "E2E测试项目",
            "drawing_path": str(drawing_path),
            "context": {
                "part_no": "E2E-001",
                "part_name": "测试零件",
                "customer": "测试客户",
            },
        },
    )
    assert project_response.status_code == 201
    project = project_response.json()
    assert project["project_name"] == "E2E测试项目"
    assert project["context"]["part_no"] == "E2E-001"
    project_id = project["id"]

    # Step 3: Verify project appears in recent projects
    recent_projects = await client.get("/api/projects/recent")
    assert recent_projects.status_code == 200
    assert len(recent_projects.json()) == 1
    assert recent_projects.json()[0]["project_name"] == "E2E测试项目"

    # Step 4: Start analysis run
    run_response = await client.post(f"/api/projects/{project_id}/runs")
    assert run_response.status_code == 201
    run = run_response.json()
    assert run["project_id"] == project_id
    assert run["status"] == "needs_review"
    assert run["pipeline_mode"] == "chain"
    assert run["manual_review_required"] is True
    assert run["chain_stages"]["pfd"]["status"] == "generated"
    assert run["chain_stages"]["pfd"]["row_count"] == 2
    run_id = run["id"]

    # Step 5: Review draft - verify process flow data
    pfd_table = await client.get(f"/api/runs/{run_id}/tables/process_flow")
    assert pfd_table.status_code == 200
    pfd_data = pfd_table.json()
    assert len(pfd_data["rows"]) == 2
    assert pfd_data["rows"][0]["process_step_id"] == "P10"
    assert pfd_data["rows"][0]["operation"] == "来料检验"
    assert pfd_data["rows"][1]["process_step_id"] == "P20"

    # Step 6: Edit draft - update operation name
    edit_response = await client.patch(
        f"/api/runs/{run_id}/edit-patch",
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
    edited_run = edit_response.json()
    assert edited_run["current_result"]["process_flow"]["steps"][0]["operation"] == "来料检验-已复核"

    # Step 7: Confirm PFD stage (triggers PFMEA generation)
    pfd_confirm_response = await client.post(
        f"/api/runs/{run_id}/chain/pfd-confirm",
        json={
            "confirmed_by": "qe",
            "edit_patch": {
                "items": [
                    {
                        "action": "update",
                        "table": "process_flow",
                        "row_id": "P20",
                        "changes": {"operation": "装配-已确认"},
                    }
                ]
            },
        },
    )
    assert pfd_confirm_response.status_code == 200
    pfd_confirmed = pfd_confirm_response.json()
    assert pfd_confirmed["chain_stages"]["pfd"]["status"] == "confirmed"
    # PFMEA generation is async, so it may be "running" or "generated"
    assert pfd_confirmed["chain_stages"]["pfmea"]["status"] in ["running", "generated"]
    assert pfd_confirmed["current_result"]["process_flow"]["steps"][1]["operation"] == "装配-已确认"
    assert pfd_confirmed["current_result"]["process_flow"]["steps"][1]["confirmed_by"] == "qe"

    # Step 8: Wait for PFMEA generation to complete and verify
    # In real scenario, the background job completes; here we fetch the updated run
    updated_run = await client.get(f"/api/runs/{run_id}")
    assert updated_run.status_code == 200
    run_data = updated_run.json()
    assert run_data["chain_stages"]["pfmea"]["status"] == "generated"

    pfmea_table = await client.get(f"/api/runs/{run_id}/tables/pfmea")
    assert pfmea_table.status_code == 200
    pfmea_data = pfmea_table.json()
    assert len(pfmea_data["rows"]) == 2
    assert pfmea_data["rows"][0]["pfmea_id"] == "F10"
    assert pfmea_data["rows"][1]["pfmea_id"] == "F20"

    # Step 9: Confirm PFMEA stage (triggers CP generation)
    pfmea_confirm_response = await client.post(
        f"/api/runs/{run_id}/chain/pfmea-confirm",
        json={"confirmed_by": "qe"},
    )
    assert pfmea_confirm_response.status_code == 200
    pfmea_confirmed = pfmea_confirm_response.json()
    assert pfmea_confirmed["chain_stages"]["pfmea"]["status"] == "confirmed"
    # CP generation is async, so it may be "running" or "generated"
    assert pfmea_confirmed["chain_stages"]["cp"]["status"] in ["running", "generated"]

    # Step 10: Wait for Control Plan generation to complete and verify
    updated_run2 = await client.get(f"/api/runs/{run_id}")
    assert updated_run2.status_code == 200
    run_data2 = updated_run2.json()
    assert run_data2["chain_stages"]["cp"]["status"] == "generated"

    cp_table = await client.get(f"/api/runs/{run_id}/tables/control_plan")
    assert cp_table.status_code == 200
    cp_data = cp_table.json()
    assert len(cp_data["rows"]) == 2
    assert cp_data["rows"][0]["control_plan_id"] == "CP10"
    assert cp_data["rows"][1]["control_plan_id"] == "CP20"

    # Step 11: Confirm CP stage (completes the chain)
    cp_confirm_response = await client.post(
        f"/api/runs/{run_id}/chain/cp-confirm",
        json={"confirmed_by": "qe"},
    )
    assert cp_confirm_response.status_code == 200
    cp_confirmed = cp_confirm_response.json()
    assert cp_confirmed["chain_stages"]["cp"]["status"] == "confirmed"

    # Step 12: Export results
    export_dir = output_dir / f"project-{project_id}" / "exports"
    export_response = await client.post(
        f"/api/runs/{run_id}/exports",
        json={
            "output_dir": str(export_dir),
            "export_mode": "final",
        },
    )
    assert export_response.status_code == 201
    export_result = export_response.json()
    assert export_result["export_mode"] == "final"
    assert export_result["run_id"] == run_id

    # Step 13: Verify output files exist
    assert export_dir.exists()
    exported_files = list(export_dir.glob("*"))
    assert len(exported_files) > 0, "Export directory should contain files"

    # Step 14: Verify run appears in recent runs
    recent_runs = await client.get("/api/runs/recent")
    assert recent_runs.status_code == 200
    assert len(recent_runs.json()) == 1
    assert recent_runs.json()[0]["id"] == run_id

    # Step 15: Test restore functionality
    restore_response = await client.post(f"/api/runs/{run_id}/restore")
    assert restore_response.status_code == 200
    restored_run = restore_response.json()
    assert restored_run["id"] == run_id
    assert restored_run["status"] == cp_confirmed["status"]


async def test_workflow_with_linkage_sync(e2e_client):
    """Test workflow including linkage synchronization."""
    client, tmp_path, output_dir = e2e_client

    # Create project and run
    drawing_path = _create_mock_drawing(tmp_path)
    project = (
        await client.post(
            "/api/projects",
            json={
                "project_name": "联动同步测试",
                "drawing_path": str(drawing_path),
            },
        )
    ).json()
    run = (await client.post(f"/api/projects/{project['id']}/runs")).json()

    # Apply linkage sync
    sync_response = await client.post(
        f"/api/runs/{run['id']}/linkage/apply-sync",
        json={"apply_all": True},
    )
    assert sync_response.status_code == 200
    synced = sync_response.json()

    # Verify linkage suggestions were processed
    assert "linkage_report" in synced["current_result"]


async def test_workflow_with_knowledge_recommendations(e2e_client):
    """Test workflow including knowledge recommendation handling."""
    client, tmp_path, output_dir = e2e_client

    # Create project and run
    drawing_path = _create_mock_drawing(tmp_path)
    project = (
        await client.post(
            "/api/projects",
            json={
                "project_name": "知识推荐测试",
                "drawing_path": str(drawing_path),
            },
        )
    ).json()
    run = (await client.post(f"/api/projects/{project['id']}/runs")).json()

    # Ignore a knowledge recommendation
    ignore_response = await client.post(
        f"/api/runs/{run['id']}/recommendations/KR-1/ignore",
        json={"reason": "已有等效控制措施"},
    )
    assert ignore_response.status_code == 200
    ignored = ignore_response.json()
    kr = ignored["current_result"]["metadata"]["knowledge_recommendations"][0]
    assert kr["status"] == "已忽略"
    assert kr["recommendation_id"] == "KR-1"


async def test_workflow_with_change_impact_resolution(e2e_client):
    """Test workflow including change impact resolution."""
    client, tmp_path, output_dir = e2e_client

    # Create project and run
    drawing_path = _create_mock_drawing(tmp_path)
    project = (
        await client.post(
            "/api/projects",
            json={
                "project_name": "变更影响测试",
                "drawing_path": str(drawing_path),
            },
        )
    ).json()
    run = (await client.post(f"/api/projects/{project['id']}/runs")).json()

    # Resolve a change impact
    resolve_response = await client.post(
        f"/api/runs/{run['id']}/change-impacts/CI-1/resolve",
        json={"status": "已处理"},
    )
    assert resolve_response.status_code == 200
    resolved = resolve_response.json()
    ci = resolved["current_result"]["metadata"]["change_impacts"][0]
    assert ci["status"] == "已处理"
    assert ci["item_id"] == "CI-1"


async def test_workflow_error_handling(e2e_client):
    """Test error handling in workflow."""
    client, tmp_path, output_dir = e2e_client

    # Test 404 for non-existent run
    response = await client.get("/api/runs/99999")
    assert response.status_code == 404
    error = response.json()
    assert error["code"] == "NOT_FOUND"
    assert "failure_message" in error

    # Note: Project endpoint doesn't properly handle 404 yet (returns 500 with KeyError)
    # This is a known issue that should be fixed in the routes layer
