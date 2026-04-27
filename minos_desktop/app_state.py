"""UI-neutral state objects for the MINOS desktop shell."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DesktopPage:
    key: str
    title: str


DESKTOP_PAGES: tuple[DesktopPage, ...] = (
    DesktopPage("project", "项目"),
    DesktopPage("drawing_import", "图纸导入"),
    DesktopPage("drawing_analysis", "AI 识别结果"),
    DesktopPage("pfd", "PFD 草案"),
    DesktopPage("pfmea", "PFMEA 草案"),
    DesktopPage("control_plan", "CP 草案"),
    DesktopPage("actions", "措施管理"),
    DesktopPage("change_impacts", "变更影响"),
    DesktopPage("knowledge", "知识库推荐"),
    DesktopPage("automation_review", "AI 预审"),
    DesktopPage("review", "人工复核"),
    DesktopPage("export", "导出"),
    DesktopPage("settings", "设置"),
)


@dataclass
class DesktopProjectState:
    project_name: str = "MINOS 三表项目"
    drawing_path: str = ""
    output_dir: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    def ensure_output_dir(self) -> Path:
        target = Path(self.output_dir or "out/desktop")
        target.mkdir(parents=True, exist_ok=True)
        self.output_dir = str(target)
        return target


@dataclass(frozen=True)
class DesktopAIConfigState:
    provider: str = "openai_responses"
    model: str = ""
    model_configured: bool = False
    model_source: str = ""
    base_url: str = ""
    base_url_configured: bool = False
    base_url_source: str = ""
    api_key_configured: bool = False
    api_key_source: str = ""
    api_key_env_name: str = ""
    wire_api: str = "responses"
    responses_path: str = "v1/responses"


@dataclass(frozen=True)
class DesktopExportRecord:
    name: str
    path: str


@dataclass(frozen=True)
class GenerationRunSummary:
    status: str
    status_display: str
    blocked_stage: str
    exports: dict[str, str]
    manifest_path: str
    manual_review_required: bool
    manual_review_count: int
    manual_review_raw_count: int


@dataclass(frozen=True)
class DesktopRunState:
    status: str
    status_display: str
    blocked_stage: str
    exports: tuple[DesktopExportRecord, ...]
    manifest_path: str
    manifest_run_id: str
    manual_review_required: bool
    manual_review_count: int
    manual_review_raw_count: int
    manual_review_items: tuple[Any, ...] = ()


@dataclass(frozen=True)
class DesktopProjectRecord:
    id: int
    project_name: str
    drawing_path: str
    output_dir: str
    context: dict[str, Any]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class DesktopRunRecord:
    id: int
    project_id: int | None
    state: DesktopRunState
    output_dir: str
    raw_result: dict[str, Any]
    failure_message: str
    created_at: str
    original_result: dict[str, Any] = field(default_factory=dict)
    current_result: dict[str, Any] = field(default_factory=dict)
    edit_patch: dict[str, Any] = field(default_factory=dict)


def summarize_generation_result(result: dict[str, Any]) -> GenerationRunSummary:
    manual_review = result.get("manual_review") if isinstance(result, dict) else {}
    items = manual_review.get("items", []) if isinstance(manual_review, dict) else []
    raw_count = manual_review.get("raw_count", None) if isinstance(manual_review, dict) else None
    manifest = result.get("manifest") if isinstance(result, dict) else {}
    exports = result.get("exports") if isinstance(result, dict) else {}
    status = str(result.get("status", "")) if isinstance(result, dict) else ""
    status_display = (
        str(result.get("status_display") or _status_display(status))
        if isinstance(result, dict)
        else ""
    )
    return GenerationRunSummary(
        status=status,
        status_display=status_display,
        blocked_stage=str(result.get("blocked_stage") or "") if isinstance(result, dict) else "",
        exports={str(key): str(value) for key, value in exports.items()}
        if isinstance(exports, dict)
        else {},
        manifest_path=str(manifest.get("path", "")) if isinstance(manifest, dict) else "",
        manual_review_required=bool(manual_review.get("required", False))
        if isinstance(manual_review, dict)
        else False,
        manual_review_count=len(items) if isinstance(items, list) else 0,
        manual_review_raw_count=int(raw_count)
        if isinstance(raw_count, int)
        else len(items)
        if isinstance(items, list)
        else 0,
    )


def desktop_run_state_from_result(result: dict[str, Any]) -> DesktopRunState:
    summary = summarize_generation_result(result)
    manifest = result.get("manifest") if isinstance(result, dict) else {}
    manual_review = result.get("manual_review") if isinstance(result, dict) else {}
    items = manual_review.get("items", []) if isinstance(manual_review, dict) else []
    return DesktopRunState(
        status=summary.status,
        status_display=summary.status_display,
        blocked_stage=summary.blocked_stage,
        exports=tuple(
            DesktopExportRecord(name=name, path=path)
            for name, path in sorted(summary.exports.items())
        ),
        manifest_path=summary.manifest_path,
        manifest_run_id=str(manifest.get("run_id", "")) if isinstance(manifest, dict) else "",
        manual_review_required=summary.manual_review_required,
        manual_review_count=summary.manual_review_count,
        manual_review_raw_count=summary.manual_review_raw_count,
        manual_review_items=tuple(items) if isinstance(items, list) else (),
    )


def _status_display(status: str) -> str:
    return {
        "draft_ready": "草案已就绪",
        "needs_review": "待人工复核",
        "blocked": "已阻断",
        "failed": "失败",
    }.get(status, status)
