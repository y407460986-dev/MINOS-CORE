import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient

from minos_core.pipeline_chain import generate_pfmea_from_confirmed_pfd
from minos_desktop.api.app import create_app
from minos_desktop.app_state import ChainStageStates, DesktopRunState, StageConfirmState
from minos_desktop.api.sse import create_sse_token
from minos_desktop.services import DesktopRunService
from minos_desktop.api.sse import ProgressChannel, create_channel, remove_channel


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

    def test_pfmea_progress_step_index_counts_pfd_steps_once(self):
        confirmed_pfd = {
            "steps": [
                {"process_step_id": "P10", "operation": "来料检验"},
                {"process_step_id": "P20", "operation": "冲压成形"},
            ]
        }
        payloads = [
            {
                "rows": [
                    {
                        "pfmea_id": "",
                        "process_step_id": "P10",
                        "process_item": "制造过程",
                        "process_step_name": "",
                        "work_element_4m": "机",
                        "function_process_step": "",
                        "function_work_element": "检验台确认",
                        "failure_effect": "不合格件流入",
                        "severity": 7,
                        "failure_mode": "来料误判",
                        "failure_cause": "检验标准错误",
                        "prevention_control": "标准版本确认",
                        "occurrence": 3,
                        "detection_control": "记录复核",
                        "detection": 4,
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
            },
            {
                "rows": [
                    {
                        "pfmea_id": "",
                        "process_step_id": "P20",
                        "process_item": "制造过程",
                        "process_step_name": "",
                        "work_element_4m": "机",
                        "function_process_step": "",
                        "function_work_element": "压力机成形",
                        "failure_effect": "尺寸异常",
                        "severity": 8,
                        "failure_mode": "成形尺寸偏差",
                        "failure_cause": "参数漂移",
                        "prevention_control": "首件确认",
                        "occurrence": 4,
                        "detection_control": "尺寸巡检",
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
            },
        ]
        events: list[dict] = []

        with patch("minos_core.pipeline_chain.OpenAITextGenerator") as generator:
            generator.return_value.generate_structured.side_effect = payloads
            generate_pfmea_from_confirmed_pfd({}, confirmed_pfd, on_progress=events.append)

        completed_events = [event for event in events if event["type"] == "step_complete"]
        self.assertEqual([event["step_index"] for event in completed_events], [0, 1])
        self.assertEqual([event["total_steps"] for event in completed_events], [2, 2])
        self.assertEqual([event["rows_so_far"] for event in completed_events], [1, 2])

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

    def test_sse_empty_channel_returns_persisted_terminal_state(self):
        async def request_stream() -> tuple[int, str]:
            with tempfile.TemporaryDirectory() as tmpdir:
                db_path = os.path.join(tmpdir, "desktop.sqlite3")
                service = DesktopRunService(db_path)
                chain_stages = ChainStageStates(
                    pfd=StageConfirmState(status="confirmed", row_count=1),
                    pfmea=StageConfirmState(status="failed", row_count=3),
                    pipeline_mode="chain",
                )
                run = service.save_chain_run(
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
                        manual_review_items=(),
                        chain_stages=chain_stages,
                    ),
                    tmpdir,
                    {
                        "document_type": "three_table_generation_result",
                        "status": "failed",
                        "blocked_stage": "pfmea",
                        "process_flow": {"steps": [{"process_step_id": "P10"}]},
                        "pfmea": {"rows": [{"pfmea_id": "F1"}, {"pfmea_id": "F2"}, {"pfmea_id": "F3"}]},
                        "control_plan": {"rows": []},
                        "manual_review": {"required": False, "items": []},
                    },
                    "PFMEA 生成失败",
                    chain_stages,
                )
                app = create_app(db_path=db_path, output_dir=tmpdir)
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await client.get(f"/api/runs/{run.id}/chain/pfmea/stream")
                return response.status_code, response.text

        status_code, text = asyncio.run(request_stream())

        self.assertEqual(status_code, 200)
        self.assertIn('"status": "failed"', text)
        self.assertIn('"total_rows": 3', text)
        self.assertNotIn("not_running", text)

    def test_sse_token_endpoint_requires_bearer_token(self):
        async def request_token() -> tuple[int, str]:
            with tempfile.TemporaryDirectory() as tmpdir:
                app = create_app(
                    db_path=os.path.join(tmpdir, "desktop.sqlite3"),
                    output_dir=tmpdir,
                )
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await client.get("/api/sse-token")
                return response.status_code, response.text

        with patch.dict(os.environ, {"MINOS_DESKTOP_API_TOKEN": "secret"}, clear=False):
            status_code, text = asyncio.run(request_token())

        self.assertEqual(status_code, 401)
        self.assertIn("Authorization bearer token", text)

    def test_sse_stream_requires_short_lived_token_when_api_token_set(self):
        async def request_stream(query: str = "") -> int:
            with tempfile.TemporaryDirectory() as tmpdir:
                db_path = os.path.join(tmpdir, "desktop.sqlite3")
                service = DesktopRunService(db_path)
                chain_stages = ChainStageStates(
                    pfd=StageConfirmState(status="confirmed", row_count=1),
                    pfmea=StageConfirmState(status="generated", row_count=1),
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
                        "process_flow": {"steps": [{"process_step_id": "P10"}]},
                        "pfmea": {"rows": [{"pfmea_id": "F1"}]},
                        "control_plan": {"rows": []},
                        "manual_review": {"required": False, "items": []},
                    },
                    "",
                    chain_stages,
                )
                app = create_app(db_path=db_path, output_dir=tmpdir)
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await client.get(
                        f"/api/runs/{run.id}/chain/pfmea/stream{query}"
                    )
                return response.status_code

        with patch.dict(os.environ, {"MINOS_DESKTOP_API_TOKEN": "secret"}, clear=False):
            self.assertEqual(asyncio.run(request_stream()), 401)
            self.assertEqual(asyncio.run(request_stream("?token=bad-token")), 401)
            token = create_sse_token("secret")
            self.assertEqual(asyncio.run(request_stream(f"?token={token}")), 200)

    def test_sse_closed_channel_reconnect_returns_persisted_terminal_state(self):
        async def request_stream() -> tuple[int, str]:
            with tempfile.TemporaryDirectory() as tmpdir:
                db_path = os.path.join(tmpdir, "desktop.sqlite3")
                service = DesktopRunService(db_path)
                chain_stages = ChainStageStates(
                    pfd=StageConfirmState(status="confirmed", row_count=1),
                    pfmea=StageConfirmState(status="generated", row_count=2),
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
                        "process_flow": {"steps": [{"process_step_id": "P10"}]},
                        "pfmea": {"rows": [{"pfmea_id": "F1"}, {"pfmea_id": "F2"}]},
                        "control_plan": {"rows": []},
                        "manual_review": {"required": False, "items": []},
                    },
                    "",
                    chain_stages,
                )
                channel = create_channel(run.id, "pfmea")
                channel.close()
                app = create_app(db_path=db_path, output_dir=tmpdir)
                transport = ASGITransport(app=app)
                try:
                    async with AsyncClient(transport=transport, base_url="http://test") as client:
                        response = await client.get(f"/api/runs/{run.id}/chain/pfmea/stream")
                    return response.status_code, response.text
                finally:
                    remove_channel(run.id, "pfmea")

        status_code, text = asyncio.run(request_stream())

        self.assertEqual(status_code, 200)
        self.assertIn('"status": "generated"', text)
        self.assertIn('"total_rows": 2', text)

    def test_sse_closed_channel_reconnect_returns_persisted_failed_state(self):
        async def request_stream() -> tuple[int, str]:
            with tempfile.TemporaryDirectory() as tmpdir:
                db_path = os.path.join(tmpdir, "desktop.sqlite3")
                service = DesktopRunService(db_path)
                chain_stages = ChainStageStates(
                    pfd=StageConfirmState(status="confirmed", row_count=1),
                    pfmea=StageConfirmState(status="failed", row_count=4),
                    pipeline_mode="chain",
                )
                run = service.save_chain_run(
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
                        manual_review_items=(),
                        chain_stages=chain_stages,
                    ),
                    tmpdir,
                    {
                        "document_type": "three_table_generation_result",
                        "status": "failed",
                        "blocked_stage": "pfmea",
                        "process_flow": {"steps": [{"process_step_id": "P10"}]},
                        "pfmea": {"rows": [{"pfmea_id": "F1"}, {"pfmea_id": "F2"}, {"pfmea_id": "F3"}, {"pfmea_id": "F4"}]},
                        "control_plan": {"rows": []},
                        "manual_review": {"required": False, "items": []},
                    },
                    "PFMEA 生成失败",
                    chain_stages,
                )
                channel = create_channel(run.id, "pfmea")
                channel.close()
                app = create_app(db_path=db_path, output_dir=tmpdir)
                transport = ASGITransport(app=app)
                try:
                    async with AsyncClient(transport=transport, base_url="http://test") as client:
                        response = await client.get(f"/api/runs/{run.id}/chain/pfmea/stream")
                    return response.status_code, response.text
                finally:
                    remove_channel(run.id, "pfmea")

        status_code, text = asyncio.run(request_stream())

        self.assertEqual(status_code, 200)
        self.assertIn('"status": "failed"', text)
        self.assertIn('"total_rows": 4', text)
        self.assertIn("PFMEA 生成失败", text)


if __name__ == "__main__":
    unittest.main()
