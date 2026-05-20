"""Local knowledge base v2 — 加载、标准化、过滤 FMEA 知识条目。

提供三个公开函数：
- load_knowledge_base(path)  — 加载并标准化知识库
- normalize_knowledge_item(item) — 将旧格式条目标准化为 v2 格式
- active_knowledge_items(items)  — 过滤 status=='active' 的条目
"""

from __future__ import annotations

import json
import sqlite3
import warnings
from pathlib import Path
from typing import Any

from minos_core._paths import configs_dir
from minos_core.knowledge_recommendation import DEFAULT_KNOWLEDGE_RULES

# ---------------------------------------------------------------------------
# 默认知识库路径
# ---------------------------------------------------------------------------


def _default_kb_path() -> Path:
    return configs_dir() / "knowledge" / "fmea_rules.zh-CN.json"


_DEFAULT_KB_PATH = _default_kb_path()
_INITIAL_DEFAULT_KB_PATH = _DEFAULT_KB_PATH


def _effective_default_kb_path() -> Path:
    if _DEFAULT_KB_PATH != _INITIAL_DEFAULT_KB_PATH:
        return Path(_DEFAULT_KB_PATH)
    return _default_kb_path()

# ---------------------------------------------------------------------------
# category 枚举
# ---------------------------------------------------------------------------

_CATEGORY_VALUES = frozenset({
    "failure_mode_pattern",
    "failure_cause_pattern",
    "prevention_control_pattern",
    "detection_control_pattern",
    "control_plan_pattern",
    "rating_hint",
    "comprehensive",
})

# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def load_knowledge_base(path: str | Path | None = None) -> list[dict[str, Any]]:
    """加载并标准化知识库。

    Parameters
    ----------
    path : str | Path | None
        - ``None`` — 使用默认 JSON 知识库。
          如果默认文件不存在，发出 warning 并回退到内置种子规则。
        - 显式路径 — 必须存在，否则抛出 ``FileNotFoundError``。
          支持 ``.json`` / ``.sqlite`` / ``.sqlite3`` / ``.db``。

    Returns
    -------
    list[dict[str, Any]]
        标准化后的知识条目列表（按 knowledge_id + version 去重，保留 confidence 较高的）。
    """
    default_path = _effective_default_kb_path()
    if path is None:
        path = default_path
    path = Path(path)

    if path == default_path and not path.exists():
        warnings.warn(
            f"默认知识库 {path} 不存在，使用内置种子规则"
        )
        return [
            normalize_knowledge_item(dict(rule), index=i)
            for i, rule in enumerate(DEFAULT_KNOWLEDGE_RULES)
        ]

    if not path.exists():
        raise FileNotFoundError(f"知识库文件不存在: {path}")

    if path.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
        items = _load_sqlite_items(path)
    else:
        items = _load_json_items(path)

    if not items:
        raise ValueError(f"知识库文件解析为空: {path}")

    normalized = [
        normalize_knowledge_item(item, index=i) for i, item in enumerate(items)
    ]
    return _deduplicate(normalized)


def normalize_knowledge_item(
    item: dict[str, Any], *, index: int = 0
) -> dict[str, Any]:
    """将一条知识条目（旧格式或新格式）标准化为 knowledge_base v2 格式。

    旧格式字段映射：
    - ``rule_id`` → ``knowledge_id``
    - ``operation_terms`` → ``process_terms``
    - ``requires_special_characteristic`` → ``special_characteristic_required``
    - ``enabled=False`` → ``status="inactive"``
    - ``recommendation_type`` → 用于推断 ``category``

    Parameters
    ----------
    item : dict
        原始知识条目。
    index : int
        条目序号，仅在缺失 ``rule_id`` 时用于自动生成 ``knowledge_id``。

    Returns
    -------
    dict[str, Any]
        标准化后的 v2 知识对象。
    """
    # ---- knowledge_id ----
    knowledge_id = str(item.get("rule_id", "")).strip()
    if not knowledge_id:
        knowledge_id = f"KB-AUTO-{index:04d}"

    # ---- process_terms (优先新字段，回退到 operation_terms) ----
    process_terms = item.get("process_terms")
    if process_terms is None:
        process_terms = item.get("operation_terms", [])
    if isinstance(process_terms, tuple):
        process_terms = list(process_terms)
    elif not isinstance(process_terms, list):
        process_terms = []

    # ---- characteristic_terms ----
    characteristic_terms = item.get("characteristic_terms", [])
    if isinstance(characteristic_terms, tuple):
        characteristic_terms = list(characteristic_terms)
    elif not isinstance(characteristic_terms, list):
        characteristic_terms = []

    # ---- failure_terms ----
    failure_terms = item.get("failure_terms", [])
    if isinstance(failure_terms, tuple):
        failure_terms = list(failure_terms)
    elif not isinstance(failure_terms, list):
        failure_terms = []

    # ---- special_characteristic_required ----
    special_characteristic_required = bool(
        item.get("special_characteristic_required")
        or item.get("requires_special_characteristic")
    )

    # ---- requires_high_ap ----
    requires_high_ap = bool(item.get("requires_high_ap"))

    # ---- suggested_fields (显式字段，不合并 risk/controls) ----
    suggested_fields = item.get("suggested_fields", {})
    if not isinstance(suggested_fields, dict):
        suggested_fields = {}

    # ---- recommended_controls ----
    recommended_controls = item.get("recommended_controls", {})
    if not isinstance(recommended_controls, dict):
        recommended_controls = {}

    # ---- risk (passthrough for backward compatibility) ----
    risk = item.get("risk", {})
    if not isinstance(risk, dict):
        risk = {}

    # ---- rating_hint ----
    rating_hint = item.get("rating_hint", {})
    if not isinstance(rating_hint, dict):
        rating_hint = {}

    # ---- message ----
    message = str(item.get("message", ""))

    # ---- source ----
    source = item.get("source")
    if source and str(source).strip():
        source = str(source).strip()
    else:
        source = "local_seed"

    # ---- version ----
    version = str(item.get("version", "1.0")).strip() or "1.0"

    # ---- status: 优先保留已有 status，否则从 enabled 推断 ----
    if "status" in item:
        status = str(item["status"]).strip()
    elif item.get("enabled") is False:
        status = "inactive"
    else:
        status = "active"

    # ---- confidence: 非数字归一为 0.0 ----
    confidence = item.get("confidence", 0.0)
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        confidence = 0.0
    confidence = float(confidence)

    # ---- enabled ----
    enabled = bool(item.get("enabled", True))

    # ---- category: 从旧格式字段自动推断 ----
    category = _infer_category(item)

    return {
        "knowledge_id": knowledge_id,
        "category": category,
        "process_terms": process_terms,
        "characteristic_terms": characteristic_terms,
        "failure_terms": failure_terms,
        "special_characteristic_required": special_characteristic_required,
        "requires_high_ap": requires_high_ap,
        "suggested_fields": suggested_fields,
        "recommended_controls": recommended_controls,
        "rating_hint": rating_hint,
        "risk": risk,
        "message": message,
        "source": source,
        "version": version,
        "status": status,
        "confidence": confidence,
        "enabled": enabled,
    }


def active_knowledge_items(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """返回 status=='active' 且 enabled 不为 False 的知识条目。"""
    return [
        item
        for item in items
        if item.get("status") in ("active",)
        and item.get("enabled") is not False
    ]


# ---------------------------------------------------------------------------
# category 自动推断
# ---------------------------------------------------------------------------


def _infer_category(item: dict[str, Any]) -> str:
    """从旧规则字段自动推断 category。

    检查 combined suggested field keys（risk + controls + rating_hint +
    显式 suggested_fields），按以下优先级判断：

    1. 如果匹配多个 category → ``comprehensive``
    2. 如果包含 ``risk`` 键（非空）→ ``comprehensive``
    3. 如果恰好匹配一个 → 对应 category
    4. 默认 → ``control_plan_pattern``
    """
    combined = _collect_suggested_field_keys(item)

    has_failure_mode = bool(combined & {"failure_mode", "failure_effect"})
    has_failure_cause = "failure_cause" in combined
    has_prevention = "prevention_control" in combined
    has_detection = "detection_control" in combined
    has_control_plan = bool(
        combined & {"measurement_method", "sample_frequency", "reaction_plan"}
    )
    has_rating = bool(combined & {"severity", "occurrence", "detection"})

    matched: list[str] = []
    if has_failure_mode:
        matched.append("failure_mode_pattern")
    if has_failure_cause:
        matched.append("failure_cause_pattern")
    if has_prevention:
        matched.append("prevention_control_pattern")
    if has_detection:
        matched.append("detection_control_pattern")
    if has_control_plan:
        matched.append("control_plan_pattern")
    if has_rating:
        matched.append("rating_hint")

    if len(matched) > 1:
        return "comprehensive"

    risk = item.get("risk", {})
    if isinstance(risk, dict) and risk:
        return "comprehensive"

    if matched:
        return matched[0]

    return "control_plan_pattern"


def _collect_suggested_field_keys(item: dict[str, Any]) -> set[str]:
    """聚合条目中所有「建议字段」的键名。

    来源包括：显式 suggested_fields、risk、recommended_controls、rating_hint。
    """
    keys: set[str] = set()

    # 显式 suggested_fields
    sf = item.get("suggested_fields", {})
    if isinstance(sf, dict):
        for k, v in sf.items():
            if v:  # 只计入有实际值的字段
                keys.add(k)

    # risk 块
    risk = item.get("risk", {})
    if isinstance(risk, dict):
        for k in ("failure_mode", "failure_effect", "failure_cause"):
            if risk.get(k):
                keys.add(k)

    # recommended_controls 块
    controls = item.get("recommended_controls", {})
    if isinstance(controls, dict):
        for k, v in controls.items():
            if v:
                keys.add(k)

    # rating_hint 块
    rating = item.get("rating_hint", {})
    if isinstance(rating, dict):
        for k, v in rating.items():
            if v is not None:
                keys.add(k)

    return keys


# ---------------------------------------------------------------------------
# 底层加载器（逻辑复用自 knowledge_recommendation._load_json_rules /
# _load_sqlite_rules）
# ---------------------------------------------------------------------------


def _load_json_items(path: Path) -> list[dict[str, Any]]:
    """从 JSON 文件加载知识条目列表。"""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        rules = payload.get("rules", [])
        if isinstance(rules, list):
            return [item for item in rules if isinstance(item, dict)]
    return []


def _load_sqlite_items(path: Path) -> list[dict[str, Any]]:
    """从 SQLite 数据库加载知识条目列表。"""
    with sqlite3.connect(str(path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT rule_id, category, payload_json, enabled
            FROM knowledge_rules
            WHERE enabled = 1
            ORDER BY rule_id
            """
        ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(str(row["payload_json"] or "{}"))
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload.setdefault("rule_id", str(row["rule_id"]))
        payload.setdefault("knowledge_type", str(row["category"]))
        items.append(payload)
    return items


# ---------------------------------------------------------------------------
# 去重
# ---------------------------------------------------------------------------


def _deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 (knowledge_id, version) 去重，保留 confidence 较高的条目。"""
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        key = (item["knowledge_id"], item["version"])
        if key in seen:
            if item["confidence"] > seen[key]["confidence"]:
                seen[key] = item
        else:
            seen[key] = item
    return list(seen.values())
