"""UI-neutral state objects for the MINOS desktop sidecar."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DesktopProjectState:
    project_name: str = "MINOS 三表项目"
    drawing_path: str = ""
    component_drawings: list[str] = field(default_factory=list)
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
    responses_path: str = "responses"
    base_url_override: str = ""
    api_key_override_set: bool = False
    model_override: str = ""
    base_url_locked_by_env: bool = False
    api_key_locked_by_env: bool = False
    model_locked_by_env: bool = False


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
class StageConfirmState:
    """单个链式阶段的确认状态。"""
    status: str = "not_started"  # not_started | running | generated | confirmed | blocked | failed
    generated_at: str = ""
    confirmed_at: str = ""
    confirmed_by: str = ""
    row_count: int = 0
    pending_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "generated_at": self.generated_at,
            "confirmed_at": self.confirmed_at,
            "confirmed_by": self.confirmed_by,
            "row_count": self.row_count,
            "pending_count": self.pending_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StageConfirmState:
        return cls(
            status=data.get("status", "not_started"),
            generated_at=data.get("generated_at", ""),
            confirmed_at=data.get("confirmed_at", ""),
            confirmed_by=data.get("confirmed_by", ""),
            row_count=data.get("row_count", 0),
            pending_count=data.get("pending_count", 0),
        )


@dataclass(frozen=True)
class ChainStageStates:
    """链式三阶段确认状态聚合。"""
    pfd: StageConfirmState = field(default_factory=StageConfirmState)
    pfmea: StageConfirmState = field(default_factory=StageConfirmState)
    cp: StageConfirmState = field(default_factory=StageConfirmState)
    pipeline_mode: str = "batch"  # "batch" | "chain"

    @property
    def current_stage(self) -> str:
        """当前活跃的阶段名。"""
        if self.cp.status == "confirmed":
            return "complete"
        if self.pfmea.status == "confirmed":
            return "cp"
        if self.pfd.status == "confirmed":
            return "pfmea"
        if self.pfd.status in ("generated", "running"):
            return "pfd"
        return "pfd"

    def to_dict(self) -> dict[str, Any]:
        return {
            "pfd": self.pfd.to_dict(),
            "pfmea": self.pfmea.to_dict(),
            "cp": self.cp.to_dict(),
            "pipeline_mode": self.pipeline_mode,
            "current_stage": self.current_stage,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChainStageStates:
        return cls(
            pfd=StageConfirmState.from_dict(data.get("pfd", {})),
            pfmea=StageConfirmState.from_dict(data.get("pfmea", {})),
            cp=StageConfirmState.from_dict(data.get("cp", {})),
            pipeline_mode=data.get("pipeline_mode", "batch"),
        )


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
    chain_stages: ChainStageStates | None = None


@dataclass(frozen=True)
class DesktopProjectRecord:
    id: int
    project_name: str
    drawing_path: str
    output_dir: str
    context: dict[str, Any]
    created_at: str
    updated_at: str
    component_drawings: tuple[str, ...] = ()


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
