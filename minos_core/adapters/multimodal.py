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
from typing import Any, Protocol
from urllib.parse import urlparse

from minos_core.ai_config import (
    load_openai_api_key,
    load_openai_responses_config,
)
from minos_core.drawing_input import DrawingPageEvidence
from minos_core.drawing_visual_evidence import build_visual_evidence_regions


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
        self._last_visual_evidence_regions: list[dict[str, Any]] = []

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
                "visual_evidence_regions": [
                    dict(region) for region in self._last_visual_evidence_regions
                ],
            },
            reasoning=str(response.get("reasoning_text", "")),
        )

    def _responses_url(self) -> str:
        return f"{self.base_url}/{self.responses_path}"

    def _request_payload(
        self, pages: list[DrawingPageEvidence], context: dict[str, Any]
    ) -> dict[str, Any]:
        if _visual_task(context) == "special_characteristic_locator":
            return self._special_characteristic_locator_payload(pages, context)

        prompt_context = dict(context)
        prompt_context.setdefault(
            "available_drawing_page_evidence_ids",
            [page.evidence_id for page in pages],
        )
        visual_regions = _visual_evidence_regions_for_request(pages, prompt_context)
        self._last_visual_evidence_regions = [dict(region) for region in visual_regions]
        if visual_regions:
            prompt_context["visual_evidence_regions"] = [
                _public_visual_region(region) for region in visual_regions
            ]
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
        for region in visual_regions:
            content.append(
                {
                    "type": "input_text",
                    "text": (
                        "视觉证据裁剪 "
                        f"{region['region_id']}，label={region['label']}，"
                        f"bbox={region['bbox']}，evidence_refs={region['evidence_refs']}。"
                    ),
                }
            )
            content.append(
                {
                    "type": "input_image",
                    "image_url": _image_data_url(region["image_path"]),
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

    def _special_characteristic_locator_payload(
        self, pages: list[DrawingPageEvidence], context: dict[str, Any]
    ) -> dict[str, Any]:
        prompt_context = dict(context)
        prompt_context.setdefault(
            "available_drawing_page_evidence_ids",
            [page.evidence_id for page in pages],
        )
        visual_regions = _focused_special_characteristic_regions_for_request(
            pages, prompt_context
        )
        self._last_visual_evidence_regions = [dict(region) for region in visual_regions]
        if visual_regions:
            prompt_context["visual_evidence_regions"] = [
                _public_visual_region(region) for region in visual_regions
            ]
        content: list[dict[str, Any]] = [
            {
                "type": "input_text",
                "text": _special_characteristic_locator_prompt(prompt_context),
            }
        ]
        if visual_regions:
            for region in visual_regions:
                content.append(
                    {
                        "type": "input_text",
                        "text": (
                            "视觉证据裁剪 "
                            f"{region['region_id']}，label={region['label']}，"
                            f"bbox={region['bbox']}，evidence_refs={region['evidence_refs']}。"
                        ),
                    }
                )
                content.append(
                    {
                        "type": "input_image",
                        "image_url": _image_data_url(region["image_path"]),
                        "detail": "high",
                    }
                )
        else:
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
            "input": [{"role": "user", "content": content}],
        }
        if self.store is not None:
            payload["store"] = self.store
        if self.reasoning_effort:
            payload["reasoning"] = {"effort": self.reasoning_effort}
        if self.json_schema is not None:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "drawing_special_characteristic_locator",
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


def create_default_multimodal_drawing_analyzer() -> MultimodalDrawingAnalyzer:
    return OpenAIResponsesMultimodalDrawingAnalyzer()


def _drawing_analysis_prompt(context: dict[str, Any]) -> str:
    context_text = json.dumps(context, ensure_ascii=False, sort_keys=True)
    visual_locator_instruction = _special_characteristic_visual_locator_instruction(context)
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
        "必需顶层 JSON 键还包括：declared_special_characteristics, declared_totals, "
        "located_occurrences, special_characteristic_candidates, special_characteristic_locations, "
        "missing_counts, focused_review_requests。"
        f"{visual_locator_instruction}"
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


def _special_characteristic_visual_locator_instruction(context: dict[str, Any]) -> str:
    count_clause = _special_characteristic_count_clause(context)
    return (
        "你同时承担 GPT5.5 visual locator 角色。"
        f"{count_clause}"
        "如果输入中包含 visual_evidence_regions，请优先查看标题栏、产品特殊特性表、"
        "技术要求总区和逐条技术要求裁剪；输出 evidence_refs 时可引用对应 region_id。"
        "必须先根据图例确认 CC/SC 符号形状，再在整页图中定位符号落点。"
        "不要为了满足 declared_totals 凑数；带圈数字、普通序号、条款编号本身不是 "
        "CC/SC 分类证据，只有与图例形状一致并能绑定到具体要求时才可作为候选。"
        "如果声明有 SC 但未找到可靠 SC，请优先复核技术要求或尺寸区域中含"
        "转动力矩、操作力矩、torque、0.5~2.5Nm 等力矩功能要求的行，"
        "找不到时继续保留 missing_counts.SC，不要把第5/6条编号误当 SC。"
        "每个 located_occurrences 项必须包含 candidate_id, candidate_type, source, "
        "symbol_text_or_shape, linked_feature, symbol_bbox, linked_feature_bbox, "
        "evidence_refs, confidence, reasoning；source 必须写 gpt55_visual_locator。"
        "located_occurrences 只是候选证据，不能直接写成最终 special_characteristics；"
        "最终确认只能交给 evidence judge 或人工确认。"
        "如果 located_occurrences 数量少于 declared_totals，必须输出 missing_counts，"
        "并在 focused_review_requests 中写明缺少类别和需要复核的区域。"
    )


def _special_characteristic_count_clause(context: dict[str, Any]) -> str:
    totals = {"CC": 0, "SC": 0}
    for key in ("ocr_analysis_summary", "special_characteristic_discovery_request"):
        source = context.get(key)
        if not isinstance(source, dict):
            continue
        declared_totals = source.get("declared_totals")
        if not isinstance(declared_totals, dict):
            continue
        for classification in ("CC", "SC"):
            totals[classification] = max(
                totals[classification],
                _non_negative_count(declared_totals.get(classification)),
            )

    count_clause = (
        f"OCR/MinerU 已给出 declared_totals：CC={totals['CC']}，SC={totals['SC']}。"
        if totals["CC"] > 0 or totals["SC"] > 0
        else "如果标题栏、图例或产品特殊特性表声明 CC/SC 数量，也必须输出 declared_totals。"
    )
    return count_clause


SPECIAL_CHARACTERISTIC_LOCATOR_OUTPUT_KEYS = (
    "declared_special_characteristics",
    "declared_totals",
    "located_occurrences",
    "special_characteristic_candidates",
    "special_characteristic_locations",
    "missing_counts",
    "focused_review_requests",
)


def _special_characteristic_locator_context(context: dict[str, Any]) -> dict[str, Any]:
    summary = context.get("ocr_analysis_summary")
    summary_dict = summary if isinstance(summary, dict) else {}
    discovery = context.get("special_characteristic_discovery_request")
    discovery_dict = discovery if isinstance(discovery, dict) else {}
    visual_regions = context.get("visual_evidence_regions")
    requirements = [
        _special_locator_requirement_hint(item)
        for item in summary_dict.get("technical_requirements", [])
        if isinstance(item, dict)
    ]
    requirements = [item for item in requirements if item][:8]
    return {
        "available_drawing_page_evidence_ids": context.get(
            "available_drawing_page_evidence_ids", []
        ),
        "declared_totals": _best_special_locator_totals(
            discovery_dict.get("declared_totals"),
            summary_dict.get("declared_totals"),
        ),
        "declared_special_characteristics": [
            dict(item)
            for item in discovery_dict.get("declared_special_characteristics", [])
            if isinstance(item, dict)
        ][:8],
        "technical_requirement_hints": requirements,
        "visual_evidence_regions": visual_regions
        if isinstance(visual_regions, list)
        else [],
        "special_characteristic_locator_scope": context.get(
            "special_characteristic_locator_scope",
            "title_block,key_product_characteristic_table,technical_requirements",
        ),
    }


def _best_special_locator_totals(*values: Any) -> dict[str, int]:
    totals = {"CC": 0, "SC": 0}
    for value in values:
        if not isinstance(value, dict):
            continue
        for classification in ("CC", "SC"):
            totals[classification] = max(
                totals[classification],
                _non_negative_count(value.get(classification)),
            )
    return totals


def _special_locator_requirement_hint(item: dict[str, Any]) -> dict[str, Any]:
    text = str(item.get("text") or item.get("source_text") or "").strip()
    if not text:
        return {}
    return {
        "text": text[:240],
        "evidence_refs": [
            str(ref)
            for ref in item.get("evidence_refs", [])
            if str(ref).strip()
        ][:4]
        if isinstance(item.get("evidence_refs"), list)
        else [],
    }


def _visual_task(context: dict[str, Any]) -> str:
    return str(context.get("visual_task") or "").strip().lower()


def _special_characteristic_locator_prompt(context: dict[str, Any]) -> str:
    locator_context = _special_characteristic_locator_context(context)
    context_text = json.dumps(locator_context, ensure_ascii=False, sort_keys=True)
    count_clause = _special_characteristic_count_clause(context)
    keys = ", ".join(SPECIAL_CHARACTERISTIC_LOCATOR_OUTPUT_KEYS)
    return (
        "你现在只做一个任务：识别图纸中的 CC/SC 特殊特性声明和候选位置。"
        "不要生成 PFD、PFMEA、CP，不要抽取材料、尺寸、公差、工序或完整图纸分析。"
        f"{count_clause}"
        "只阅读输入中的标题栏/特殊特性数量区域、产品特殊特性表区域、技术要求区域，"
        "以及必要的技术要求行裁剪。"
        "带圈数字、普通序号、条款编号本身不是 CC/SC；只有与图例符号或明确 CC/SC 标识一致，"
        "并且能绑定到具体要求文本时，才输出候选。"
        "特别注意含转动力矩、操作力矩、torque、0.5~2.5Nm 的功能要求行；"
        "也要注意 GB15086/GB 15086、Q/BJORV M 0102 等客户/法规要求是否带 CC 标识。"
        "只返回合法 JSON，不要 Markdown。"
        f"只允许返回这些顶层键：{keys}。"
        "标题栏、图例或产品特殊特性数量表中的声明行只能写入 "
        "declared_special_characteristics 和 declared_totals；"
        "不能把声明行、数量行、图例行本身写入 located_occurrences、"
        "special_characteristic_candidates 或 special_characteristic_locations。"
        "located_occurrences 只允许写已经绑定到具体技术要求、尺寸、功能或法规条款的候选。"
        "located_occurrences 和 special_characteristic_candidates 中每项必须包含："
        "candidate_id, candidate_type, source, symbol_text_or_shape, linked_feature, "
        "symbol_bbox, linked_feature_bbox, evidence_refs, confidence, reasoning。"
        "candidate_type 只能是 CC、SC 或 unknown；source 必须是 gpt55_visual_locator。"
        "不要把候选直接写入 special_characteristics；最终确认交给 judge 或人工。"
        "如果标题栏、图例或产品特殊特性表声明 CC/SC 数量，必须输出 declared_totals。"
        "如果没有找到足够候选，必须输出 missing_counts 和 focused_review_requests。"
        "上下文："
        f"{context_text}"
    )


def _non_negative_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _visual_evidence_regions_for_request(
    pages: list[DrawingPageEvidence],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    summary = context.get("ocr_analysis_summary")
    if not isinstance(summary, dict):
        return []
    requirements = [
        item for item in summary.get("technical_requirements", []) if isinstance(item, dict)
    ]
    regions: list[dict[str, Any]] = []
    for page in pages:
        page_regions = build_visual_evidence_regions(
            page_image_path=page.image_path,
            page_evidence_id=page.evidence_id,
            technical_requirements=requirements,
        )
        regions.extend(
            region for region in page_regions if region.get("label") != "full_page"
        )
    return regions


def _focused_special_characteristic_regions_for_request(
    pages: list[DrawingPageEvidence],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    summary = context.get("ocr_analysis_summary")
    requirements = []
    if isinstance(summary, dict):
        requirements = [
            item for item in summary.get("technical_requirements", []) if isinstance(item, dict)
        ]
    allowed_labels = {
        "title_block_special_counts",
        "key_product_characteristic_table",
        "technical_requirements",
    }
    detail = str(
        context.get("special_characteristic_locator_detail") or "broad"
    ).strip().lower()
    if detail == "detailed":
        allowed_labels.update(
            {
                "technical_requirement_line_001",
                "technical_requirement_line_002",
                "technical_requirement_line_003",
                "technical_requirement_line_004",
            }
        )
    regions: list[dict[str, Any]] = []
    for page in pages:
        page_regions = build_visual_evidence_regions(
            page_image_path=page.image_path,
            page_evidence_id=page.evidence_id,
            technical_requirements=requirements,
        )
        regions.extend(
            region
            for region in page_regions
            if str(region.get("label") or "") in allowed_labels
        )
    return regions


def _public_visual_region(region: dict[str, Any]) -> dict[str, Any]:
    return {
        key: region[key]
        for key in ("region_id", "page_evidence_id", "label", "bbox", "evidence_refs")
        if key in region
    }


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
        except TimeoutError as exc:
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
