"""AI judge wrapper and verifier for special-characteristic evidence packets."""

from __future__ import annotations

import json
from typing import Any

from minos_core._text_utils import string_list, text
from minos_core.adapters.llm_text import OpenAITextGenerator


class FakeSpecialCharacteristicJudge:
    """Deterministic judge used by tests and pipeline dry-runs."""

    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    def judge(self, evidence_packet: dict[str, Any]) -> dict[str, Any]:
        return dict(self.payload)


class SpecialCharacteristicJudge:
    """Evidence-bound GPT judge for SC/CC verdicts."""

    def __init__(self, generator: Any | None = None, model: str = "gpt-5.5") -> None:
        self.generator = generator or OpenAITextGenerator()
        self.model = model

    def judge(self, evidence_packet: dict[str, Any]) -> dict[str, Any]:
        return self.generator.generate_structured(
            _judge_system_prompt(),
            json.dumps(evidence_packet, ensure_ascii=False, sort_keys=True),
            response_format=_judge_response_format(),
            model=self.model,
            max_tokens=4096,
            temperature=0.0,
        )


def normalize_special_characteristic_judgments(payload: Any) -> list[dict[str, Any]]:
    rows = payload.get("special_characteristic_judgments", []) if isinstance(payload, dict) else []
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(rows if isinstance(rows, list) else [], start=1):
        if not isinstance(raw, dict):
            continue
        classification = text(raw.get("classification")).upper()
        if classification not in {"SC", "CC"}:
            classification = "unknown"
        verdict = text(raw.get("verdict")) or "needs_human_review"
        if verdict not in {"confirmed", "rejected", "needs_human_review"}:
            verdict = "needs_human_review"
        normalized.append(
            {
                "judgment_id": text(raw.get("judgment_id")) or f"SCJ-{index:03d}",
                "candidate_id": text(raw.get("candidate_id")),
                "classification": classification,
                "verdict": verdict,
                "linked_feature": text(raw.get("linked_feature")),
                "confidence": _confidence(raw.get("confidence")),
                "standard_evidence_refs": string_list(raw.get("standard_evidence_refs", [])),
                "symbol_evidence_refs": string_list(raw.get("symbol_evidence_refs", [])),
                "page_evidence_refs": string_list(raw.get("page_evidence_refs", [])),
                "reasoning_summary": text(raw.get("reasoning_summary")),
            }
        )
    return normalized


def verify_special_characteristic_judgments(
    judgments: list[dict[str, Any]],
    evidence_packet: dict[str, Any],
) -> dict[str, Any]:
    candidate_ids = _candidate_ids(evidence_packet)
    standard_ids = _standard_evidence_ids(evidence_packet)
    page_ids = set(string_list(evidence_packet.get("page_evidence_refs", [])))
    confirmed: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    for item in judgments:
        missing = _missing_refs(item, candidate_ids, standard_ids, page_ids)
        if _is_confirmable(item, missing):
            confirmed.append(
                {
                    **item,
                    "confirmation_status": "judge_confirmed",
                    "needs_confirmation": False,
                }
            )
            continue
        risks.append(_risk_from_judgment(item, missing))
    risks.extend(_count_mismatch_risks(confirmed, evidence_packet))
    return {"confirmed": confirmed, "risks": risks}


def _candidate_ids(evidence_packet: dict[str, Any]) -> set[str]:
    return {
        text(item.get("candidate_id"))
        for item in evidence_packet.get("symbol_occurrences", [])
        if isinstance(item, dict) and text(item.get("candidate_id"))
    }


def _standard_evidence_ids(evidence_packet: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for key, id_key in (
        ("legend_evidence", "legend_id"),
        ("text_evidence", "text_id"),
        ("customer_rules", "rule_id"),
    ):
        for item in evidence_packet.get(key, []):
            if isinstance(item, dict):
                value = text(item.get(id_key), item.get("id"), item.get("evidence_id"))
                if value:
                    ids.add(value)
    return ids


def _missing_refs(
    item: dict[str, Any],
    candidate_ids: set[str],
    standard_ids: set[str],
    page_ids: set[str],
) -> list[str]:
    missing: list[str] = []
    candidate_id = text(item.get("candidate_id"))
    if not candidate_id or candidate_id not in candidate_ids:
        missing.append(candidate_id or "candidate_id")
    for ref in item.get("symbol_evidence_refs", []):
        if ref not in candidate_ids:
            missing.append(ref)
    for ref in item.get("standard_evidence_refs", []):
        if ref not in standard_ids:
            missing.append(ref)
    for ref in item.get("page_evidence_refs", []):
        if ref not in page_ids:
            missing.append(ref)
    return missing


def _is_confirmable(item: dict[str, Any], missing: list[str]) -> bool:
    return (
        item["verdict"] == "confirmed"
        and item["classification"] in {"SC", "CC"}
        and bool(item["standard_evidence_refs"])
        and bool(item["symbol_evidence_refs"])
        and bool(item["page_evidence_refs"])
        and not missing
    )


def _risk_from_judgment(
    item: dict[str, Any],
    missing_evidence_refs: list[str],
) -> dict[str, Any]:
    judgment_id = text(item.get("judgment_id")) or "unknown"
    return {
        "risk_id": f"SC-JUDGE-{judgment_id}",
        "item_id": f"SC-JUDGE-{judgment_id}",
        "category": "special_characteristic_judge",
        "severity": "review",
        "target": f"special_characteristic_judgments.{judgment_id}",
        "message": "AI 裁判结果证据不足或需要人工确认。",
        "missing_evidence_refs": missing_evidence_refs,
        "judgment": dict(item),
    }


def _count_mismatch_risks(
    confirmed: list[dict[str, Any]],
    evidence_packet: dict[str, Any],
) -> list[dict[str, Any]]:
    declared_totals = evidence_packet.get("declared_totals")
    if not isinstance(declared_totals, dict):
        return []
    confirmed_counts = {"CC": 0, "SC": 0}
    for item in confirmed:
        classification = text(item.get("classification")).upper()
        if classification in confirmed_counts:
            confirmed_counts[classification] += 1

    risks: list[dict[str, Any]] = []
    for classification in ("CC", "SC"):
        expected_count = _declared_count(declared_totals.get(classification))
        confirmed_count = confirmed_counts[classification]
        if expected_count <= confirmed_count:
            continue
        risks.append(
            {
                "risk_id": f"SC-JUDGE-COUNT-MISMATCH-{classification}",
                "item_id": f"SC-JUDGE-COUNT-MISMATCH-{classification}",
                "category": "special_characteristic_judge",
                "severity": "review",
                "target": f"declared_totals.{classification}",
                "message": (
                    f"图纸声明 {classification} 有 {expected_count} 个，"
                    f"GPT5.5 当前只确认 {confirmed_count} 个。"
                ),
                "classification": classification,
                "expected_count": expected_count,
                "confirmed_count": confirmed_count,
            }
        )
    return risks


def _declared_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _judge_system_prompt() -> str:
    return (
        "你是 MINOS 的特殊特性证据约束裁判。"
        "只能基于用户提供的 special_characteristic_evidence_packet 判断 SC/CC。"
        "视觉定位器和 OCR 只是证人，不能把候选本身当成最终结论。"
        "不能引用 evidence packet 之外的证据，不能编造 candidate、图例、文本或页面引用。"
        "symbol_evidence_refs 只能引用 symbol_occurrences.candidate_id；"
        "standard_evidence_refs 只能引用 legend_evidence.legend_id、"
        "text_evidence.text_id 或 customer_rules.rule_id；"
        "page_evidence_refs 只能引用 evidence packet.page_evidence_refs。"
        "只有同时具备候选符号证据、标准/图例/文字证据和页面证据时，才能输出 confirmed。"
        "普通数值或性能要求本身不能单独升级为 SC/CC。"
        "证据不足时输出 needs_human_review。只输出符合 schema 的 JSON。"
    )


def _judge_response_format() -> dict[str, Any]:
    judgment_schema = {
        "type": "object",
        "properties": {
            "judgment_id": {"type": "string"},
            "candidate_id": {"type": "string"},
            "classification": {"type": "string", "enum": ["SC", "CC", "unknown"]},
            "verdict": {
                "type": "string",
                "enum": ["confirmed", "rejected", "needs_human_review"],
            },
            "linked_feature": {"type": "string"},
            "confidence": {"type": "number"},
            "standard_evidence_refs": {"type": "array", "items": {"type": "string"}},
            "symbol_evidence_refs": {"type": "array", "items": {"type": "string"}},
            "page_evidence_refs": {"type": "array", "items": {"type": "string"}},
            "reasoning_summary": {"type": "string"},
        },
        "required": [
            "judgment_id",
            "candidate_id",
            "classification",
            "verdict",
            "linked_feature",
            "confidence",
            "standard_evidence_refs",
            "symbol_evidence_refs",
            "page_evidence_refs",
            "reasoning_summary",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "special_characteristic_judgments",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "special_characteristic_judgments": {
                        "type": "array",
                        "items": judgment_schema,
                    }
                },
                "required": ["special_characteristic_judgments"],
                "additionalProperties": False,
            },
        },
    }


def _confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0
