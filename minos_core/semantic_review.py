"""Semantic validation checks for AI-generated APQP drafts.

Pure functions: input dicts -> output strings/dicts. No file I/O, no API calls.
Conservative keyword matching (English + Chinese); false positives preferred over
false negatives for safety checks.
"""

from __future__ import annotations

import math
import re
from typing import Any

# ---------------------------------------------------------------------------
# Keyword sets
# ---------------------------------------------------------------------------

_VISUAL_FAILURE_KEYWORDS = [
    "外观", "划伤", "划痕", "碰伤", "碰痕", "毛刺", "飞边", "缺料",
    "缩水", "变形", "色差", "脏污", "油污", "锈蚀", "氧化", "斑点",
    "气泡", "裂纹", "拉伤", "压伤", "凹坑", "凸起", "流痕", "熔接痕",
    "scratch", "dent", "burr", "flash", "deform", "stain", "rust",
    "discoloration", "crack", "pit", "bubble", "visual", "cosmetic",
    "appearance", "表面",
]

_DIMENSIONAL_FAILURE_KEYWORDS = [
    "尺寸", "公差", "直径", "长度", "宽度", "高度", "厚度", "深度",
    "间距", "位置度", "平面度", "平行度", "垂直度", "同轴度", "圆度",
    "圆柱度", "跳动", "轮廓度", "dimension", "tolerance", "diameter",
    "length", "width", "height", "thickness", "depth", "position",
    "flatness", "parallelism", "perpendicularity", "concentricity",
    "roundness", "cylindricity", "runout", "profile",
]

_VISUAL_DETECTION_KEYWORDS = [
    "目视", "目检", "外观检查", "外观检验", "visual", "目测",
    "外观检测", "肉眼", "看", "查看",
]

_MEASUREMENT_DETECTION_KEYWORDS = [
    "卡尺", "千分尺", "三坐标", "CMM", "投影仪", "高度规", "塞尺",
    "量规", "通止规", "检具", "测量", "计量", "测试", "检测仪",
    "caliper", "micrometer", "cmm", "gauge", "measure", "test",
    "meter", "probe", "laser", "光学", "影像仪", "轮廓仪",
]

_IGNORE_DETECTION_KEYWORDS = {
    "防错", "poka", "error proof", "防呆", "互锁", "interlock",
    "传感器", "sensor", "PLC", "自动检测", "auto check",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize(text: Any) -> str:
    """Strip, lowercase, collapse whitespace."""
    return " ".join(str(text).strip().lower().split())


def _to_float(value: Any) -> float | None:
    """Convert to float, returning None for empty or non-numeric."""
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _any_keyword_hit(text: str, keywords: list[str]) -> bool:
    """Return True if any keyword appears in the normalized text."""
    t = _normalize(text)
    return any(kw in t for kw in keywords)


def _get_field(row: dict[str, Any], *names: str) -> Any:
    """Return the value of the first named field that is not None in the row.

    Unlike ``row.get(a) or row.get(b)``, this correctly returns 0, False, and
    empty strings when those are set explicitly.
    """
    for name in names:
        val = row.get(name)
        if val is not None:
            return val
    return None


# ---------------------------------------------------------------------------
# Single-row checks
# ---------------------------------------------------------------------------


def check_rpn_arithmetic(row: dict[str, Any]) -> list[str]:
    """Verify S * O * D == RPN. Returns issue messages if mismatch.

    Handles both English field names (severity, occurrence, detection, rpn)
    and Chinese/alternative names (S, O, D, RPN, 严重度, 频度, 探测度).
    """
    issues: list[str] = []

    severity = _to_float(_get_field(row, "severity", "S", "严重度"))
    occurrence = _to_float(_get_field(row, "occurrence", "O", "频度"))
    detection = _to_float(_get_field(row, "detection", "D", "探测度"))
    rpn = _to_float(_get_field(row, "rpn", "RPN"))

    if severity is None or occurrence is None or detection is None:
        # Cannot compute RPN at all; skip arithmetic check, but flag missing values
        missing = []
        if severity is None:
            missing.append("S/severity")
        if occurrence is None:
            missing.append("O/occurrence")
        if detection is None:
            missing.append("D/detection")
        if missing:
            row_id = _normalize(
                row.get("pfmea_id") or row.get("id") or row.get("item_id") or "?"
            )
            issues.append(
                f"[{row_id}] 无法验证 RPN 运算：缺少 {'，'.join(missing)}"
            )
        return issues

    if rpn is None:
        row_id = _normalize(
            row.get("pfmea_id") or row.get("id") or row.get("item_id") or "?"
        )
        issues.append(f"[{row_id}] RPN 值为空，无法验证 S×O×D 运算")
        return issues

    expected_rpn = severity * occurrence * detection
    if not math.isclose(expected_rpn, rpn, rel_tol=1e-9, abs_tol=0.01):
        row_id = _normalize(
            row.get("pfmea_id") or row.get("id") or row.get("item_id") or "?"
        )
        issues.append(
            f"[{row_id}] RPN 算术错误：S({severity})×O({occurrence})×D({detection})"
            f" = {expected_rpn}，但记录值为 {rpn}"
        )
    return issues


def check_cause_effect_logic(row: dict[str, Any]) -> list[str]:
    """Check failure_cause, failure_mode, failure_effect are not identical.

    In a valid FMEA, the cause, mode, and effect should be distinct concepts.
    Identical or near-identical text suggests the AI copy-pasted without reasoning.
    """
    issues: list[str] = []

    cause = _normalize(
        row.get("failure_cause") or row.get("失效原因") or ""
    )
    mode = _normalize(
        row.get("failure_mode") or row.get("失效模式") or ""
    )
    effect = _normalize(
        row.get("failure_effect") or row.get("失效后果") or row.get("失效影响") or ""
    )

    if not cause or not mode or not effect:
        # Cannot evaluate if any are missing
        return issues

    pairs = [
        ("失效原因(failure_cause)", "失效模式(failure_mode)", cause, mode),
        ("失效原因(failure_cause)", "失效后果(failure_effect)", cause, effect),
        ("失效模式(failure_mode)", "失效后果(failure_effect)", mode, effect),
    ]

    for label_a, label_b, text_a, text_b in pairs:
        if text_a == text_b:
            row_id = _normalize(
                row.get("pfmea_id")
                or row.get("id")
                or row.get("item_id")
                or "?"
            )
            issues.append(
                f"[{row_id}] PFMEA 逻辑可疑：{label_a} 与 {label_b} 内容相同"
                f"（'{text_a}'），三者应互不相同以形成因果链"
            )

    return issues


def check_detection_vs_failure_type(row: dict[str, Any]) -> list[str]:
    """Check detection control appropriateness vs failure mode type.

    - Visual failure modes (外观划伤 etc.) should include visual inspection.
    - Dimensional failure modes (尺寸超差 etc.) should include measurement.
    - Detection methods that are "ignored" (防错, sensor, Poka-yoke) are skipped.
    """
    issues: list[str] = []

    failure_mode = _normalize(
        row.get("failure_mode") or row.get("失效模式") or ""
    )
    detection_control = _normalize(
        row.get("detection_control") or row.get("探测控制") or row.get("detection_method") or ""
    )

    if not failure_mode or not detection_control:
        return issues

    # Skip if detection method is in the ignore set (防错, sensor, etc.)
    if _any_keyword_hit(detection_control, list(_IGNORE_DETECTION_KEYWORDS)):
        return issues

    is_visual_failure = _any_keyword_hit(failure_mode, _VISUAL_FAILURE_KEYWORDS)
    is_dimensional_failure = _any_keyword_hit(failure_mode, _DIMENSIONAL_FAILURE_KEYWORDS)

    if is_visual_failure:
        if not _any_keyword_hit(detection_control, _VISUAL_DETECTION_KEYWORDS):
            row_id = _normalize(
                row.get("pfmea_id")
                or row.get("id")
                or row.get("item_id")
                or "?"
            )
            issues.append(
                f"[{row_id}] 探测方法可能不匹配：故障模式含外观类关键词"
                f"（'{_normalize(failure_mode)}'），但探测控制"
                f"（'{detection_control}'）未包含目视检查方法"
            )

    if is_dimensional_failure:
        if not _any_keyword_hit(detection_control, _MEASUREMENT_DETECTION_KEYWORDS):
            row_id = _normalize(
                row.get("pfmea_id")
                or row.get("id")
                or row.get("item_id")
                or "?"
            )
            issues.append(
                f"[{row_id}] 探测方法可能不匹配：故障模式含尺寸类关键词"
                f"（'{_normalize(failure_mode)}'），但探测控制"
                f"（'{detection_control}'）未包含测量/计量方法"
            )

    return issues


def check_measurement_vs_tolerance(row: dict[str, Any]) -> list[str]:
    """Check CP measurement method is appropriate for tolerance precision.

    Tight tolerances (<= ±0.05 mm) should not use visual-only inspection.
    """
    issues: list[str] = []

    tolerance = _normalize(
        row.get("tolerance") or row.get("spec_tolerance") or row.get("公差") or ""
    )
    measurement_method = _normalize(
        row.get("measurement_method")
        or row.get("detection_control")
        or row.get("评价方法")
        or row.get("检测方法")
        or ""
    )
    characteristic = _normalize(
        row.get("characteristic") or row.get("产品特性") or row.get("控制特性") or ""
    )

    if not tolerance or not measurement_method:
        return issues

    # Extract the tightest tolerance value from spec string like "±0.01" or "10±0.05"
    tol_match = re.search(r"[±±]\s*([\d.]+)", tolerance)
    if not tol_match:
        tol_match = re.search(r"([\d.]+)\s*(?:mm|毫米)?\s*$", tolerance)
        # Try symmetric patterns like "0.01" alone
        if not tol_match:
            tol_match = re.search(r"([\d.]+)", tolerance)

    if not tol_match:
        return issues

    tol_value = float(tol_match.group(1))

    # Tight tolerance threshold: 0.05 mm or tighter
    if tol_value > 0.05:
        return issues

    # Check if measurement is purely visual (no measurement instrument)
    has_measurement = _any_keyword_hit(measurement_method, _MEASUREMENT_DETECTION_KEYWORDS)
    has_visual_only = _any_keyword_hit(measurement_method, _VISUAL_DETECTION_KEYWORDS) and not has_measurement
    is_ignored = _any_keyword_hit(measurement_method, list(_IGNORE_DETECTION_KEYWORDS))

    if is_ignored:
        return issues

    if has_visual_only:
        row_id = _normalize(
            row.get("control_plan_id")
            or row.get("pfmea_id")
            or row.get("id")
            or row.get("item_id")
            or "?"
        )
        characteristic_info = f"（特性：{characteristic}）" if characteristic else ""
        issues.append(
            f"[{row_id}] 测量精度可能不足：公差为 ±{tol_value}mm"
            f"（≤0.05mm 精密公差），但检测方法为目视检查"
            f"（'{measurement_method}'）{characteristic_info}"
        )

    return issues


# ---------------------------------------------------------------------------
# Cross-table checks
# ---------------------------------------------------------------------------


def check_cross_table_step_name_consistency(
    pfd_steps: list[dict[str, Any]],
    pfmea_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Check step name consistency between PFD and PFMEA.

    Compares operation names from PFD steps with the process_step / operation
    field on PFMEA rows that share the same process_step_id.

    Returns list of issue dicts with item_id, category, message, severity.
    """
    issues: list[dict[str, Any]] = []

    if not pfd_steps or not pfmea_rows:
        return issues

    # Build lookup: process_step_id -> operation name from PFD
    pfd_by_step_id: dict[str, str] = {}
    for step in pfd_steps:
        if not isinstance(step, dict):
            continue
        sid = str(step.get("process_step_id", "")).strip()
        if not sid:
            continue
        op_name = _normalize(
            step.get("operation") or step.get("process_name") or step.get("step_name") or ""
        )
        if op_name:
            pfd_by_step_id[sid] = op_name

    # Also build by sequence number as fallback
    pfd_by_seq: dict[int, str] = {}
    for step in pfd_steps:
        if not isinstance(step, dict):
            continue
        seq = step.get("sequence") or step.get("step_no")
        if seq is None:
            continue
        try:
            seq_i = int(seq)
        except (TypeError, ValueError):
            continue
        op_name = _normalize(
            step.get("operation") or step.get("process_name") or step.get("step_name") or ""
        )
        if op_name:
            pfd_by_seq[seq_i] = op_name

    for row in pfmea_rows:
        if not isinstance(row, dict):
            continue
        pfmea_step_name = _normalize(
            row.get("process_step") or row.get("operation") or row.get("工序") or ""
        )
        if not pfmea_step_name:
            continue

        pfmea_id = str(
            row.get("pfmea_id") or row.get("id") or row.get("item_id") or ""
        ).strip()
        step_id = str(row.get("process_step_id", "")).strip()

        # Try matching by process_step_id first
        if step_id and step_id in pfd_by_step_id:
            pfd_name = pfd_by_step_id[step_id]
            if pfmea_step_name != pfd_name:
                issues.append({
                    "item_id": pfmea_id or f"pfmea-{step_id}",
                    "category": "cross_table_consistency",
                    "message": (
                        f"PFD 与 PFMEA 工序名称不一致："
                        f"PFD 工序 '{pfd_name}'（step_id={step_id}）"
                        f" vs PFMEA 工序 '{pfmea_step_name}'（{pfmea_id}）"
                    ),
                    "severity": "review",
                })
            continue

        # Fallback: try matching by sequence number
        seq_val = row.get("sequence") or row.get("step_no")
        if seq_val is not None:
            try:
                seq_i = int(seq_val)
            except (TypeError, ValueError):
                seq_i = None
            if seq_i is not None and seq_i in pfd_by_seq:
                pfd_name = pfd_by_seq[seq_i]
                if pfmea_step_name != pfd_name:
                    issues.append({
                        "item_id": pfmea_id or f"pfmea-seq-{seq_i}",
                        "category": "cross_table_consistency",
                        "message": (
                            f"PFD 与 PFMEA 工序名称不一致："
                            f"PFD 工序 '{pfd_name}'（seq={seq_i}）"
                            f" vs PFMEA 工序 '{pfmea_step_name}'（{pfmea_id}）"
                        ),
                        "severity": "review",
                    })

    return issues


# ---------------------------------------------------------------------------
# Aggregate entry points
# ---------------------------------------------------------------------------


def semantic_review_row(
    row: dict[str, Any],
    table: str,
    pfd_steps: list[dict[str, Any]] | None = None,
    pfmea_rows: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Run all applicable semantic checks on a single row.

    Args:
        row: The data row dict.
        table: One of "pfmea", "control_plan", "process_flow".
        pfd_steps: PFD steps for cross-reference (optional).
        pfmea_rows: PFMEA rows for cross-reference (optional).

    Returns:
        List of issue message strings.
    """
    issues: list[str] = []

    if table == "pfmea":
        issues.extend(check_rpn_arithmetic(row))
        issues.extend(check_cause_effect_logic(row))
        issues.extend(check_detection_vs_failure_type(row))
        # PFMEA rows may also have tolerance info
        issues.extend(check_measurement_vs_tolerance(row))
    elif table == "control_plan":
        issues.extend(check_measurement_vs_tolerance(row))
        # CP rows sometimes carry RPN from linked PFMEA
        if _get_field(row, "rpn", "RPN") is not None:
            issues.extend(check_rpn_arithmetic(row))

    return issues


def semantic_review_cross_table(
    pfd_steps: list[dict[str, Any]],
    pfmea_rows: list[dict[str, Any]],
    cp_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run cross-table semantic checks.

    Args:
        pfd_steps: Process Flow Diagram steps.
        pfmea_rows: PFMEA failure mode rows.
        cp_rows: Control Plan rows (reserved for future checks, e.g.
                 PFD-to-CP step name consistency).

    Returns:
        List of issue dicts with item_id, category, message, severity.
    """
    issues: list[dict[str, Any]] = []

    # PFD <-> PFMEA step name consistency
    issues.extend(
        check_cross_table_step_name_consistency(pfd_steps, pfmea_rows)
    )

    # PFD <-> CP step name consistency (same pattern, different target)
    issues.extend(
        check_cross_table_step_name_consistency(pfd_steps, cp_rows)
    )

    return issues
