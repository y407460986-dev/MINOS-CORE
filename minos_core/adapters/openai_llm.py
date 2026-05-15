"""OpenAI Chat Completions API adapter for text LLM tasks.

Consumes the same configuration sources as the multimodal adapter
(``ai_config.load_openai_api_key`` and ``ai_config.load_openai_responses_config``)
so a single set of environment variables or Codex files drives both paths.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from minos_core.adapters.llm import LLMMessage, LLMResult
from minos_core.ai_config import load_openai_api_key, load_openai_responses_config


class OpenAILLMError(RuntimeError):
    """Raised when the OpenAI Chat Completions API call cannot complete."""


class OpenAILLMAdapter:
    """OpenAI Chat Completions API adapter for text-only LLM tasks.

    Configuration is intentionally environment-driven so API keys never live in
    source files. Supported variables:

    - ``MINOS_OPENAI_API_KEY``, ``OPENAI_API_KEY``, or ``ARK_API_KEY``
    - ``MINOS_OPENAI_BASE_URL``, ``OPENAI_BASE_URL``, or ``ARK_BASE_URL``
    - ``MINOS_OPENAI_MODEL``, ``OPENAI_MODEL``, or ``ARK_MODEL``
    - ``MINOS_OPENAI_REASONING_EFFORT``, ``OPENAI_REASONING_EFFORT``, or
      ``ARK_REASONING_EFFORT``
    - if environment variables are absent, Codex ``~/.codex/config.toml``
      and ``~/.codex/auth.json`` may be used without exposing the key.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        timeout: int = 120,
        max_retries: int = 2,
        retry_delay: float = 1.0,
    ) -> None:
        config = load_openai_responses_config()
        self.api_key = api_key if api_key is not None else load_openai_api_key()
        base_url_value = (base_url or config.base_url).rstrip("/")

        # Validate base_url must use HTTPS to protect API key
        if not base_url_value.startswith("https://"):
            raise ValueError(
                f"base_url must use HTTPS to protect API key, got: {base_url_value}"
            )

        self.base_url = base_url_value
        self.model = model or config.model
        self.reasoning_effort = (
            reasoning_effort if reasoning_effort is not None else config.reasoning_effort
        )
        self.user_agent = config.user_agent
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.retry_delay = max(0.0, float(retry_delay))

    # -- public API -----------------------------------------------------------

    def complete(self, messages: list[LLMMessage]) -> LLMResult:
        """Generate a text completion from structured messages.

        Calls ``POST /v1/chat/completions`` with the configured model and
        returns the first choice's message content wrapped in an
        ``LLMResult``.
        """
        if not self.api_key:
            raise OpenAILLMError(
                "OpenAI API key is not configured. "
                "See documentation for configuration instructions."
            )
        payload = self._build_payload(messages)
        response = self._post_json(self._chat_url(), payload)
        return self._parse_result(response)

    def complete_structured(
        self,
        messages: list[LLMMessage],
        json_schema: dict[str, Any] | None = None,
    ) -> LLMResult:
        """Generate a completion that is constrained to JSON.

        When *json_schema* is provided the request uses
        ``response_format`` with ``json_schema`` strict mode; otherwise it
        uses the simpler ``json_object`` mode.
        """
        if not self.api_key:
            raise OpenAILLMError(
                "OpenAI API key is not configured. "
                "See documentation for configuration instructions."
            )
        payload = self._build_payload(messages, structured=True, json_schema=json_schema)
        response = self._post_json(self._chat_url(), payload)
        result = self._parse_result(response)
        metadata: dict[str, Any] = dict(result.metadata)
        metadata["response_format"] = "json_schema" if json_schema else "json_object"
        return LLMResult(content=result.content, model=result.model, metadata=metadata)

    # -- internal helpers ----------------------------------------------------

    def _chat_url(self) -> str:
        return f"{self.base_url}/v1/chat/completions"

    def _build_payload(
        self,
        messages: list[LLMMessage],
        structured: bool = False,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if structured:
            if json_schema:
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "response",
                        "schema": json_schema,
                        "strict": True,
                    },
                }
            else:
                payload["response_format"] = {"type": "json_object"}
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        return payload

    @staticmethod
    def _parse_result(response: dict[str, Any]) -> LLMResult:
        choice = response["choices"][0]
        content = choice["message"]["content"]
        return LLMResult(
            content=content,
            model=str(response.get("model", "")),
            metadata={
                "usage": response.get("usage", {}),
                "finish_reason": choice.get("finish_reason", ""),
            },
        )

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        request_body = json.dumps(payload).encode("utf-8")
        attempts = self.max_retries + 1
        for attempt in range(1, attempts + 1):
            request = urllib.request.Request(
                url,
                data=request_body,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": self.user_agent,
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                if attempt < attempts and _should_retry_http_status(exc.code):
                    time.sleep(self.retry_delay * attempt)
                    continue
                # Do not include response body (may contain sensitive information)
                raise OpenAILLMError(
                    f"OpenAI Chat Completions API failed after {attempt} attempt(s): "
                    f"HTTP {exc.code}"
                ) from exc
            except urllib.error.URLError as exc:
                if attempt < attempts:
                    time.sleep(self.retry_delay * attempt)
                    continue
                raise OpenAILLMError(
                    f"OpenAI Chat Completions API connection failed after "
                    f"{attempt} attempt(s): {exc}"
                ) from exc
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OpenAILLMError(
                f"OpenAI Chat Completions API returned invalid JSON: {exc}"
            ) from exc
        if not isinstance(parsed, dict):
            raise OpenAILLMError("OpenAI Chat Completions API returned non-object JSON")
        return parsed


def _should_retry_http_status(status_code: int) -> bool:
    return status_code in {429, 500, 502, 503, 504}
