import json
import os
import unittest
import urllib.error
from io import BytesIO
from unittest.mock import patch

from minos_core.adapters.llm_text import OpenAITextGenerator
from minos_core.ai_config import AIProviderConfig


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _StreamResponse(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _TimeoutStreamResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def readline(self):
        raise TimeoutError("stream stalled")


class OpenAITextGeneratorResponsesTests(unittest.TestCase):
    def test_generate_structured_uses_responses_payload_and_text_schema(self):
        config = AIProviderConfig(
            provider="openai_responses",
            model="gpt-test",
            base_url="https://proxy.example/v1",
            api_key_configured=True,
            api_key_env_name="MINOS_OPENAI_API_KEY",
            api_key_source="env:MINOS_OPENAI_API_KEY",
            responses_path="responses",
            reasoning_effort="medium",
            store=False,
            user_agent="minos-test",
        )
        captured = {}

        def fake_urlopen(request, timeout=0, context=None):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            raw = (
                b'event: response.output_text.delta\n'
                b'data: {"type":"response.output_text.delta","delta":"{\\"ok\\": true}"}\n\n'
            )
            return _StreamResponse(raw)

        schema = {
            "type": "json_schema",
            "json_schema": {
                "name": "chain_stage",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"],
                    "additionalProperties": False,
                },
            },
        }
        with patch.dict(os.environ, {"MINOS_OPENAI_API_KEY": "secret"}, clear=True):
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                result = OpenAITextGenerator(config).generate_structured(
                    "system",
                    "user",
                    response_format=schema,
                    max_tokens=123,
                    temperature=0.1,
                )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(captured["url"], "https://proxy.example/v1/responses")
        payload = captured["payload"]
        self.assertEqual(payload["model"], "gpt-test")
        self.assertEqual(payload["max_output_tokens"], 123)
        self.assertNotIn("max_tokens", payload)
        self.assertNotIn("temperature", payload)
        self.assertEqual(payload["input"][0]["role"], "system")
        self.assertEqual(payload["input"][1]["role"], "user")
        self.assertEqual(payload["text"]["format"]["type"], "json_schema")
        self.assertEqual(payload["text"]["format"]["name"], "chain_stage")
        self.assertEqual(payload["reasoning"], {"effort": "medium"})
        self.assertIs(payload["store"], False)
        self.assertIs(payload["stream"], True)

    def test_generate_structured_reads_responses_stream(self):
        config = AIProviderConfig(
            provider="openai_responses",
            model="gpt-test",
            base_url="https://proxy.example/v1",
            api_key_configured=True,
            api_key_env_name="MINOS_OPENAI_API_KEY",
            responses_path="responses",
            reasoning_effort="medium",
        )
        captured = {}

        def fake_urlopen(request, timeout=0, context=None):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            raw = (
                b'event: response.output_text.delta\n'
                b'data: {"type":"response.output_text.delta","delta":"{\\"ok\\":"}\n\n'
                b'event: response.output_text.delta\n'
                b'data: {"type":"response.output_text.delta","delta":" true}"}\n\n'
                b'event: response.completed\n'
                b'data: {"type":"response.completed","response":{"id":"resp_test","model":"gpt-test","output":[]}}\n\n'
            )
            return _StreamResponse(raw)

        with patch.dict(os.environ, {"MINOS_OPENAI_API_KEY": "secret"}, clear=True):
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                result = OpenAITextGenerator(config).generate_structured("system", "user")

        self.assertEqual(result, {"ok": True})
        self.assertIs(captured["payload"]["stream"], True)

    def test_generate_structured_reads_stream_event_name_when_type_missing(self):
        config = AIProviderConfig(
            provider="openai_responses",
            model="gpt-test",
            base_url="https://proxy.example/v1",
            api_key_configured=True,
            api_key_env_name="MINOS_OPENAI_API_KEY",
            responses_path="responses",
            reasoning_effort="medium",
        )

        def fake_urlopen(_request, timeout=0, context=None):
            raw = (
                b"event: response.output_text.delta\n"
                b'data: {"delta":"{\\"ok\\": true}"}\n\n'
            )
            return _StreamResponse(raw)

        with patch.dict(os.environ, {"MINOS_OPENAI_API_KEY": "secret"}, clear=True):
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                result = OpenAITextGenerator(config).generate_structured("system", "user")

        self.assertEqual(result, {"ok": True})

    def test_generate_structured_accepts_json_object_with_trailing_explanation(self):
        config = AIProviderConfig(
            provider="openai_responses",
            model="gpt-test",
            base_url="https://proxy.example/v1",
            api_key_configured=True,
            api_key_env_name="MINOS_OPENAI_API_KEY",
            responses_path="responses",
            reasoning_effort="medium",
        )

        def fake_urlopen(_request, timeout=0, context=None):
            content = (
                '{"rows":[{"characteristic_number":"P03-SC-01",'
                '"control_method":"过程控制"}]}\n'
                "原因判断：不确定。\n"
                "处理方案：重试。"
            )
            event = {
                "type": "response.output_text.delta",
                "delta": content,
            }
            raw = (
                "event: response.output_text.delta\n"
                f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            ).encode()
            return _StreamResponse(raw)

        with patch.dict(os.environ, {"MINOS_OPENAI_API_KEY": "secret"}, clear=True):
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                result = OpenAITextGenerator(config).generate_structured("system", "user")

        self.assertEqual(
            result,
            {
                "rows": [
                    {
                        "characteristic_number": "P03-SC-01",
                        "control_method": "过程控制",
                    }
                ]
            },
        )

    def test_generate_structured_reports_read_timeout_clearly(self):
        config = AIProviderConfig(
            provider="openai_responses",
            model="gpt-test",
            base_url="https://proxy.example/v1",
            api_key_configured=True,
            api_key_env_name="MINOS_OPENAI_API_KEY",
            responses_path="responses",
        )

        def fake_urlopen(_request, timeout=0, context=None):
            raise TimeoutError("The read operation timed out")

        with patch.dict(os.environ, {"MINOS_OPENAI_API_KEY": "secret"}, clear=True):
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                with self.assertRaises(RuntimeError) as raised:
                    OpenAITextGenerator(config).generate_structured("system", "user")

        message = str(raised.exception)
        self.assertIn("LLM Responses timed out after", message)
        self.assertIn("PFD/PFMEA/CP", message)

    def test_generate_structured_reports_stream_read_timeout_clearly(self):
        config = AIProviderConfig(
            provider="openai_responses",
            model="gpt-test",
            base_url="https://proxy.example/v1",
            api_key_configured=True,
            api_key_env_name="MINOS_OPENAI_API_KEY",
            responses_path="responses",
        )

        def fake_urlopen(_request, timeout=0, context=None):
            return _TimeoutStreamResponse()

        with patch.dict(os.environ, {"MINOS_OPENAI_API_KEY": "secret"}, clear=True):
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                with self.assertRaises(RuntimeError) as raised:
                    OpenAITextGenerator(config).generate_structured("system", "user")

        message = str(raised.exception)
        self.assertIn("LLM Responses timed out after", message)
        self.assertIn("PFD/PFMEA/CP", message)

    def test_http_error_does_not_include_response_body_or_api_key(self):
        config = AIProviderConfig(
            provider="openai_responses",
            model="gpt-test",
            base_url="https://proxy.example/v1",
            api_key_configured=True,
            api_key_env_name="MINOS_OPENAI_API_KEY",
            responses_path="responses",
        )

        def fake_urlopen(request, timeout=0, context=None):
            raise urllib.error.HTTPError(
                request.full_url,
                401,
                "Unauthorized",
                {},
                BytesIO(b'{"debug":"Bearer secret","message":"bad key"}'),
            )

        with patch.dict(os.environ, {"MINOS_OPENAI_API_KEY": "secret"}, clear=True):
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                with self.assertLogs("minos_core.adapters.llm_text", level="ERROR") as logs:
                    with self.assertRaises(RuntimeError) as raised:
                        OpenAITextGenerator(config).generate_structured("system", "user")

        message = str(raised.exception)
        logged = "\n".join(logs.output)
        self.assertIn("LLM Responses HTTP 401", message)
        self.assertNotIn("secret", message)
        self.assertNotIn("bad key", message)
        self.assertNotIn("secret", logged)
        self.assertNotIn("bad key", logged)

    def test_text_generation_defaults_to_medium_reasoning_when_codex_is_xhigh(self):
        config = AIProviderConfig(
            provider="openai_responses",
            model="gpt-test",
            base_url="https://proxy.example/v1",
            api_key_configured=True,
            api_key_env_name="MINOS_OPENAI_API_KEY",
            responses_path="responses",
            reasoning_effort="xhigh",
        )
        captured = {}

        def fake_urlopen(request, timeout=0, context=None):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            raw = (
                b'event: response.output_text.delta\n'
                b'data: {"type":"response.output_text.delta","delta":"{\\"ok\\": true}"}\n\n'
            )
            return _StreamResponse(raw)

        with patch.dict(os.environ, {"MINOS_OPENAI_API_KEY": "secret"}, clear=True):
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                OpenAITextGenerator(config).generate_structured("system", "user")

        self.assertEqual(captured["payload"]["reasoning"], {"effort": "medium"})

    def test_text_generation_reasoning_can_be_overridden_by_env(self):
        config = AIProviderConfig(
            provider="openai_responses",
            model="gpt-test",
            base_url="https://proxy.example/v1",
            api_key_configured=True,
            api_key_env_name="MINOS_OPENAI_API_KEY",
            responses_path="responses",
            reasoning_effort="xhigh",
        )
        captured = {}

        def fake_urlopen(request, timeout=0, context=None):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            raw = (
                b'event: response.output_text.delta\n'
                b'data: {"type":"response.output_text.delta","delta":"{\\"ok\\": true}"}\n\n'
            )
            return _StreamResponse(raw)

        with patch.dict(
            os.environ,
            {
                "MINOS_OPENAI_API_KEY": "secret",
                "MINOS_TEXT_LLM_REASONING_EFFORT": "medium",
            },
            clear=True,
        ):
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                OpenAITextGenerator(config).generate_structured("system", "user")

        self.assertEqual(captured["payload"]["reasoning"], {"effort": "medium"})

    def test_text_generation_retries_gateway_timeout(self):
        config = AIProviderConfig(
            provider="openai_responses",
            model="gpt-test",
            base_url="https://proxy.example/v1",
            api_key_configured=True,
            api_key_env_name="MINOS_OPENAI_API_KEY",
            responses_path="responses",
            reasoning_effort="medium",
        )
        attempts = {"count": 0}

        def fake_urlopen(_request, timeout=0, context=None):
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise urllib.error.HTTPError(
                    "https://proxy.example/v1/responses",
                    504,
                    "Gateway Time-out",
                    {},
                    None,
                )
            raw = (
                b'event: response.output_text.delta\n'
                b'data: {"type":"response.output_text.delta","delta":"{\\"ok\\": true}"}\n\n'
            )
            return _StreamResponse(raw)

        with patch.dict(os.environ, {"MINOS_OPENAI_API_KEY": "secret"}, clear=True):
            with patch("time.sleep", return_value=None):
                with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                    result = OpenAITextGenerator(config).generate_structured("system", "user")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(attempts["count"], 3)

    def test_text_generation_retries_stream_server_overloaded(self):
        config = AIProviderConfig(
            provider="openai_responses",
            model="gpt-test",
            base_url="https://proxy.example/v1",
            api_key_configured=True,
            api_key_env_name="MINOS_OPENAI_API_KEY",
            responses_path="responses",
            reasoning_effort="medium",
        )
        attempts = {"count": 0}

        def fake_urlopen(_request, timeout=0, context=None):
            attempts["count"] += 1
            if attempts["count"] < 3:
                raw = (
                    b'event: error\n'
                    b'data: {"type":"error","error":{"type":"service_unavailable_error",'
                    b'"code":"server_is_overloaded","message":"Our servers are currently '
                    b'overloaded. Please try again later."},"sequence_number":3}\n\n'
                )
                return _StreamResponse(raw)
            raw = (
                b'event: response.output_text.delta\n'
                b'data: {"type":"response.output_text.delta","delta":"{\\"ok\\": true}"}\n\n'
            )
            return _StreamResponse(raw)

        with patch.dict(os.environ, {"MINOS_OPENAI_API_KEY": "secret"}, clear=True):
            with patch("time.sleep", return_value=None):
                with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                    result = OpenAITextGenerator(config).generate_structured("system", "user")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(attempts["count"], 3)


if __name__ == "__main__":
    unittest.main()
