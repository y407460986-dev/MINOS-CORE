import json
import os
import unittest
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

        def fake_urlopen(request, timeout=0):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return _Response({"output_text": '{"ok": true}'})

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

    def test_generate_structured_reports_read_timeout_clearly(self):
        config = AIProviderConfig(
            provider="openai_responses",
            model="gpt-test",
            base_url="https://proxy.example/v1",
            api_key_configured=True,
            api_key_env_name="MINOS_OPENAI_API_KEY",
            responses_path="responses",
        )

        def fake_urlopen(_request, timeout=0):
            raise TimeoutError("The read operation timed out")

        with patch.dict(os.environ, {"MINOS_OPENAI_API_KEY": "secret"}, clear=True):
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                with self.assertRaises(RuntimeError) as raised:
                    OpenAITextGenerator(config).generate_structured("system", "user")

        message = str(raised.exception)
        self.assertIn("LLM Responses timed out after", message)
        self.assertIn("PFD/PFMEA/CP", message)

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

        def fake_urlopen(request, timeout=0):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return _Response({"output_text": '{"ok": true}'})

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

        def fake_urlopen(request, timeout=0):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return _Response({"output_text": '{"ok": true}'})

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


if __name__ == "__main__":
    unittest.main()
