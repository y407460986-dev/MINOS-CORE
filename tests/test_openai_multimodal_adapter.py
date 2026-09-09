import json
import os
import tempfile
import time
import unittest
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from minos_core.adapters.multimodal import (
    OpenAIMultimodalError,
    OpenAIResponsesMultimodalDrawingAnalyzer,
    _drawing_analysis_prompt,
    _extract_output_text,
    _parse_responses_stream,
    _should_retry_http_status,
    create_default_multimodal_drawing_analyzer,
)
from minos_core.drawing_input import load_drawing_source, render_drawing_pages


class OpenAIResponsesMultimodalDrawingAnalyzerTests(unittest.TestCase):
    def test_requires_api_key_without_network_call(self):
        with patch.dict(os.environ, {"MINOS_DISABLE_CODEX_CONFIG": "1"}, clear=True):
            analyzer = OpenAIResponsesMultimodalDrawingAnalyzer(api_key="", model="gpt-test")

            with self.assertRaisesRegex(OpenAIMultimodalError, "API key is not configured"):
                analyzer.analyze_drawing_pages([])

    def test_request_payload_contains_base64_image_url_and_prompt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "drawing.png"
            Image.new("RGB", (10, 8), color="white").save(image_path)
            pages = render_drawing_pages(load_drawing_source(image_path))
            analyzer = OpenAIResponsesMultimodalDrawingAnalyzer(
                api_key="test-key",
                model="gpt-test",
            )
            analyzer.store = False
            analyzer.reasoning_effort = "high"

            payload = analyzer._request_payload(pages, {"part_family": "stamping"})

            self.assertEqual(payload["model"], "gpt-test")
            self.assertIs(payload["store"], False)
            self.assertEqual(payload["reasoning"], {"effort": "high"})
            self.assertIs(payload["stream"], True)
            content = payload["input"][0]["content"]
            self.assertEqual(content[0]["type"], "input_text")
            self.assertIn("drawing_analysis_bundle", content[0]["text"])
            self.assertIn("所有给用户看的业务内容", content[0]["text"])
            self.assertIn("必须使用中文", content[0]["text"])
            self.assertEqual(content[1]["type"], "input_image")
            self.assertTrue(content[1]["image_url"].startswith("data:image/png;base64,"))

    def test_request_payload_includes_visual_evidence_crops_from_ocr_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "drawing.png"
            Image.new("RGB", (2000, 1400), color="white").save(image_path)
            pages = render_drawing_pages(load_drawing_source(image_path))
            analyzer = OpenAIResponsesMultimodalDrawingAnalyzer(
                api_key="test-key",
                model="gpt-test",
            )

            payload = analyzer._request_payload(
                pages,
                {
                    "ocr_analysis_summary": {
                        "declared_totals": {"CC": 2, "SC": 1},
                        "technical_requirements": [
                            {"text": "4. 转动力矩(0.5~2.5)Nm", "evidence_refs": ["REQ4"]},
                            {"text": "5. GB 15086", "evidence_refs": ["REQ5"]},
                        ],
                    }
                },
            )

            content = payload["input"][0]["content"]
            images = [item for item in content if item["type"] == "input_image"]
            text_blocks = "\n".join(
                item["text"] for item in content if item["type"] == "input_text"
            )

            self.assertGreater(len(images), 1)
            self.assertIn("drawing_page_001_title_block_special_counts", text_blocks)
            self.assertIn("drawing_page_001_technical_requirement_001", text_blocks)

    def test_focused_locator_default_payload_uses_broad_regions_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "drawing.png"
            Image.new("RGB", (2000, 1400), color="white").save(image_path)
            pages = render_drawing_pages(load_drawing_source(image_path))
            analyzer = OpenAIResponsesMultimodalDrawingAnalyzer(
                api_key="test-key",
                model="gpt-test",
            )

            payload = analyzer._request_payload(
                pages,
                {
                    "visual_task": "special_characteristic_locator",
                    "ocr_analysis_summary": {
                        "declared_totals": {"CC": 2, "SC": 1},
                        "technical_requirements": [
                            {"text": "4. (2) 转动力矩(0.5~2.5)Nm"},
                            {"text": "5. GB 15086"},
                            {"text": "6. Q/BJORV M 0102"},
                        ],
                    },
                },
            )

            content = payload["input"][0]["content"]
            images = [item for item in content if item["type"] == "input_image"]
            text_blocks = "\n".join(
                item["text"] for item in content if item["type"] == "input_text"
            )

            self.assertEqual(len(images), 3)
            self.assertIn("drawing_page_001_title_block_special_counts", text_blocks)
            self.assertIn("drawing_page_001_key_product_characteristic_table", text_blocks)
            self.assertIn("drawing_page_001_technical_requirements", text_blocks)
            self.assertNotIn("technical_requirement_line_001", text_blocks)
            self.assertNotIn("technical_requirement_line_004", text_blocks)

    def test_focused_locator_detailed_payload_keeps_line_crops(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "drawing.png"
            Image.new("RGB", (2000, 1400), color="white").save(image_path)
            pages = render_drawing_pages(load_drawing_source(image_path))
            analyzer = OpenAIResponsesMultimodalDrawingAnalyzer(
                api_key="test-key",
                model="gpt-test",
            )

            payload = analyzer._request_payload(
                pages,
                {
                    "visual_task": "special_characteristic_locator",
                    "special_characteristic_locator_detail": "detailed",
                    "ocr_analysis_summary": {
                        "declared_totals": {"CC": 2, "SC": 1},
                        "technical_requirements": [
                            {"text": "4. (2) 转动力矩(0.5~2.5)Nm"},
                            {"text": "5. GB 15086"},
                            {"text": "6. Q/BJORV M 0102"},
                        ],
                    },
                },
            )

            content = payload["input"][0]["content"]
            images = [item for item in content if item["type"] == "input_image"]
            text_blocks = "\n".join(
                item["text"] for item in content if item["type"] == "input_text"
            )

            self.assertGreaterEqual(len(images), 6)
            self.assertLessEqual(len(images), 8)
            self.assertIn("drawing_page_001_technical_requirement_line_003", text_blocks)
            self.assertIn("drawing_page_001_technical_requirement_line_004", text_blocks)

    def test_focused_locator_prompt_uses_slim_special_characteristic_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "drawing.png"
            Image.new("RGB", (2000, 1400), color="white").save(image_path)
            pages = render_drawing_pages(load_drawing_source(image_path))
            analyzer = OpenAIResponsesMultimodalDrawingAnalyzer(
                api_key="test-key",
                model="gpt-test",
            )

            payload = analyzer._request_payload(
                pages,
                {
                    "visual_task": "special_characteristic_locator",
                    "ocr_analysis_summary": {
                        "declared_totals": {"CC": 2, "SC": 1},
                        "technical_requirements": [
                            {
                                "text": "4. (2) 转动力矩(0.5~2.5)Nm",
                                "evidence_refs": ["REQ4-TORQUE"],
                            },
                            {"text": "5. GB 15086", "evidence_refs": ["REQ5"]},
                            {"text": "6. Q/BJORV M 0102", "evidence_refs": ["REQ6"]},
                        ],
                        "materials": [{"name": "SHOULD_NOT_BE_SENT_TO_LOCATOR"}],
                        "manufacturing_clues": [
                            {"operation": "SHOULD_NOT_BE_SENT_TO_LOCATOR"}
                        ],
                    },
                    "irrelevant_large_context": "x" * 8000,
                },
            )

            prompt = payload["input"][0]["content"][0]["text"]

            self.assertIn("declared_totals", prompt)
            self.assertIn("located_occurrences", prompt)
            self.assertIn("special_characteristic_candidates", prompt)
            self.assertIn("focused_review_requests", prompt)
            self.assertIn("声明行、数量行、图例行本身", prompt)
            self.assertIn("不能把声明行", prompt)
            self.assertIn("绑定到具体技术要求、尺寸、功能或法规条款", prompt)
            self.assertNotIn("materials, surface_treatments", prompt)
            self.assertNotIn("manufacturing_clues, uncertainties", prompt)
            self.assertNotIn('"materials"', prompt)
            self.assertNotIn('"surface_treatments"', prompt)
            self.assertNotIn('"manufacturing_clues"', prompt)
            self.assertNotIn('"uncertainties"', prompt)
            self.assertNotIn("SHOULD_NOT_BE_SENT_TO_LOCATOR", prompt)
            self.assertNotIn("irrelevant_large_context", prompt)
            self.assertLess(len(prompt), 3500)

    def test_prompt_requests_gpt55_visual_locator_outputs_for_declared_counts(self):
        prompt = _drawing_analysis_prompt(
            {
                "ocr_analysis_summary": {
                    "declared_totals": {"CC": 2, "SC": 1},
                },
                "special_characteristic_discovery_request": {
                    "declared_totals": {"CC": 2, "SC": 1},
                },
            }
        )

        self.assertIn("GPT5.5 visual locator", prompt)
        self.assertIn("located_occurrences", prompt)
        self.assertIn("missing_counts", prompt)
        self.assertIn("focused_review_requests", prompt)
        self.assertIn("CC=2", prompt)
        self.assertIn("SC=1", prompt)
        self.assertIn("带圈数字", prompt)
        self.assertIn("转动力矩", prompt)

    def test_mimo_analyzer_class_is_removed(self):
        import minos_core.adapters.multimodal as multimodal

        self.assertFalse(hasattr(multimodal, "MimoV25ChatCompletionsDrawingAnalyzer"))
        self.assertFalse(hasattr(multimodal, "_mimo_v25_drawing_analysis_prompt"))

    def test_default_multimodal_analyzer_uses_openai_responses_even_when_mimo_provider_set(self):
        with patch.dict(
            os.environ,
            {
                "MINOS_DISABLE_CODEX_CONFIG": "1",
                "MINOS_VISION_PROVIDER": "mimo",
                "MINOS_MIMO_API_KEY": "mimo-secret",
            },
            clear=True,
        ):
            analyzer = create_default_multimodal_drawing_analyzer()

        self.assertIsInstance(analyzer, OpenAIResponsesMultimodalDrawingAnalyzer)

    def test_responses_url_uses_configured_path(self):
        analyzer = OpenAIResponsesMultimodalDrawingAnalyzer(
            api_key="test-key",
            base_url="https://proxy.example/v1",
            model="gpt-test",
            responses_path="responses",
        )

        self.assertEqual(analyzer._responses_url(), "https://proxy.example/v1/responses")

    def test_rejects_unsupported_wire_api_before_network_call(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            (codex_home / "config.toml").write_text(
                '\n'.join(
                    [
                        'model_provider = "custom"',
                        '[model_providers.custom]',
                        'wire_api = "chat"',
                        'base_url = "https://proxy.example"',
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "MINOS_CODEX_HOME": str(codex_home),
                    "MINOS_OPENAI_API_KEY": "secret",
                },
                clear=True,
            ):
                with self.assertRaisesRegex(OpenAIMultimodalError, "unsupported"):
                    OpenAIResponsesMultimodalDrawingAnalyzer()

    def test_retries_transient_http_error_then_succeeds(self):
        analyzer = OpenAIResponsesMultimodalDrawingAnalyzer(
            api_key="test-key",
            base_url="https://proxy.example",
            model="gpt-test",
            responses_path="responses",
            retry_delay=0,
        )
        calls = {"count": 0}

        def fake_urlopen(request, timeout=0, context=None):
            calls["count"] += 1
            self.assertEqual(request.headers["User-agent"], analyzer.user_agent)
            if calls["count"] == 1:
                raise urllib.error.HTTPError(
                    request.full_url,
                    503,
                    "Service unavailable",
                    hdrs=None,
                    fp=BytesIO(b'{"error":{"message":"temporary"}}'),
                )

            class _Response:
                status = 200

                def read(self):
                    return b'{"output_text":"ok"}'

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

            return _Response()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            parsed = analyzer._post_json(
                analyzer._responses_url(), {"model": "gpt-test", "stream": False}
            )

        self.assertEqual(calls["count"], 2)
        self.assertEqual(parsed["output_text"], "ok")

    def test_streaming_parser_collects_output_text_delta(self):
        raw = (
            b'event: response.created\n'
            b'data: {"type":"response.created"}\n\n'
            b'event: response.output_text.delta\n'
            b'data: {"type":"response.output_text.delta","delta":"MINOS"}\n\n'
            b'event: response.output_text.delta\n'
            b'data: {"type":"response.output_text.delta","delta":"_OK"}\n\n'
            b'event: response.completed\n'
            b'data: {"type":"response.completed","response":{"id":"resp_test","model":"gpt-test","output":[]}}\n\n'
        )

        parsed = _parse_responses_stream(BytesIO(raw), fallback_model="gpt-test")

        self.assertEqual(parsed["id"], "resp_test")
        self.assertEqual(parsed["output_text"], "MINOS_OK")

    def test_streaming_parser_accepts_output_text_done_event(self):
        raw = (
            b'event: response.output_text.done\n'
            b'data: {"type":"response.output_text.done","text":"{\\"ok\\":true}"}\n\n'
            b'event: response.completed\n'
            b'data: {"type":"response.completed","response":{"id":"resp_test","model":"gpt-test","output":[]}}\n\n'
        )

        parsed = _parse_responses_stream(BytesIO(raw), fallback_model="gpt-test")

        self.assertEqual(parsed["id"], "resp_test")
        self.assertEqual(parsed["output_text"], '{"ok":true}')

    def test_streaming_parser_accepts_response_done_output_text(self):
        raw = (
            b'event: response.done\n'
            b'data: {"type":"response.done","response":{"id":"resp_test",'
            b'"model":"gpt-test","output_text":"{\\"ok\\":true}"}}\n\n'
        )

        parsed = _parse_responses_stream(BytesIO(raw), fallback_model="gpt-test")

        self.assertEqual(parsed["id"], "resp_test")
        self.assertEqual(parsed["output_text"], '{"ok":true}')

    def test_streaming_parser_accepts_output_item_done_message_content(self):
        raw = (
            b'event: response.output_item.done\n'
            b'data: {"type":"response.output_item.done","item":{"type":"message",'
            b'"content":[{"type":"output_text","text":"{\\"ok\\":true}"}]}}\n\n'
            b'event: response.completed\n'
            b'data: {"type":"response.completed","response":{"id":"resp_test","model":"gpt-test","output":[]}}\n\n'
        )

        parsed = _parse_responses_stream(BytesIO(raw), fallback_model="gpt-test")

        self.assertEqual(parsed["id"], "resp_test")
        self.assertEqual(parsed["output_text"], '{"ok":true}')

    def test_streaming_parser_accepts_content_part_done_output_text(self):
        raw = (
            b'event: response.content_part.done\n'
            b'data: {"type":"response.content_part.done","part":{"type":"output_text","text":"{\\"ok\\":true}"}}\n\n'
            b'event: response.completed\n'
            b'data: {"type":"response.completed","response":{"id":"resp_test","model":"gpt-test","output":[]}}\n\n'
        )

        parsed = _parse_responses_stream(BytesIO(raw), fallback_model="gpt-test")

        self.assertEqual(parsed["id"], "resp_test")
        self.assertEqual(parsed["output_text"], '{"ok":true}')

    def test_streaming_parser_reports_failed_event(self):
        raw = (
            b'event: response.failed\n'
            b'data: {"type":"response.failed","error":{"message":"boom"}}\n\n'
        )

        with self.assertRaisesRegex(OpenAIMultimodalError, "stream failed"):
            _parse_responses_stream(BytesIO(raw), fallback_model="gpt-test")

    def test_post_json_retries_stream_server_overloaded(self):
        analyzer = OpenAIResponsesMultimodalDrawingAnalyzer(
            api_key="test-key",
            base_url="https://proxy.example",
            model="gpt-test",
            responses_path="responses",
            retry_delay=0,
        )
        calls = {"count": 0}

        def fake_urlopen(_request, timeout=0, context=None):
            calls["count"] += 1
            if calls["count"] < 3:
                raw = (
                    b'event: error\n'
                    b'data: {"type":"error","error":{"type":"service_unavailable_error",'
                    b'"code":"server_is_overloaded","message":"Our servers are currently '
                    b'overloaded. Please try again later."},"sequence_number":3}\n\n'
                )
                return BytesIO(raw)
            raw = (
                b'event: response.output_text.delta\n'
                b'data: {"type":"response.output_text.delta","delta":"ok"}\n\n'
            )
            return BytesIO(raw)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            parsed = analyzer._post_json(
                analyzer._responses_url(), {"model": "gpt-test", "stream": True}
            )

        self.assertEqual(parsed["output_text"], "ok")
        self.assertEqual(calls["count"], 3)

    def test_streaming_parser_times_out_when_line_read_hangs(self):
        class _SlowStream:
            def readline(self):
                time.sleep(0.03)
                return b"event: response.output_text.delta\n"

        with self.assertRaisesRegex(OpenAIMultimodalError, "stream timed out"):
            _parse_responses_stream(
                _SlowStream(),
                fallback_model="gpt-test",
                timeout_seconds=0.01,
            )

    def test_retry_status_helper(self):
        self.assertTrue(_should_retry_http_status(502))
        self.assertTrue(_should_retry_http_status(503))
        self.assertFalse(_should_retry_http_status(401))

    def test_http_error_does_not_include_response_body_or_api_key(self):
        analyzer = OpenAIResponsesMultimodalDrawingAnalyzer(
            api_key="test-key",
            base_url="https://proxy.example",
            model="gpt-test",
            responses_path="responses",
            max_retries=0,
        )

        def fake_urlopen(request, timeout=0, context=None):
            raise urllib.error.HTTPError(
                request.full_url,
                401,
                "Unauthorized",
                hdrs=None,
                fp=BytesIO(b'{"debug":"Bearer test-key","message":"bad key"}'),
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with self.assertRaises(OpenAIMultimodalError) as raised:
                analyzer._post_json(
                    analyzer._responses_url(),
                    {"model": "gpt-test", "stream": False},
                )

        message = str(raised.exception)
        self.assertIn("401", message)
        self.assertNotIn("test-key", message)
        self.assertNotIn("bad key", message)

    def test_extract_output_text_supports_responses_shapes(self):
        self.assertEqual(_extract_output_text({"output_text": "hello"}), "hello")
        response = {
            "output": [
                {
                    "content": [
                        {"type": "output_text", "text": json.dumps({"ok": True})}
                    ]
                }
            ]
        }
        self.assertEqual(_extract_output_text(response), '{"ok": true}')


if __name__ == "__main__":
    unittest.main()
