import json
import os
import unittest
import urllib.error
from io import BytesIO
from unittest.mock import patch

from minos_core.adapters.llm import LLMAdapter, LLMMessage, LLMResult
from minos_core.adapters.openai_llm import (
    OpenAILLMAdapter,
    OpenAILLMError,
    _should_retry_http_status,
)


class _FakeResponse:
    """A minimal file-like object that emulates urlopen's context manager."""

    def __init__(self, payload: dict, status: int = 200) -> None:
        self._payload = payload
        self.status = status

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class ProtocolConformanceTests(unittest.TestCase):
    def test_openai_llm_adapter_satisfies_llm_adapter_protocol(self):
        """OpenAILLMAdapter has a ``complete`` method matching the protocol."""
        self.assertTrue(hasattr(OpenAILLMAdapter, "complete"))
        self.assertTrue(callable(getattr(OpenAILLMAdapter, "complete")))

    def test_fake_llm_adapter_satisfies_llm_adapter_protocol(self):
        """Existing FakeLLMAdapter also satisfies the protocol."""
        from minos_core.adapters.llm import FakeLLMAdapter

        self.assertTrue(hasattr(FakeLLMAdapter, "complete"))


# ---------------------------------------------------------------------------
# API key check (no network)
# ---------------------------------------------------------------------------


class APIKeyCheckTests(unittest.TestCase):
    def test_raises_when_api_key_empty(self):
        with patch.dict(os.environ, {"MINOS_DISABLE_CODEX_CONFIG": "1"}, clear=True):
            adapter = OpenAILLMAdapter(api_key="", model="gpt-test")

            with self.assertRaisesRegex(OpenAILLMError, "API key is not configured"):
                adapter.complete([LLMMessage(role="user", content="hello")])

    def test_raises_when_api_key_empty_for_structured(self):
        with patch.dict(os.environ, {"MINOS_DISABLE_CODEX_CONFIG": "1"}, clear=True):
            adapter = OpenAILLMAdapter(api_key="", model="gpt-test")

            with self.assertRaisesRegex(OpenAILLMError, "API key is not configured"):
                adapter.complete_structured(
                    [LLMMessage(role="user", content="hello")]
                )


# ---------------------------------------------------------------------------
# Request payload construction
# ---------------------------------------------------------------------------


class PayloadConstructionTests(unittest.TestCase):
    def setUp(self):
        self.adapter = OpenAILLMAdapter(
            api_key="test-key",
            base_url="https://proxy.example",
            model="gpt-test",
            reasoning_effort="medium",
        )

    def test_basic_payload_has_model_and_messages(self):
        messages = [
            LLMMessage(role="system", content="You are helpful."),
            LLMMessage(role="user", content="Say hi."),
        ]
        payload = self.adapter._build_payload(messages)

        self.assertEqual(payload["model"], "gpt-test")
        self.assertEqual(len(payload["messages"]), 2)
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["messages"][0]["content"], "You are helpful.")
        self.assertEqual(payload["messages"][1]["role"], "user")
        self.assertEqual(payload["messages"][1]["content"], "Say hi.")
        self.assertEqual(payload["reasoning_effort"], "medium")

    def test_basic_payload_no_reasoning_effort_when_empty(self):
        adapter = OpenAILLMAdapter(api_key="test-key", model="gpt-test", reasoning_effort="")
        payload = adapter._build_payload([LLMMessage(role="user", content="hi")])

        self.assertNotIn("reasoning_effort", payload)

    def test_structured_payload_json_object_mode(self):
        payload = self.adapter._build_payload(
            [LLMMessage(role="user", content="Return JSON")],
            structured=True,
        )

        self.assertEqual(payload["response_format"], {"type": "json_object"})

    def test_structured_payload_json_schema_mode(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        payload = self.adapter._build_payload(
            [LLMMessage(role="user", content="Who are you?")],
            structured=True,
            json_schema=schema,
        )

        self.assertEqual(payload["response_format"]["type"], "json_schema")
        self.assertEqual(payload["response_format"]["json_schema"]["name"], "response")
        self.assertEqual(
            payload["response_format"]["json_schema"]["schema"]["properties"]["name"]["type"],
            "string",
        )
        self.assertIs(payload["response_format"]["json_schema"]["strict"], True)

    def test_chat_url_construction(self):
        self.assertEqual(
            self.adapter._chat_url(),
            "https://proxy.example/v1/chat/completions",
        )

    def test_chat_url_strips_trailing_slash(self):
        adapter = OpenAILLMAdapter(
            api_key="test-key",
            base_url="https://proxy.example/",
            model="gpt-test",
        )
        self.assertEqual(
            adapter._chat_url(),
            "https://proxy.example/v1/chat/completions",
        )


# ---------------------------------------------------------------------------
# Result parsing
# ---------------------------------------------------------------------------


class ResultParsingTests(unittest.TestCase):
    def test_parse_result_extracts_content_and_usage(self):
        response = {
            "model": "gpt-test",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "Hello!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        result = OpenAILLMAdapter._parse_result(response)

        self.assertEqual(result.content, "Hello!")
        self.assertEqual(result.model, "gpt-test")
        self.assertEqual(result.metadata["usage"]["total_tokens"], 15)
        self.assertEqual(result.metadata["finish_reason"], "stop")


# ---------------------------------------------------------------------------
# HTTP success path
# ---------------------------------------------------------------------------


class HTTPSuccessTests(unittest.TestCase):
    def test_complete_makes_request_and_returns_result(self):
        adapter = OpenAILLMAdapter(
            api_key="test-key",
            base_url="https://proxy.example",
            model="gpt-test",
        )

        fake_api_response = {
            "model": "gpt-test",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "Hello, user!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }

        def fake_urlopen(request, timeout=0):
            self.assertIn("Authorization", request.headers)
            self.assertEqual(request.headers["Authorization"], "Bearer test-key")
            self.assertEqual(request.headers["Content-type"], "application/json")
            return _FakeResponse(fake_api_response)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = adapter.complete(
                [LLMMessage(role="user", content="Say hello")]
            )

        self.assertEqual(result.content, "Hello, user!")
        self.assertEqual(result.model, "gpt-test")
        self.assertEqual(result.metadata["usage"]["total_tokens"], 8)

    def test_complete_structured_sends_response_format(self):
        adapter = OpenAILLMAdapter(
            api_key="test-key",
            base_url="https://proxy.example",
            model="gpt-test",
        )

        fake_api_response = {
            "model": "gpt-test",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": '{"name": "MINOS"}',
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
        }

        captured_payload: dict = {}

        def fake_urlopen(request, timeout=0):
            nonlocal captured_payload
            captured_payload = json.loads(request.data.decode("utf-8"))
            return _FakeResponse(fake_api_response)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = adapter.complete_structured(
                [LLMMessage(role="user", content="What is the project name?")],
                json_schema={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            )

        # Verify the request sent the right payload
        self.assertEqual(captured_payload["model"], "gpt-test")
        self.assertEqual(captured_payload["response_format"]["type"], "json_schema")
        self.assertEqual(
            captured_payload["response_format"]["json_schema"]["schema"]["required"],
            ["name"],
        )
        self.assertIs(
            captured_payload["response_format"]["json_schema"]["strict"],
            True,
        )

        # Verify the result
        self.assertEqual(result.content, '{"name": "MINOS"}')
        self.assertEqual(result.metadata["response_format"], "json_schema")
        self.assertEqual(result.metadata["usage"]["total_tokens"], 12)


# ---------------------------------------------------------------------------
# Error handling and retries
# ---------------------------------------------------------------------------


class ErrorHandlingTests(unittest.TestCase):
    def setUp(self):
        self.adapter = OpenAILLMAdapter(
            api_key="test-key",
            base_url="https://proxy.example",
            model="gpt-test",
            retry_delay=0,
        )

    def test_retries_transient_http_error_then_succeeds(self):
        calls = {"count": 0}

        def fake_urlopen(request, timeout=0):
            calls["count"] += 1
            if calls["count"] == 1:
                raise urllib.error.HTTPError(
                    request.full_url,
                    503,
                    "Service unavailable",
                    hdrs=None,
                    fp=BytesIO(b'{"error":{"message":"temporary"}}'),
                )
            return _FakeResponse(
                {
                    "model": "gpt-test",
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": "ok"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = self.adapter.complete(
                [LLMMessage(role="user", content="ping")]
            )

        self.assertEqual(calls["count"], 2)
        self.assertEqual(result.content, "ok")

    def test_retries_connection_error_then_succeeds(self):
        calls = {"count": 0}

        def fake_urlopen(request, timeout=0):
            calls["count"] += 1
            if calls["count"] == 1:
                raise urllib.error.URLError("connection refused")
            return _FakeResponse(
                {
                    "model": "gpt-test",
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": "recovered"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
                }
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = self.adapter.complete(
                [LLMMessage(role="user", content="hi")]
            )

        self.assertEqual(calls["count"], 2)
        self.assertEqual(result.content, "recovered")

    def test_exhausts_retries_on_http_error_then_raises(self):
        adapter = OpenAILLMAdapter(
            api_key="test-key",
            base_url="https://proxy.example",
            model="gpt-test",
            max_retries=1,
            retry_delay=0,
        )

        def fake_urlopen(request, timeout=0):
            raise urllib.error.HTTPError(
                request.full_url,
                500,
                "Internal error",
                hdrs=None,
                fp=BytesIO(b'{"error":{"message":"crash"}}'),
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with self.assertRaisesRegex(OpenAILLMError, "failed after 2 attempt"):
                adapter.complete([LLMMessage(role="user", content="x")])

    def test_no_retry_on_client_error(self):
        adapter = OpenAILLMAdapter(
            api_key="test-key",
            base_url="https://proxy.example",
            model="gpt-test",
            max_retries=2,
            retry_delay=0,
        )
        calls = {"count": 0}

        def fake_urlopen(request, timeout=0):
            calls["count"] += 1
            raise urllib.error.HTTPError(
                request.full_url,
                400,
                "Bad request",
                hdrs=None,
                fp=BytesIO(b'{"error":{"message":"invalid"}}'),
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with self.assertRaisesRegex(OpenAILLMError, "failed after 1 attempt"):
                adapter.complete([LLMMessage(role="user", content="x")])

        self.assertEqual(calls["count"], 1)

    def test_raises_on_invalid_json_response(self):
        def fake_urlopen(request, timeout=0):
            return _FakeResponseRaw(b"not json at all")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with self.assertRaisesRegex(OpenAILLMError, "invalid JSON"):
                self.adapter._post_json(
                    self.adapter._chat_url(),
                    {"model": "gpt-test", "messages": []},
                )


class _FakeResponseRaw:
    """Returns raw bytes for testing malformed responses."""

    def __init__(self, raw: bytes) -> None:
        self._raw = raw

    def read(self) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------


class RetryHelperTests(unittest.TestCase):
    def test_retry_status_helper(self):
        self.assertTrue(_should_retry_http_status(429))
        self.assertTrue(_should_retry_http_status(500))
        self.assertTrue(_should_retry_http_status(502))
        self.assertTrue(_should_retry_http_status(503))
        self.assertTrue(_should_retry_http_status(504))
        self.assertFalse(_should_retry_http_status(200))
        self.assertFalse(_should_retry_http_status(400))
        self.assertFalse(_should_retry_http_status(401))
        self.assertFalse(_should_retry_http_status(403))
        self.assertFalse(_should_retry_http_status(404))


if __name__ == "__main__":
    unittest.main()
