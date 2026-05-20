import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

from minos_core.pipeline_chain import generate_pfmea_from_confirmed_pfd
from minos_desktop.app_state import ChainStageStates, DesktopRunState, StageConfirmState
from minos_desktop.services import DesktopRunService
from minos_desktop.api.sse import ProgressChannel


class TestSseChainResilience(unittest.TestCase):
    def test_progress_channel_emits_heartbeat_while_idle(self):
        async def collect_event_type() -> str:
            channel = ProgressChannel(101, "pfmea", heartbeat_interval=0.01)
            drain = channel.drain()
            event = await asyncio.wait_for(drain.__anext__(), timeout=0.2)
            await drain.aclose()
            return str(event.event)

        self.assertEqual(asyncio.run(collect_event_type()), "heartbeat")

    def test_pfmea_generation_continues_after_one_step_failure(self):
        confirmed_pfd = {
            "steps": [
                {"process_step_id": "P10", "operation": "来料检验"},
                {"process_step_id": "P20", "operation": "冲压成形"},
            ]
        }
        success_payload = {
            "rows": [
                {
                    "pfmea_id": "",
                    "process_step_id": "P20",
                    "process_item": "制造过程",
                    "process_step_name": "",
                    "work_element_4m": "机",
                    "function_process_step": "",
                    "function_work_element": "压力机输出",
                    "failure_effect": "影响装配",
                    "severity": 8,
                    "failure_mode": "成形尺寸偏差",
                    "failure_cause": "冲压参数漂移",
                    "prevention_control": "参数确认",
                    "occurrence": 4,
                    "detection_control": "尺寸检验",
                    "detection": 5,
                    "action_priority": "M",
                    "special_characteristics": "无",
                    "preventive_action": "",
                    "detection_action": "",
                    "responsible_person": "",
                    "target_date": "",
                    "status": "未开始",
                    "needs_confirmation": True,
                }
            ]
        }
        events: list[dict] = []

        with patch("minos_core.pipeline_chain.OpenAITextGenerator") as generator:
            llm = generator.return_value

            def fake_generate_structured(*_args, **kwargs):
                prompt = kwargs.get("user_prompt", "")
                if "P10" in prompt:
                    raise RuntimeError("upstream timeout")
                return success_payload

            llm.generate_structured.side_effect = fake_generate_structured

            pfmea = generate_pfmea_from_confirmed_pfd(
                {},
                confirmed_pfd,
                on_progress=events.append,
            )

        self.assertEqual([row["process_step_id"] for row in pfmea["rows"]], ["P20"])
        self.assertEqual(pfmea["metadata"]["failed_step_ids"], ["P10"])
        self.assertEqual(events[0]["type"], "step_failed")
        self.assertEqual(events[0]["step_id"], "P10")
        self.assertEqual(events[-1]["type"], "step_complete")
        self.assertEqual(events[-1]["step_id"], "P20")

    def test_pfmea_generation_still_fails_when_all_steps_fail(self):
        confirmed_pfd = {"steps": [{"process_step_id": "P10", "operation": "来料检验"}]}

        with patch("minos_core.pipeline_chain.OpenAITextGenerator") as generator:
            generator.return_value.generate_structured.side_effect = RuntimeError("all failed")
            with self.assertRaisesRegex(ValueError, "all failed"):
                generate_pfmea_from_confirmed_pfd({}, confirmed_pfd)

    def test_pfmea_progress_checkpoint_persists_partial_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            service = DesktopRunService(db_path)
            chain_stages = ChainStageStates(
                pfd=StageConfirmState(status="confirmed", row_count=2),
                pfmea=StageConfirmState(status="running"),
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
                    "drawing_analysis": {},
                    "process_flow": {
                        "steps": [
                            {"process_step_id": "P10", "operation": "来料检验"},
                            {"process_step_id": "P20", "operation": "冲压成形"},
                        ]
                    },
                    "pfmea": {"rows": []},
                    "control_plan": {"rows": []},
                    "manual_review": {"required": False, "items": []},
                },
                "",
                chain_stages,
            )

            def fake_generate(_drawing_analysis, _confirmed_pfd, on_progress=None):
                if on_progress:
                    on_progress({
                        "type": "step_complete",
                        "stage": "pfmea",
                        "step_index": 0,
                        "total_steps": 2,
                        "step_id": "P10",
                        "rows_so_far": 1,
                        "new_rows": [
                            {
                                "pfmea_id": "PFMEA-P10-01",
                                "process_step_id": "P10",
                                "failure_mode": "来料错误",
                                "needs_confirmation": True,
                            }
                        ],
                    })
                persisted = DesktopRunService(db_path).get_run(run.id)
                self.assertEqual(
                    persisted.current_result["pfmea"]["rows"][0]["pfmea_id"],
                    "PFMEA-P10-01",
                )
                self.assertEqual(persisted.current_result["pfmea"]["metadata"]["chain_stage_status"], "partial")
                return {
                    "rows": [
                        {
                            "pfmea_id": "PFMEA-P10-01",
                            "process_step_id": "P10",
                            "failure_mode": "来料错误",
                            "needs_confirmation": True,
                        },
                        {
                            "pfmea_id": "PFMEA-P20-01",
                            "process_step_id": "P20",
                            "failure_mode": "尺寸偏差",
                            "needs_confirmation": True,
                        },
                    ]
                }

            with patch("minos_core.pipeline_chain.generate_pfmea_from_confirmed_pfd", fake_generate):
                generated = service.generate_pfmea_for_confirmed_pfd(run.id)

        self.assertEqual(generated.state.chain_stages.pfmea.status, "generated")
        self.assertEqual(len(generated.current_result["pfmea"]["rows"]), 2)


if __name__ == "__main__":
    unittest.main()
