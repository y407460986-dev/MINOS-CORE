"""Chain orchestration helpers extracted from run_service.py."""
from __future__ import annotations

from typing import Any

from ..table_editor import EDIT_PATCH_VERSION
from .run_edit_helpers import _normalize_three_table_result


def _guess_failure_reason(message: str) -> str:
    lowered = message.lower()
    if "mineru" in lowered and (
        "all connection attempts failed" in lowered
        or "mineru-api" in lowered
        or "processing documents" in lowered
    ):
        return "MinerU 本地解析服务连接失败，OCR 后处理没有正常收尾。"
    if "504" in lowered or "gateway time-out" in lowered or "gateway timeout" in lowered:
        return "AI 上游模型或中转服务响应超时。"
    if "timed out" in lowered or "timeout" in lowered:
        return "AI 模型响应超时或网络链路过慢。"
    if "references unknown evidence" in lowered or "unknown evidence" in lowered:
        return "AI 引用了不存在的图纸页面证据，通常是模型页码引用和实际渲染页数不一致。"
    if "api" in lowered or "key" in lowered:
        return "AI 配置可能缺失或不可用。"
    if "permission" in lowered or "access is denied" in lowered:
        return "输出目录或输入文件可能没有访问权限。"
    if "not found" in lowered or "no such file" in lowered:
        return "输入文件或运行依赖的路径可能不存在。"
    return "不确定。"


def _default_failure_actions(message: str) -> list[str]:
    lowered = message.lower()
    if "mineru" in lowered and (
        "all connection attempts failed" in lowered
        or "mineru-api" in lowered
        or "processing documents" in lowered
    ):
        return [
            "重试图纸识别；如果已有 OCR 输出，MINOS 会优先复用可读结果。",
            "如果连续失败，检查 MinerU 运行时、模型资源和本机显存/内存占用。",
            "放弃任务。",
        ]
    if "504" in lowered or "gateway time-out" in lowered or "gateway timeout" in lowered:
        return [
            "稍后重试失效模式分析生成；当前 PFD 已保留。",
            "如果连续失败，降低文本模型推理强度或切换更稳定的 AI 服务。",
            "放弃任务。",
        ]
    return [
        "检查图纸路径、输出目录权限和 AI 配置后重试。",
        "保留当前项目记录，修正输入后重新运行。",
        "放弃任务。",
    ]


def _status_display(status: str) -> str:
    return {
        "draft_ready": "草案已就绪",
        "needs_review": "待人工复核",
        "blocked": "已阻断",
        "failed": "失败",
    }.get(status, status)


def format_desktop_failure(
    error: BaseException | str,
    *,
    reason: str | None = None,
    actions: list[str] | None = None,
) -> str:
    raw = str(error)
    reason_text = reason or _guess_failure_reason(raw)
    action_items = actions or _default_failure_actions(raw)
    if not any("放弃任务" in item for item in action_items):
        action_items.append("放弃任务。")
    return "\n".join(
        [
            f"原始错误：{raw}",
            f"原因判断：{reason_text}",
            "处理方案：",
            *[f"{index}. {item}" for index, item in enumerate(action_items, start=1)],
        ]
    )


def _desktop_result_envelope(
    raw_result: dict[str, Any],
    *,
    current_result: dict[str, Any] | None = None,
    edit_patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_raw = _normalize_three_table_result(raw_result)
    normalized_current = (
        _normalize_three_table_result(current_result)
        if current_result is not None
        else normalized_raw
    )
    return {
        "_desktop_storage_version": 1,
        "raw_result": normalized_raw,
        "current_result": normalized_current,
        "edit_patch": edit_patch
        if edit_patch is not None
        else {"edit_patch_version": EDIT_PATCH_VERSION, "items": []},
    }
