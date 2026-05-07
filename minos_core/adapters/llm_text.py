"""Responses API text LLM adapter used by the staged PFD/PFMEA/CP chain."""

from __future__ import annotations

import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request
from typing import Any

from minos_core.ai_config import (
    AIProviderConfig,
    load_openai_api_key,
    load_openai_responses_config,
)
from minos_core.adapters.multimodal import _extract_output_text

logger = logging.getLogger(__name__)

_DEFAULT_MAX_TOKENS = 4096
_DEFAULT_TIMEOUT_SECONDS = 240


class OpenAITextGenerator:
    """Text-only Responses API caller with JSON-schema constrained output."""

    def __init__(self, config: AIProviderConfig | None = None):
        if config is None:
            config = load_openai_responses_config()
        self._config = config
        self._api_key = load_openai_api_key()
        self._base_url = config.base_url.rstrip("/")
        self._responses_path = config.responses_path.strip("/")
        self._reasoning_effort = _text_reasoning_effort(config.reasoning_effort)
        self._user_agent = config.user_agent
        self._timeout_seconds = _text_timeout_seconds()
        if config.wire_api != "responses":
            raise RuntimeError(
                f"unsupported Codex/OpenAI wire_api for text generator: {config.wire_api}"
            )

    @property
    def model(self) -> str:
        return self._config.model

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: dict | None = None,
        model: str | None = None,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """调用 Responses API 生成结构化 JSON 输出。"""
        model_name = model or self.model
        logger.info("LLM text: model=%s max_tokens=%d", model_name, max_tokens)

        if not self._api_key:
            raise RuntimeError("OpenAI API key is not configured for text generation")

        payload: dict[str, Any] = {
            "model": model_name,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_prompt}],
                },
            ],
            "max_output_tokens": max_tokens,
        }
        if temperature is not None and not self._reasoning_effort:
            payload["temperature"] = temperature
        if self._config.store is not None:
            payload["store"] = self._config.store
        if self._reasoning_effort:
            payload["reasoning"] = {"effort": self._reasoning_effort}
        if response_format:
            payload["text"] = {"format": _responses_text_format(response_format)}
        else:
            payload["text"] = {"format": {"type": "json_object"}}

        body = self._post_json(self._responses_url(), payload)
        content = _extract_output_text(body)
        if not content:
            raise RuntimeError("LLM returned empty response")

        return _parse_json_content(content)

    def _responses_url(self) -> str:
        return f"{self._base_url}/{self._responses_path}"

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        attempts = 3
        for attempt in range(1, attempts + 1):
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": self._user_agent,
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self._timeout_seconds) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except (TimeoutError, socket.timeout) as exc:
                raise RuntimeError(_timeout_message(self._timeout_seconds)) from exc
            except urllib.error.HTTPError as exc:
                err_body = exc.read().decode("utf-8", errors="replace")
                if attempt < attempts and exc.code in {429, 500, 502, 503}:
                    time.sleep(attempt)
                    continue
                logger.error("LLM Responses HTTP %d: %s", exc.code, err_body[:500])
                raise RuntimeError(f"LLM Responses HTTP {exc.code}: {err_body[:300]}") from exc
            except urllib.error.URLError as exc:
                if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                    raise RuntimeError(_timeout_message(self._timeout_seconds)) from exc
                if attempt < attempts:
                    time.sleep(attempt)
                    continue
                raise RuntimeError(f"LLM Responses connection failed: {exc}") from exc
        raise RuntimeError("LLM Responses call exhausted retries")


def _responses_text_format(response_format: dict[str, Any]) -> dict[str, Any]:
    if response_format.get("type") != "json_schema":
        return dict(response_format)
    schema_payload = response_format.get("json_schema")
    if not isinstance(schema_payload, dict):
        raise RuntimeError("json_schema response_format must contain json_schema object")
    return {
        "type": "json_schema",
        "name": str(schema_payload.get("name") or "response"),
        "schema": schema_payload.get("schema") or {},
        "strict": bool(schema_payload.get("strict", True)),
    }


def _parse_json_content(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("LLM didn't return pure JSON, trying to extract...")
        if "```json" in content:
            block = content.split("```json", 1)[1].split("```", 1)[0]
            parsed = json.loads(block)
        elif "```" in content:
            block = content.split("```", 1)[1].split("```", 1)[0]
            parsed = json.loads(block)
        else:
            raise RuntimeError(
                f"无法解析 LLM 输出为 JSON (前500字): {content[:500]}"
            )
    if not isinstance(parsed, dict):
        raise RuntimeError("LLM JSON response must be an object")
    return parsed


def _text_timeout_seconds() -> int:
    raw = os.getenv("MINOS_TEXT_LLM_TIMEOUT_SECONDS") or os.getenv(
        "MINOS_OPENAI_TEXT_TIMEOUT_SECONDS"
    )
    if not raw:
        return _DEFAULT_TIMEOUT_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_TIMEOUT_SECONDS
    return value if value > 0 else _DEFAULT_TIMEOUT_SECONDS


def _text_reasoning_effort(configured_effort: str) -> str:
    override = os.getenv("MINOS_TEXT_LLM_REASONING_EFFORT") or os.getenv(
        "MINOS_OPENAI_TEXT_REASONING_EFFORT"
    )
    if override:
        return override
    return "medium" if configured_effort else ""


def _timeout_message(timeout_seconds: int) -> str:
    return (
        f"LLM Responses timed out after {timeout_seconds} second(s) while generating "
        "PFD/PFMEA/CP JSON. 文本模型响应超时，请检查模型/中转服务是否过慢，"
        "或通过 MINOS_TEXT_LLM_TIMEOUT_SECONDS 调整超时时间后重试。"
    )
