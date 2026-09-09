import os
import tempfile
import unittest
from unittest.mock import patch

from minos_desktop.app_state import (
    ChainStageStates,
    DesktopRunState,
    StageConfirmState,
    desktop_run_state_from_result,
)
from minos_desktop.services import (
    DesktopRunService,
)
from minos_desktop.table_editor import (
    ROW_STATUS_COLUMN,
    build_edit_patch,
    three_table_to_table_model,
)


class TestRunServiceIntegration(unittest.TestCase):
    def test_pfd_confirm_returns_immediately_and_pfmea_generation_runs_separately(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            service = DesktopRunService(db_path)
            chain_stages = ChainStageStates(
                pfd=StageConfirmState(status="generated", row_count=1, pending_count=1),
                pipeline_mode="chain",
            )
            run = service.save_chain_run(
                None,
                DesktopRunState(
                    status="needs_review",
                    status_display="待人工确认",
                    blocked_stage="",
                    exports=(),
                    manifest_path="",
                    manifest_run_id="",
                    manual_review_required=False,
                    manual_review_count=0,
                    manual_review_raw_count=0,
                    manual_review_items=(),
                    chain_stages=chain_stages,
                ),
                tmpdir,
                {
                    "document_type": "three_table_generation_result",
                    "status": "needs_review",
                    "drawing_analysis": {"drawing_identity": {"part_name": "尾门铰链"}},
                    "process_flow": {
                        "steps": [
                            {
                                "process_step_id": "P10",
                                "operation": "来料检验",
                                "needs_confirmation": True,
                            }
                        ]
                    },
                    "pfmea": {"rows": []},
                    "control_plan": {"rows": []},
                    "manual_review": {"required": False, "items": []},
                },
                "",
                chain_stages,
            )

            with patch(
                "minos_core.pipeline_chain.generate_pfmea_from_confirmed_pfd",
                side_effect=AssertionError("PFMEA generation must not run inside confirm"),
            ):
                confirmed = service.confirm_pfd_stage(run.id, confirmed_by="qe")

            self.assertEqual(confirmed.state.chain_stages.pfd.status, "confirmed")
            self.assertEqual(confirmed.state.chain_stages.pfmea.status, "running")
            self.assertEqual(confirmed.current_result["pfmea"], {"rows": []})
            self.assertEqual(
                confirmed.current_result["process_flow"]["steps"][0]["review_status"],
                "已确认",
            )

            def fake_generate_pfmea(_drawing_analysis, confirmed_pfd, model=None, on_progress=None):
                return {
                    "rows": [
                        {
                            "pfmea_id": "F1",
                            "process_step_id": "P10",
                            "operation_seen_by_pfmea": confirmed_pfd["steps"][0]["operation"],
                        }
                    ]
                }

            with patch(
                "minos_core.pipeline_chain.generate_pfmea_from_confirmed_pfd",
                fake_generate_pfmea,
            ):
                generated = service.generate_pfmea_for_confirmed_pfd(run.id)

            self.assertEqual(generated.state.chain_stages.pfmea.status, "generated")
            self.assertEqual(generated.current_result["pfmea"]["rows"][0]["pfmea_id"], "F1")


    def test_legacy_pfmea_sync_placeholders_are_hidden_when_generation_failed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            service = DesktopRunService(db_path)
            chain_stages = ChainStageStates(
                pfd=StageConfirmState(status="confirmed", row_count=1),
                pfmea=StageConfirmState(status="generated", row_count=1, pending_count=1),
                pipeline_mode="chain",
            )
            raw_result = {
                "document_type": "three_table_generation_result",
                "status": "needs_review",
                "process_flow": {
                    "steps": [
                        {
                            "process_step_id": "P10",
                            "operation": "来料检验",
                            "needs_confirmation": False,
                        }
                    ]
                },
                "pfmea": {"rows": []},
                "control_plan": {"rows": []},
                "manual_review": {"required": False, "items": []},
            }
            current_result = {
                **raw_result,
                "pfmea": {
                    "rows": [
                        {
                            "pfmea_id": "PFMEA-SYNC-P10",
                            "process_step_id": "P10",
                            "failure_mode": "待工程人员填写失效模式",
                            "review_status": "联动新增",
                            "needs_confirmation": True,
                        }
                    ]
                },
            }
            legacy_envelope = {
                "_desktop_storage_version": 1,
                "raw_result": raw_result,
                "current_result": current_result,
                "edit_patch": {"edit_patch_version": "minos-core.edit_patch.v1", "items": []},
                "chain_stages": chain_stages.to_dict(),
            }
            run = service.save_run(
                None,
                DesktopRunState(
                    status="needs_review",
                    status_display="待人工确认",
                    blocked_stage="",
                    exports=(),
                    manifest_path="",
                    manifest_run_id="",
                    manual_review_required=False,
                    manual_review_count=0,
                    manual_review_raw_count=0,
                    manual_review_items=(),
                    chain_stages=chain_stages,
                ),
                tmpdir,
                legacy_envelope,
                "原始错误：LLM Responses HTTP 504 Gateway Time-out",
            )
            reloaded = service.get_run(run.id)

        self.assertEqual(reloaded.current_result["pfmea"]["rows"], [])
        self.assertEqual(reloaded.state.status, "failed")
        self.assertEqual(reloaded.state.blocked_stage, "pfmea")
        self.assertEqual(reloaded.state.chain_stages.pfmea.status, "failed")
        self.assertEqual(reloaded.state.chain_stages.pfmea.row_count, 0)
        self.assertEqual(reloaded.state.chain_stages.pfmea.pending_count, 0)
        self.assertEqual(reloaded.current_result["status"], "failed")
        self.assertEqual(reloaded.current_result["blocked_stage"], "pfmea")
        self.assertIn("504 Gateway Time-out", reloaded.failure_message)


    def test_process_flow_edit_invalidates_downstream_chain_stages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            chain_stages = ChainStageStates(
                pfd=StageConfirmState(status="confirmed", row_count=1),
                pfmea=StageConfirmState(status="confirmed", row_count=1),
                cp=StageConfirmState(status="generated", row_count=1),
                pipeline_mode="chain",
            )
            run = run_service.save_chain_run(
                None,
                desktop_run_state_from_result(
                    {
                        "status": "needs_review",
                        "manual_review": {"required": False, "items": []},
                    }
                ),
                tmpdir,
                {
                    "document_type": "three_table_generation_result",
                    "status": "needs_review",
                    "process_flow": {
                        "steps": [
                            {
                                "process_step_id": "P10",
                                "operation": "来料检验",
                                "needs_confirmation": False,
                            }
                        ]
                    },
                    "pfmea": {"rows": [{"pfmea_id": "F1", "process_step_id": "P10"}]},
                    "control_plan": {"rows": [{"control_plan_id": "C1", "process_step_id": "P10"}]},
                    "manual_review": {"required": False, "items": []},
                },
                "",
                chain_stages,
            )
            updated = run_service.apply_edit_patch_to_run(
                run.id,
                build_edit_patch(
                    [
                        {
                            "action": "update",
                            "table": "process_flow",
                            "target_id": "P10",
                            "changes": {"operation": "更新后的工序"},
                        }
                    ]
                ),
            )

        self.assertEqual(updated.current_result["pfmea"], {"rows": []})
        self.assertEqual(updated.current_result["control_plan"], {"rows": []})
        self.assertEqual(updated.state.chain_stages.pfd.status, "generated")
        self.assertEqual(updated.state.chain_stages.pfmea.status, "not_started")
        self.assertEqual(updated.state.chain_stages.cp.status, "not_started")
        self.assertIn(
            "pfmea",
            updated.current_result["metadata"]["chain_invalidated_stages"],
        )
        self.assertIn(
            "control_plan",
            updated.current_result["metadata"]["chain_invalidated_stages"],
        )


    def test_pfmea_edit_invalidates_control_plan_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            chain_stages = ChainStageStates(
                pfd=StageConfirmState(status="confirmed", row_count=1),
                pfmea=StageConfirmState(status="confirmed", row_count=1),
                cp=StageConfirmState(status="confirmed", row_count=1),
                pipeline_mode="chain",
            )
            run = run_service.save_chain_run(
                None,
                desktop_run_state_from_result(
                    {
                        "status": "needs_review",
                        "manual_review": {"required": False, "items": []},
                    }
                ),
                tmpdir,
                {
                    "document_type": "three_table_generation_result",
                    "status": "needs_review",
                    "process_flow": {"steps": [{"process_step_id": "P10"}]},
                    "pfmea": {
                        "rows": [
                            {
                                "pfmea_id": "F1",
                                "process_step_id": "P10",
                                "failure_mode": "尺寸偏差",
                            }
                        ]
                    },
                    "control_plan": {"rows": [{"control_plan_id": "C1", "process_step_id": "P10"}]},
                    "manual_review": {"required": False, "items": []},
                },
                "",
                chain_stages,
            )
            updated = run_service.apply_edit_patch_to_run(
                run.id,
                build_edit_patch(
                    [
                        {
                            "action": "update",
                            "table": "pfmea",
                            "target_id": "F1",
                            "changes": {"failure_mode": "孔位偏差"},
                        }
                    ]
                ),
            )

        self.assertEqual(updated.current_result["control_plan"], {"rows": []})
        self.assertEqual(updated.state.chain_stages.pfd.status, "confirmed")
        self.assertEqual(updated.state.chain_stages.pfmea.status, "generated")
        self.assertEqual(updated.state.chain_stages.cp.status, "not_started")
        self.assertEqual(
            updated.current_result["metadata"]["chain_invalidated_stages"],
            ["control_plan"],
        )


    def test_confirm_pfd_marks_rows_confirmed_and_generates_pfmea(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            run = run_service.save_chain_run(
                None,
                desktop_run_state_from_result(
                    {
                        "status": "needs_review",
                        "manual_review": {"required": False, "items": []},
                    }
                ),
                tmpdir,
                {
                    "document_type": "three_table_generation_result",
                    "status": "needs_review",
                    "drawing_analysis": {},
                    "process_flow": {
                        "steps": [
                            {
                                "process_step_id": "P10",
                                "operation": "来料检验",
                                "needs_confirmation": True,
                                "ai_inferred": True,
                            }
                        ]
                    },
                    "pfmea": {"rows": []},
                    "control_plan": {"rows": []},
                    "manual_review": {"required": False, "items": []},
                },
                "",
                ChainStageStates(
                    pfd=StageConfirmState(status="generated", row_count=1, pending_count=1),
                    pipeline_mode="chain",
                ),
            )
            updated = run_service.confirm_pfd_stage(run.id, confirmed_by="qe")

        step = updated.current_result["process_flow"]["steps"][0]
        self.assertFalse(step["needs_confirmation"])
        self.assertFalse(step["ai_inferred"])
        self.assertEqual(step["review_status"], "已确认")
        self.assertEqual(step["confirmed_by"], "qe")
        self.assertEqual(updated.state.chain_stages.pfd.status, "confirmed")
        self.assertEqual(updated.state.chain_stages.pfmea.status, "running")
        self.assertEqual(updated.current_result["pfmea"], {"rows": []})


    def test_confirm_pfd_applies_edit_patch_before_generating_pfmea(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            run = run_service.save_chain_run(
                None,
                desktop_run_state_from_result(
                    {
                        "status": "needs_review",
                        "manual_review": {"required": False, "items": []},
                    }
                ),
                tmpdir,
                {
                    "document_type": "three_table_generation_result",
                    "status": "needs_review",
                    "drawing_analysis": {},
                    "process_flow": {
                        "steps": [
                            {
                                "process_step_id": "P10",
                                "operation": "原始工序",
                                "needs_confirmation": True,
                                "ai_inferred": True,
                            }
                        ]
                    },
                    "pfmea": {"rows": []},
                    "control_plan": {"rows": []},
                    "manual_review": {"required": False, "items": []},
                },
                "",
                ChainStageStates(
                    pfd=StageConfirmState(status="generated", row_count=1, pending_count=1),
                    pipeline_mode="chain",
                ),
            )
            updated = run_service.confirm_pfd_stage(
                run.id,
                confirmed_by="qe",
                edit_patch=build_edit_patch(
                    [
                        {
                            "action": "update",
                            "table": "process_flow",
                            "target_id": "P10",
                            "changes": {"operation": "修改后的工序"},
                        }
                    ]
                ),
            )

        step = updated.current_result["process_flow"]["steps"][0]
        self.assertEqual(step["operation"], "修改后的工序")
        self.assertEqual(step["review_status"], "已确认")
        self.assertEqual(step["confirmed_by"], "qe")
        self.assertEqual(updated.state.chain_stages.pfd.status, "confirmed")
        self.assertEqual(updated.state.chain_stages.pfmea.status, "running")
        self.assertEqual(updated.current_result["pfmea"], {"rows": []})


    def test_confirm_pfd_with_edit_patch_drops_stale_control_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            run = run_service.save_chain_run(
                None,
                desktop_run_state_from_result(
                    {
                        "status": "needs_review",
                        "manual_review": {"required": False, "items": []},
                    }
                ),
                tmpdir,
                {
                    "document_type": "three_table_generation_result",
                    "status": "needs_review",
                    "drawing_analysis": {},
                    "process_flow": {
                        "steps": [
                            {
                                "process_step_id": "P10",
                                "operation": "原始工序",
                                "needs_confirmation": True,
                                "ai_inferred": True,
                            }
                        ]
                    },
                    "pfmea": {
                        "rows": [
                            {
                                "pfmea_id": "OLD-F1",
                                "process_step_id": "P10",
                                "failure_mode": "旧失效模式",
                            }
                        ]
                    },
                    "control_plan": {
                        "rows": [
                            {
                                "control_plan_id": "OLD-C1",
                                "pfmea_id": "OLD-F1",
                                "control_method": "旧控制方法",
                            }
                        ]
                    },
                    "manual_review": {"required": False, "items": []},
                },
                "",
                ChainStageStates(
                    pfd=StageConfirmState(status="generated", row_count=1, pending_count=1),
                    pfmea=StageConfirmState(status="confirmed", row_count=1),
                    cp=StageConfirmState(status="confirmed", row_count=1),
                    pipeline_mode="chain",
                ),
            )
            updated = run_service.confirm_pfd_stage(
                run.id,
                confirmed_by="qe",
                edit_patch=build_edit_patch(
                    [
                        {
                            "action": "update",
                            "table": "process_flow",
                            "target_id": "P10",
                            "changes": {"operation": "修改后的工序"},
                        }
                    ]
                ),
            )

        self.assertEqual(updated.current_result["pfmea"], {"rows": []})
        self.assertEqual(updated.current_result["control_plan"], {"rows": []})
        self.assertEqual(updated.state.chain_stages.pfmea.status, "running")
        self.assertEqual(updated.state.chain_stages.cp.status, "not_started")


    def test_regenerate_pfmea_clears_previous_failed_run_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            run = run_service.save_chain_run(
                None,
                DesktopRunState(
                    status="failed",
                    status_display="失败",
                    blocked_stage="pfmea",
                    exports=(),
                    manifest_path="",
                    manifest_run_id="",
                    manual_review_required=False,
                    manual_review_count=0,
                    manual_review_raw_count=0,
                    chain_stages=ChainStageStates(
                        pfd=StageConfirmState(status="confirmed", row_count=1),
                        pfmea=StageConfirmState(status="failed"),
                        pipeline_mode="chain",
                    ),
                ),
                tmpdir,
                {
                    "document_type": "three_table_generation_result",
                    "status": "failed",
                    "blocked_stage": "pfmea",
                    "drawing_analysis": {},
                    "process_flow": {"steps": [{"process_step_id": "P10"}]},
                    "pfmea": {"rows": []},
                    "control_plan": {"rows": []},
                    "manual_review": {"required": False, "items": []},
                },
                "原始错误：PFMEA failed",
                ChainStageStates(
                    pfd=StageConfirmState(status="confirmed", row_count=1),
                    pfmea=StageConfirmState(status="failed"),
                    pipeline_mode="chain",
                ),
            )
            with patch(
                "minos_core.pipeline_chain.generate_pfmea_from_confirmed_pfd",
                return_value={
                    "rows": [
                        {
                            "pfmea_id": "F1",
                            "process_step_id": "P10",
                            "needs_confirmation": False,
                        }
                    ]
                },
            ):
                updated = run_service.regenerate_pfmea_stage(run.id)

        self.assertEqual(updated.state.status, "needs_review")
        self.assertEqual(updated.failure_message, "")
        self.assertEqual(updated.state.chain_stages.pfmea.status, "generated")
        self.assertEqual(updated.current_result["blocked_stage"], None)


    def test_apply_edit_patch_to_run_round_trips_current_result_and_patch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            run = run_service.save_result(
                None,
                {
                    "status": "needs_review",
                    "process_flow": {
                        "steps": [
                            {
                                "process_step_id": "P10",
                                "operation": "Before",
                                "needs_confirmation": True,
                            }
                        ]
                    },
                    "pfmea": {"rows": []},
                    "control_plan": {"rows": []},
                    "manual_review": {"required": True, "items": []},
                },
                tmpdir,
            )

            updated = run_service.apply_edit_patch_to_run(
                run.id,
                {
                    "items": [
                        {
                            "action": "update",
                            "table": "process_flow",
                            "target": "process_step:P10",
                            "row_id": "P10",
                            "changes": {"operation": "After"},
                        },
                        {
                            "action": "confirm",
                            "table": "process_flow",
                            "target": "process_step:P10",
                            "row_id": "P10",
                        },
                    ]
                },
            )
            reloaded = DesktopRunService(db_path).get_run(run.id)

        self.assertEqual(
            updated.raw_result["process_flow"]["steps"][0]["operation"],
            "After",
        )
        self.assertFalse(updated.raw_result["process_flow"]["steps"][0]["needs_confirmation"])
        self.assertEqual(
            reloaded.current_result["process_flow"]["steps"][0]["operation"],
            "After",
        )
        self.assertEqual(
            reloaded.original_result["process_flow"]["steps"][0]["operation"],
            "Before",
        )
        self.assertEqual(len(reloaded.edit_patch["items"]), 2)


    def test_automation_batch_confirm_waits_until_cp_confirmed_and_after_control_plan_review_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            chain_stages = ChainStageStates(
                pfd=StageConfirmState(status="confirmed", row_count=1),
                pfmea=StageConfirmState(status="confirmed", row_count=1),
                cp=StageConfirmState(status="generated", row_count=1, pending_count=1),
                pipeline_mode="chain",
            )
            run = run_service.save_chain_run(
                None,
                desktop_run_state_from_result(
                    {
                        "document_type": "three_table_generation_result",
                        "status": "needs_review",
                        "process_flow": {"steps": []},
                        "pfmea": {"rows": []},
                        "control_plan": {"rows": []},
                        "manual_review": {"required": False, "items": []},
                    }
                ),
                tmpdir,
                {
                    "document_type": "three_table_generation_result",
                    "status": "needs_review",
                    "process_flow": {
                        "steps": [
                            {
                                "process_step_id": "P10",
                                "operation": "来料检验",
                                "review_status": "AI建议确认",
                                "needs_confirmation": False,
                                "evidence_refs": ["EV-1"],
                                "confidence": 0.95,
                            }
                        ]
                    },
                    "pfmea": {
                        "rows": [
                            {
                                "pfmea_id": "PFMEA-P10-OK",
                                "process_step_id": "P10",
                                "failure_mode": "来料错误",
                                "failure_effect": "返工",
                                "severity": 3,
                                "occurrence": 2,
                                "detection": 2,
                                "rpn": 12,
                                "action_priority": "L",
                                "review_status": "AI建议确认",
                                "needs_confirmation": False,
                                "evidence_refs": ["EV-1"],
                                "confidence": 0.95,
                            }
                        ]
                    },
                    "control_plan": {
                        "rows": [
                            {
                                "control_plan_id": "CP-P10-OK",
                                "process_step_id": "P10",
                                "pfmea_id": "PFMEA-P10-OK",
                                "control_method": "来料检验",
                                "review_status": "AI建议确认",
                                "needs_confirmation": True,
                                "evidence_refs": ["EV-1"],
                                "confidence": 0.95,
                            }
                        ]
                    },
                    "drawing_analysis": {"evidence": [{"evidence_id": "EV-1"}]},
                    "manual_review": {"required": True, "items": []},
                },
                "",
                chain_stages,
            )

            blocked = run_service.batch_confirm_automation_review(run.id)

            confirmed = run_service.confirm_cp_stage(run.id, confirmed_by="qe")
            updated = run_service.batch_confirm_automation_review(run.id)
            model = three_table_to_table_model(updated.current_result, "pfmea")

        self.assertNotIn("automation_review", blocked.current_result)
        self.assertEqual(blocked.edit_patch["items"], [])
        self.assertEqual(
            blocked.current_result["pfmea"]["rows"][0]["review_status"],
            "AI建议确认",
        )
        self.assertEqual(
            confirmed.current_result["automation_review"]["review_stage"],
            "after_control_plan",
        )
        self.assertTrue(confirmed.current_result["automation_review"]["human_decision_priority"])
        self.assertFalse(updated.current_result["pfmea"]["rows"][0]["needs_confirmation"])
        self.assertEqual(updated.current_result["pfmea"]["rows"][0]["review_status"], "已批量确认")
        self.assertEqual(model["rows"][0][ROW_STATUS_COLUMN], "已批量确认")
        self.assertEqual(
            updated.edit_patch["items"][0]["metadata"]["confirmation_mode"],
            "ai_recommended_batch",
        )

    def test_cp_confirm_materializes_quality_gate_recommendations_for_closure(self):
        from minos_core.closure_tasks import build_closure_tasks

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            chain_stages = ChainStageStates(
                pfd=StageConfirmState(status="confirmed", row_count=1),
                pfmea=StageConfirmState(status="confirmed", row_count=1),
                cp=StageConfirmState(status="generated", row_count=1),
                pipeline_mode="chain",
            )
            run = run_service.save_chain_run(
                None,
                DesktopRunState(
                    status="needs_review",
                    status_display="待人工确认",
                    blocked_stage="",
                    exports=(),
                    manifest_path="",
                    manifest_run_id="",
                    manual_review_required=False,
                    manual_review_count=0,
                    manual_review_raw_count=0,
                    manual_review_items=(),
                    chain_stages=chain_stages,
                ),
                tmpdir,
                {
                    "document_type": "three_table_generation_result",
                    "status": "needs_review",
                    "drawing_analysis": {"evidence": [{"evidence_id": "EV-1"}]},
                    "process_flow": {
                        "steps": [
                            {
                                "process_step_id": "P10",
                                "operation": "来料检验",
                                "process_function": "确认来料状态",
                                "evidence_refs": ["EV-1"],
                                "needs_confirmation": False,
                            }
                        ]
                    },
                    "pfmea": {
                        "rows": [
                            {
                                "pfmea_id": "PFMEA-P10-001",
                                "process_step_id": "P10",
                                "failure_mode": "来料错误",
                                "failure_effect": "不合格流出",
                                "failure_cause": "供方批次波动",
                                "prevention_control": "供方审核",
                                "detection_control": "来料检验",
                                "severity": 6,
                                "occurrence": 3,
                                "detection": 4,
                                "action_priority": "L",
                                "evidence_refs": ["EV-1"],
                                "needs_confirmation": False,
                            }
                        ]
                    },
                    "control_plan": {
                        "rows": [
                            {
                                "control_plan_id": "CP-P10-001",
                                "process_step_id": "P10",
                                "pfmea_id": "PFMEA-P10-001",
                                "product_characteristic": "来料状态",
                                "process_characteristic": "供方批次",
                                "specification": "按图纸",
                                "measurement_method": "来料检验",
                                "sample_size": "5件",
                                "sample_frequency": "每批",
                                "control_method": "检验记录",
                                "reaction_plan": "隔离并通知质量",
                                "evidence_refs": ["EV-1"],
                                "needs_confirmation": False,
                            }
                        ]
                    },
                    "manual_review": {"required": False, "items": []},
                },
                "",
                chain_stages,
            )
            recommendation = {
                "recommendation_id": "KR-TEST:PFMEA-P10-001",
                "target_table": "pfmea",
                "target_id": "PFMEA-P10-001",
                "reason": "检验工序建议确认检具校准状态。",
                "status": "待确认",
                "lifecycle_status": "proposed",
            }

            with patch(
                "minos_core.edit_patch.recommend_from_knowledge",
                return_value=[recommendation],
            ):
                confirmed = run_service.confirm_cp_stage(run.id, confirmed_by="qe")

        metadata = confirmed.current_result["metadata"]
        self.assertEqual(
            metadata["knowledge_recommendations"][0]["recommendation_id"],
            "KR-TEST:PFMEA-P10-001",
        )
        tasks = build_closure_tasks(confirmed.current_result)
        self.assertTrue(
            any(task.get("task_type") == "knowledge_recommendation" for task in tasks)
        )


    def test_pfd_soft_delete_reload_hides_pfmea_and_cp_rows_until_restored(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            run = run_service.save_result(
                None,
                {
                    "document_type": "three_table_generation_result",
                    "status": "needs_review",
                    "process_flow": {
                        "steps": [
                            {
                                "process_step_id": "P10",
                                "operation": "来料检验",
                                "process_function": "确认来料状态",
                                "evidence_refs": ["EV-1"],
                                "needs_confirmation": True,
                            }
                        ]
                    },
                    "pfmea": {
                        "rows": [
                            {
                                "pfmea_id": "PFMEA-P10-001",
                                "process_step_id": "P10",
                                "failure_mode": "来料错误",
                                "failure_effect": "不合格流出",
                                "severity": 6,
                                "failure_cause": "标识未确认",
                                "occurrence": 3,
                                "prevention_control": "批次隔离",
                                "detection_control": "首件确认",
                                "detection": 4,
                                "action_priority": "L",
                                "evidence_refs": ["EV-1"],
                                "needs_confirmation": True,
                            }
                        ]
                    },
                    "control_plan": {
                        "rows": [
                            {
                                "control_plan_id": "CP-P10-001",
                                "process_step_id": "P10",
                                "pfmea_id": "PFMEA-P10-001",
                                "product_process_characteristic": "来料状态",
                                "specification": "按图纸",
                                "measurement_method": "目视",
                                "sample_frequency": "每批",
                                "control_method": "来料检验",
                                "reaction_plan": "隔离",
                                "evidence_refs": ["EV-1"],
                                "needs_confirmation": True,
                            }
                        ]
                    },
                    "drawing_analysis": {"evidence": [{"evidence_id": "EV-1", "content": "fixture"}]},
                    "manual_review": {"required": True, "items": []},
                },
                tmpdir,
            )

            run_service.apply_edit_patch_to_run(
                run.id,
                {
                    "items": [
                        {
                            "action": "soft_delete",
                            "table": "process_flow",
                            "target": "process_step:P10",
                            "row_id": "P10",
                        }
                    ]
                },
            )
            reloaded = DesktopRunService(db_path).get_run(run.id)

            pfmea_model = three_table_to_table_model(reloaded.current_result, "pfmea")
            cp_model = three_table_to_table_model(reloaded.current_result, "control_plan")

            self.assertEqual(pfmea_model["rows"], [])
            self.assertEqual(cp_model["rows"], [])

            run_service.apply_edit_patch_to_run(
                run.id,
                {
                    "items": [
                        {
                            "action": "update",
                            "table": "process_flow",
                            "target": "process_step:P10",
                            "row_id": "P10",
                            "changes": {"deleted": False, "soft_deleted": False},
                        }
                    ]
                },
            )
            restored = DesktopRunService(db_path).get_run(run.id)
            restored_pfmea_model = three_table_to_table_model(restored.current_result, "pfmea")
            restored_cp_model = three_table_to_table_model(restored.current_result, "control_plan")

            self.assertEqual(restored_pfmea_model["rows"][0]["pfmea_id"], "PFMEA-P10-001")
            self.assertEqual(restored_cp_model["rows"][0]["control_plan_id"], "CP-P10-001")
            self.assertTrue(
                all(
                    item.get("status") in {"无影响", "已处理", "已忽略"}
                    for item in restored.current_result["metadata"].get("change_impacts", [])
                )
            )


    def test_metadata_patch_actions_accumulate_and_reload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            run = run_service.save_result(
                None,
                {
                    "document_type": "three_table_generation_result",
                    "status": "needs_review",
                    "process_flow": {
                        "steps": [
                            {
                                "process_step_id": "P10",
                                "operation": "来料检验",
                                "process_function": "确认来料状态",
                                "equipment": "旧检验台",
                                "evidence_refs": ["EV-1"],
                                "needs_confirmation": True,
                            }
                        ]
                    },
                    "pfmea": {
                        "rows": [
                            {
                                "pfmea_id": "PFMEA-P10-001",
                                "process_step_id": "P10",
                                "operation": "来料检验",
                                "process_step": "来料检验",
                                "function_requirement": "确认来料状态",
                                "process_work_element": "旧检验台",
                                "failure_mode": "来料错误",
                                "failure_effect": "不合格流出",
                                "severity": 6,
                                "failure_cause": "标识未确认",
                                "occurrence": 3,
                                "prevention_control": "批次隔离",
                                "detection_control": "首件确认",
                                "detection": 4,
                                "action_priority": "L",
                                "evidence_refs": ["EV-1"],
                                "needs_confirmation": True,
                            }
                        ]
                    },
                    "control_plan": {"rows": []},
                    "drawing_analysis": {"evidence": [{"evidence_id": "EV-1", "content": "fixture"}]},
                    "manual_review": {"required": True, "items": []},
                },
                tmpdir,
            )

            run_service.apply_edit_patch_to_run(
                run.id,
                {
                    "items": [
                        {
                            "action": "update",
                            "table": "process_flow",
                            "target": "process_step:P10",
                            "row_id": "P10",
                            "changes": {
                                "operation": "来料检验-已修改",
                                "process_function": "确认材料和版本已更新",
                                "equipment": "更新后的检验台",
                            },
                        }
                    ]
                },
            )
            reloaded = DesktopRunService(db_path).get_run(run.id)

        pfmea_model = three_table_to_table_model(reloaded.current_result, "pfmea")

        self.assertEqual(pfmea_model["rows"][0]["operation"], "来料检验-已修改")
        self.assertEqual(pfmea_model["rows"][0]["process_step"], "来料检验-已修改")
        self.assertEqual(pfmea_model["rows"][0]["function_requirement"], "确认材料和版本已更新")
        self.assertEqual(pfmea_model["rows"][0]["process_work_element"], "更新后的检验台")


    def test_export_run_returns_flat_export_paths_and_gate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            run = run_service.save_result(
                None,
                {
                    "status": "needs_review",
                    "process_flow": {"steps": []},
                    "pfmea": {"rows": []},
                    "control_plan": {"rows": []},
                    "manual_review": {"required": False, "items": []},
                },
                tmpdir,
            )

            result = run_service.export_run(run.id, os.path.join(tmpdir, "export"), "draft")

        self.assertEqual(result["export_mode"], "draft")
        self.assertIn("unified_workbook", result["exports"])
        self.assertIn("quality_gate", result)


    def test_recent_runs_list_and_restore_latest_current_result(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            first = run_service.save_result(
                None,
                {
                    "status": "needs_review",
                    "process_flow": {"steps": [{"process_step_id": "P10", "operation": "First"}]},
                    "pfmea": {"rows": []},
                    "control_plan": {"rows": []},
                    "manual_review": {"required": True, "items": []},
                },
                tmpdir,
            )
            second = run_service.save_result(
                None,
                {
                    "status": "draft_ready",
                    "process_flow": {"steps": [{"process_step_id": "P20", "operation": "Second"}]},
                    "pfmea": {"rows": []},
                    "control_plan": {"rows": []},
                    "manual_review": {"required": False, "items": []},
                },
                tmpdir,
            )

            recent = run_service.list_recent_runs(limit=1)
            restored = run_service.restore_run(first.id)

        self.assertEqual(recent[0].id, second.id)
        self.assertEqual(
            restored.raw_result["process_flow"]["steps"][0]["operation"],
            "First",
        )





if __name__ == "__main__":
    unittest.main()
