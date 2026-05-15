from minos_desktop.app_state import ChainStageStates, StageConfirmState
from minos_desktop.chain_state import invalidate_chain_after_patch


def test_process_flow_patch_invalidates_pfmea_and_cp():
    result = {
        "process_flow": {"steps": [{"process_step_id": "P10"}]},
        "pfmea": {"rows": [{"pfmea_id": "F1", "process_step_id": "P10"}]},
        "control_plan": {"rows": [{"control_plan_id": "C1", "pfmea_id": "F1"}]},
    }
    stages = ChainStageStates(
        pfd=StageConfirmState(status="confirmed", row_count=1),
        pfmea=StageConfirmState(status="confirmed", row_count=1),
        cp=StageConfirmState(status="confirmed", row_count=1),
        pipeline_mode="chain",
    )
    patch = {
        "edit_patch_version": "minos-core.edit_patch.v1",
        "items": [
            {
                "action": "update",
                "table": "process_flow",
                "target_id": "P10",
                "changes": {"operation": "更新工序"},
            }
        ],
    }

    updated, updated_stages = invalidate_chain_after_patch(result, patch, stages)

    assert updated["pfmea"] == {"rows": []}
    assert updated["control_plan"] == {"rows": []}
    assert updated["metadata"]["chain_invalidated_stages"] == ["pfmea", "control_plan"]
    assert updated_stages.pfd.status == "generated"
    assert updated_stages.pfmea.status == "not_started"
    assert updated_stages.cp.status == "not_started"


def test_pfmea_patch_invalidates_cp_only():
    result = {
        "process_flow": {"steps": [{"process_step_id": "P10"}]},
        "pfmea": {"rows": [{"pfmea_id": "F1", "process_step_id": "P10"}]},
        "control_plan": {"rows": [{"control_plan_id": "C1", "pfmea_id": "F1"}]},
    }
    stages = ChainStageStates(
        pfd=StageConfirmState(status="confirmed", row_count=1),
        pfmea=StageConfirmState(status="confirmed", row_count=1),
        cp=StageConfirmState(status="confirmed", row_count=1),
        pipeline_mode="chain",
    )
    patch = {
        "edit_patch_version": "minos-core.edit_patch.v1",
        "items": [
            {
                "action": "update",
                "table": "pfmea",
                "target_id": "F1",
                "changes": {"failure_mode": "孔位偏差"},
            }
        ],
    }

    updated, updated_stages = invalidate_chain_after_patch(result, patch, stages)

    assert updated["pfmea"]["rows"] == [{"pfmea_id": "F1", "process_step_id": "P10"}]
    assert updated["control_plan"] == {"rows": []}
    assert updated["metadata"]["chain_invalidated_stages"] == ["control_plan"]
    assert updated_stages.pfd.status == "confirmed"
    assert updated_stages.pfmea.status == "generated"
    assert updated_stages.cp.status == "not_started"
