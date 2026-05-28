"""Multimodal drawing analyzer adapter boundary."""

from __future__ import annotations

import base64
import json
import mimetypes
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from socket import timeout as SocketTimeout
from typing import Any, Protocol
from urllib.parse import urlparse

from minos_core.ai_config import load_openai_api_key, load_openai_responses_config
from minos_core.drawing_input import DrawingPageEvidence


@dataclass(frozen=True)
class MultimodalDrawingResult:
    content: str
    model: str = "fake"
    metadata: dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""


class MultimodalDrawingAnalyzer(Protocol):
    def analyze_drawing_pages(
        self,
        pages: list[DrawingPageEvidence],
        context: dict[str, Any] | None = None,
    ) -> MultimodalDrawingResult:
        """Analyze drawing page images and return structured JSON text."""
        ...


class NotConfiguredMultimodalDrawingAnalyzer:
    def analyze_drawing_pages(
        self,
        pages: list[DrawingPageEvidence],
        context: dict[str, Any] | None = None,
    ) -> MultimodalDrawingResult:
        raise NotImplementedError("multimodal drawing analyzer is not configured")


class FakeMultimodalDrawingAnalyzer:
    def __init__(self, content: str = "") -> None:
        self.content = content

    def analyze_drawing_pages(
        self,
        pages: list[DrawingPageEvidence],
        context: dict[str, Any] | None = None,
    ) -> MultimodalDrawingResult:
        return MultimodalDrawingResult(
            content=self.content,
            model="fake",
            metadata={
                "page_count": len(pages),
                "context_keys": sorted((context or {}).keys()),
            },
        )


class OpenAIMultimodalError(RuntimeError):
    """Raised when the OpenAI Responses drawing analyzer cannot complete."""


def _create_ssl_context() -> ssl.SSLContext:
    """Create SSL context with certificate verification.

    SECURITY FIX v3.1.0: Enables certificate validation for HTTPS requests.
    """
    context = ssl.create_default_context()
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


class OpenAIResponsesMultimodalDrawingAnalyzer:
    """OpenAI Responses API implementation for drawing analysis.

    Configuration is intentionally environment-driven so API keys never live in
    source files. Supported variables:

    - ``MINOS_OPENAI_API_KEY``, ``OPENAI_API_KEY``, or ``ARK_API_KEY``
    - ``MINOS_OPENAI_BASE_URL``, ``OPENAI_BASE_URL``, or ``ARK_BASE_URL``
    - ``MINOS_OPENAI_MODEL``, ``OPENAI_MODEL``, or ``ARK_MODEL``
    - if environment variables are absent, Codex ``~/.codex/config.toml``
      and ``~/.codex/auth.json`` may be used without exposing the key.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        responses_path: str | None = None,
        timeout: int = 120,
        max_retries: int = 2,
        retry_delay: float = 1.0,
        json_mode: bool = True,
        json_schema: dict[str, Any] | None = None,
    ) -> None:
        config = load_openai_responses_config()
        if config.wire_api != "responses":
            raise OpenAIMultimodalError(
                f"unsupported Codex/OpenAI wire_api for drawing analyzer: {config.wire_api}"
            )
        self.api_key = api_key if api_key is not None else load_openai_api_key()
        base_url_value = (base_url or config.base_url).rstrip("/")

        # SECURITY FIX v3.1.0: Validate HTTPS and setup SSL context
        parsed = urlparse(base_url_value)
        if parsed.scheme != "https":
            if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
                self._ssl_context = None  # No SSL for localhost
            else:
                raise OpenAIMultimodalError(
                    f"base_url must use HTTPS to protect API key, got: {base_url_value}"
                )
        else:
            self._ssl_context = _create_ssl_context()

        self.base_url = base_url_value
        self.model = model or config.model
        self.responses_path = (responses_path or config.responses_path).strip("/")
        self.store = config.store
        self.reasoning_effort = config.reasoning_effort
        self.user_agent = config.user_agent
        self.json_mode = json_mode
        self.json_schema = json_schema
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.retry_delay = max(0.0, float(retry_delay))

    def analyze_drawing_pages(
        self,
        pages: list[DrawingPageEvidence],
        context: dict[str, Any] | None = None,
    ) -> MultimodalDrawingResult:
        if not self.api_key:
            raise OpenAIMultimodalError(
                "OpenAI API key is not configured. "
                "See documentation for configuration instructions."
            )
        if not pages:
            raise OpenAIMultimodalError("drawing analysis requires at least one page")

        payload = self._request_payload(pages, context or {})
        response = self._post_json(self._responses_url(), payload)
        content = _extract_output_text(response)
        if not content:
            raise OpenAIMultimodalError("OpenAI response did not contain output text")
        return MultimodalDrawingResult(
            content=content,
            model=str(response.get("model", self.model)),
            metadata={
                "response_id": response.get("id"),
                "usage": response.get("usage", {}),
                "page_count": len(pages),
            },
            reasoning=str(response.get("reasoning_text", "")),
        )

    def _responses_url(self) -> str:
        return f"{self.base_url}/{self.responses_path}"

    def _request_payload(
        self, pages: list[DrawingPageEvidence], context: dict[str, Any]
    ) -> dict[str, Any]:
        prompt_context = dict(context)
        prompt_context.setdefault(
            "available_drawing_page_evidence_ids",
            [page.evidence_id for page in pages],
        )
        content: list[dict[str, Any]] = [
            {
                "type": "input_text",
                "text": _drawing_analysis_prompt(prompt_context),
            }
        ]
        for page in pages:
            content.append(
                {
                    "type": "input_image",
                    "image_url": _image_data_url(page.image_path),
                    "detail": "high",
                }
            )
        payload: dict[str, Any] = {
            "model": self.model,
            "input": [
                {
                    "role": "user",
                    "content": content,
                }
            ],
        }
        if self.store is not None:
            payload["store"] = self.store
        if self.reasoning_effort:
            payload["reasoning"] = {"effort": self.reasoning_effort}
        if self.json_schema is not None:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "drawing_analysis",
                    "schema": self.json_schema,
                    "strict": True,
                }
            }
        elif self.json_mode:
            payload["text"] = {"format": {"type": "json_object"}}
        payload["stream"] = True
        return payload

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
                # SECURITY FIX v3.1.0: Use SSL context for certificate verification
                if self._ssl_context:
                    with urllib.request.urlopen(request, timeout=self.timeout, context=self._ssl_context) as response:
                        if payload.get("stream") is True:
                            return _parse_responses_stream(
                                response,
                                fallback_model=self.model,
                                timeout_seconds=self.timeout,
                            )
                        raw = response.read().decode("utf-8")
                else:
                    with urllib.request.urlopen(request, timeout=self.timeout) as response:
                        if payload.get("stream") is True:
                            return _parse_responses_stream(
                                response,
                                fallback_model=self.model,
                                timeout_seconds=self.timeout,
                            )
                        raw = response.read().decode("utf-8")
                break
            except urllib.error.HTTPError as exc:
                exc.read()
                if attempt < attempts and _should_retry_http_status(exc.code):
                    time.sleep(self.retry_delay * attempt)
                    continue
                raise OpenAIMultimodalError(
                    f"OpenAI Responses API failed after {attempt} attempt(s): HTTP {exc.code}"
                ) from exc
            except urllib.error.URLError as exc:
                if attempt < attempts:
                    time.sleep(self.retry_delay * attempt)
                    continue
                raise OpenAIMultimodalError(
                    f"OpenAI Responses API connection failed after {attempt} attempt(s): {exc}"
                ) from exc
            except TimeoutError as exc:
                if attempt < attempts:
                    time.sleep(self.retry_delay * attempt)
                    continue
                raise OpenAIMultimodalError(
                    f"OpenAI Responses API timed out after {self.timeout:g} second(s)"
                ) from exc
            except OpenAIMultimodalError as exc:
                if attempt < attempts and is_retryable_responses_stream_error(str(exc)):
                    time.sleep(self.retry_delay * attempt)
                    continue
                raise
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OpenAIMultimodalError(f"OpenAI Responses API returned invalid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise OpenAIMultimodalError("OpenAI Responses API returned non-object JSON")
        return parsed


def _drawing_analysis_prompt(context: dict[str, Any]) -> str:
    context_text = json.dumps(context, ensure_ascii=False, sort_keys=True)
    return (
        "你是一名汽车行业 APQP/PPAP 制造工程师。请分析图纸图片，并且只返回 MINOS "
        "drawing_analysis_bundle 字段所需的合法 JSON，不要输出 Markdown。所有给用户看的业务内容"
        "必须使用中文，包括零件名称、材料说明、技术要求、检验要求、制造工序、推理说明和不确定项；"
        "标准缩写如 PFD、PFMEA、CP、SC 可以保留。每个抽取项都必须包含 evidence_refs，引用"
        " drawing_page_001 这类页面证据编号。如果某个值不确定，请写入 uncertainties，或设置"
        " needs_confirmation=true 且 confidence 低于 0.75。必需顶层 JSON 键包括："
        "drawing_identity, materials, surface_treatments, dimensions, tolerances, "
        "special_characteristics, technical_requirements, inspection_requirements, "
        "manufacturing_clues, uncertainties。manufacturing_clues 中优先返回明确的有序工序，"
        "例如 operation/process_step/process_sequence，并带 evidence_refs。不要在可以推断"
        "具体工序时只返回一段说明文字。需要通用工序名时，请使用中文且具体的名称，例如："
        "落料、冲孔、折弯、焊接、去毛刺、电镀、注塑、修边、装配、过程检验、最终检验、包装。"
        "识别顺序必须先读图框/标题栏，再看技术要求、BOM、局部标注和视图细节。"
        "drawing_identity.part_name 必须优先来自图框/标题栏中的整件名称；局部组件名、"
        "引出标注、BOM 子件、技术要求中的对象不能覆盖整张图纸的零件名。例如图框写"
        "“尾门铰链/尾门较链/door hinge/DH ASSY”，即使技术要求提到衬套、销轴或润滑，"
        "part_name 仍应是尾门铰链，衬套等只进入 technical_requirements、"
        "special_characteristics 或 manufacturing_clues。"
        "判断零件族时请区分：门铰链通常包含铰链臂/铰链座/铰链销/旋转力矩/开闭角度；"
        "限位器通常包含限位臂、限位杆、滚轮、弹簧、档位力或保持力；"
        "冲压件通常是薄板成形件，含落料、冲孔、翻边、加强筋、SPCC/DC01 等线索。"
        "上下文："
        f"{context_text}"
    )


def _image_data_url(path: str) -> str:
    image_path = Path(path)
    media_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def _extract_output_text(response: dict[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct

    fragments: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content_item in item.get("content", []):
            if not isinstance(content_item, dict):
                continue
            text = content_item.get("text")
            if isinstance(text, str):
                fragments.append(text)
    return "\n".join(fragment for fragment in fragments if fragment).strip()


def _should_retry_http_status(status_code: int) -> bool:
    return status_code in {429, 500, 502, 503, 504}


def is_retryable_responses_stream_error(message: str) -> bool:
    lower = message.lower()
    return any(
        marker in lower
        for marker in (
            "server_is_overloaded",
            "service_unavailable",
            "temporarily unavailable",
            "try again later",
            "rate_limit",
            "stream_read_error",
        )
    )


def _parse_responses_stream(
    response: Any,
    *,
    fallback_model: str = "",
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    event_name = ""
    data_lines: list[str] = []
    deltas: list[str] = []
    reasoning_deltas: list[str] = []
    completed_response: dict[str, Any] | None = None
    started_at = time.monotonic()

    def dispatch() -> None:
        nonlocal event_name, data_lines, completed_response
        if not data_lines:
            event_name = ""
            return
        raw_data = "\n".join(data_lines).strip()
        current_event_name = event_name
        event_name = ""
        data_lines = []
        if not raw_data or raw_data == "[DONE]":
            return
        try:
            payload = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            raise OpenAIMultimodalError(
                f"OpenAI Responses API stream returned invalid JSON event: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            return
        event_type = str(payload.get("type") or current_event_name)
        if event_type == "response.output_text.delta":
            delta = payload.get("delta")
            if isinstance(delta, str):
                deltas.append(delta)
        elif event_type == "response.output_text.done":
            text = payload.get("text")
            if isinstance(text, str):
                deltas.append(text)
        elif event_type == "response.reasoning_text.delta":
            delta = payload.get("delta")
            if isinstance(delta, str):
                reasoning_deltas.append(delta)
        elif event_type == "response.reasoning_text.done":
            text = payload.get("text")
            if isinstance(text, str):
                reasoning_deltas.append(text)
        elif event_type == "response.output_item.done":
            text = _extract_output_text({"output": [payload.get("item")]})
            if text:
                deltas.append(text)
        elif event_type == "response.content_part.done":
            text = _extract_content_part_text(payload.get("part"))
            if text:
                deltas.append(text)
        elif event_type in {"response.completed", "response.done"}:
            response_payload = payload.get("response")
            if isinstance(response_payload, dict):
                completed_response = response_payload
        elif event_type in {"response.failed", "error"}:
            raise OpenAIMultimodalError(
                f"OpenAI Responses API stream failed: {json.dumps(payload, ensure_ascii=False)}"
            )

    while True:
        if timeout_seconds is not None and time.monotonic() - started_at > timeout_seconds:
            raise OpenAIMultimodalError(
                f"OpenAI Responses API stream timed out after {timeout_seconds:g} second(s)"
            )
        try:
            line = response.readline()
        except (TimeoutError, SocketTimeout) as exc:
            raise OpenAIMultimodalError(
                f"OpenAI Responses API stream timed out after {timeout_seconds or 0:g} second(s)"
            ) from exc
        if not line:
            dispatch()
            break
        text = line.decode("utf-8", errors="replace").rstrip("\r\n")
        if not text:
            dispatch()
            continue
        if text.startswith("event:"):
            event_name = text.split(":", 1)[1].strip()
        elif text.startswith("data:"):
            data_lines.append(text.split(":", 1)[1].lstrip())

    if completed_response is not None:
        if deltas and not _extract_output_text(completed_response):
            completed_response = dict(completed_response)
            completed_response["output_text"] = "".join(deltas)
        if reasoning_deltas and "reasoning_text" not in completed_response:
            completed_response = dict(completed_response)
            completed_response["reasoning_text"] = "".join(reasoning_deltas)
        return completed_response
    text = "".join(deltas).strip()
    if text:
        result: dict[str, Any] = {
            "object": "response",
            "model": fallback_model,
            "output_text": text,
            "streamed": True,
        }
        reasoning = "".join(reasoning_deltas).strip()
        if reasoning:
            result["reasoning_text"] = reasoning
        return result
    raise OpenAIMultimodalError("OpenAI Responses API stream did not contain output text")


def _extract_content_part_text(part: Any) -> str:
    if not isinstance(part, dict):
        return ""
    text = part.get("text")
    return text if isinstance(text, str) else ""
