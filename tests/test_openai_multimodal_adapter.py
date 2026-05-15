import json
import os
import tempfile
import unittest
import urllib.error
import time
from pathlib import Path
from io import BytesIO
from unittest.mock import patch

from PIL import Image

from minos_core.adapters.multimodal import (
    OpenAIMultimodalError,
    OpenAIResponsesMultimodalDrawingAnalyzer,
    _parse_responses_stream,
    _should_retry_http_status,
    _extract_output_text,
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

        def fake_urlopen(request, timeout=0):
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
            'event: response.created\n'
            'data: {"type":"response.created"}\n\n'
            'event: response.output_text.delta\n'
            'data: {"type":"response.output_text.delta","delta":"MINOS"}\n\n'
            'event: response.output_text.delta\n'
            'data: {"type":"response.output_text.delta","delta":"_OK"}\n\n'
            'event: response.completed\n'
            'data: {"type":"response.completed","response":{"id":"resp_test","model":"gpt-test","output":[]}}\n\n'
        ).encode("utf-8")

        parsed = _parse_responses_stream(BytesIO(raw), fallback_model="gpt-test")

        self.assertEqual(parsed["id"], "resp_test")
        self.assertEqual(parsed["output_text"], "MINOS_OK")

    def test_streaming_parser_accepts_output_text_done_event(self):
        raw = (
            'event: response.output_text.done\n'
            'data: {"type":"response.output_text.done","text":"{\\"ok\\":true}"}\n\n'
            'event: response.completed\n'
            'data: {"type":"response.completed","response":{"id":"resp_test","model":"gpt-test","output":[]}}\n\n'
        ).encode("utf-8")

        parsed = _parse_responses_stream(BytesIO(raw), fallback_model="gpt-test")

        self.assertEqual(parsed["id"], "resp_test")
        self.assertEqual(parsed["output_text"], '{"ok":true}')

    def test_streaming_parser_accepts_response_done_output_text(self):
        raw = (
            'event: response.done\n'
            'data: {"type":"response.done","response":{"id":"resp_test","model":"gpt-test","output_text":"{\\"ok\\":true}"}}\n\n'
        ).encode("utf-8")

        parsed = _parse_responses_stream(BytesIO(raw), fallback_model="gpt-test")

        self.assertEqual(parsed["id"], "resp_test")
        self.assertEqual(parsed["output_text"], '{"ok":true}')

    def test_streaming_parser_accepts_output_item_done_message_content(self):
        raw = (
            'event: response.output_item.done\n'
            'data: {"type":"response.output_item.done","item":{"type":"message","content":[{"type":"output_text","text":"{\\"ok\\":true}"}]}}\n\n'
            'event: response.completed\n'
            'data: {"type":"response.completed","response":{"id":"resp_test","model":"gpt-test","output":[]}}\n\n'
        ).encode("utf-8")

        parsed = _parse_responses_stream(BytesIO(raw), fallback_model="gpt-test")

        self.assertEqual(parsed["id"], "resp_test")
        self.assertEqual(parsed["output_text"], '{"ok":true}')

    def test_streaming_parser_accepts_content_part_done_output_text(self):
        raw = (
            'event: response.content_part.done\n'
            'data: {"type":"response.content_part.done","part":{"type":"output_text","text":"{\\"ok\\":true}"}}\n\n'
            'event: response.completed\n'
            'data: {"type":"response.completed","response":{"id":"resp_test","model":"gpt-test","output":[]}}\n\n'
        ).encode("utf-8")

        parsed = _parse_responses_stream(BytesIO(raw), fallback_model="gpt-test")

        self.assertEqual(parsed["id"], "resp_test")
        self.assertEqual(parsed["output_text"], '{"ok":true}')

    def test_streaming_parser_reports_failed_event(self):
        raw = (
            'event: response.failed\n'
            'data: {"type":"response.failed","error":{"message":"boom"}}\n\n'
        ).encode("utf-8")

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

        def fake_urlopen(_request, timeout=0):
            calls["count"] += 1
            if calls["count"] < 3:
                raw = (
                    b'event: error\n'
                    b'data: {"type":"error","error":{"type":"service_unavailable_error","code":"server_is_overloaded","message":"Our servers are currently overloaded. Please try again later."},"sequence_number":3}\n\n'
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
