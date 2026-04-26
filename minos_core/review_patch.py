"""Minimal review patch support for generated APQP chain drafts."""

from __future__ import annotations

import copy
from typing import Any

from .domain import APQPChain

REVIEW_PATCH_VERSION = "minos-core.review_patch.v1"
REVIEW_CONFIRMATIONS_KEY = "review_confirmations"

_TARGET_ALIASES = {
    "control_plan_item": "control_item",
    "control": "control_item",
    "pfmea_row": "failure_mode",
    "process_flow_step": "process_step",
    "failure_mode_candidate_row": "failure_mode_candidate",
}

_TARGET_LIST_PATHS = {
    "evidence": (("evidence",),),
    "process_step": (
        ("process_steps",),
        ("steps",),
        ("process_flow", "steps"),
        ("process_flow", "process_steps"),
    ),
    "failure_mode_candidate": (
        ("failure_mode_candidates",),
        ("candidates",),
        ("failure_mode_candidates_bundle", "candidates"),
        ("failure_mode_candidates_bundle", "failure_mode_candidates"),
    ),
    "failure_mode": (
        ("failure_modes",),
        ("rows",),
        ("pfmea", "rows"),
        ("pfmea", "failure_modes"),
    ),
    "control_item": (
        ("controls",),
        ("control_plan_items",),
        ("control_plan", "rows"),
        ("control_plan", "controls"),
        ("control_plan", "control_plan_items"),
    ),
    "trace_link": (
        ("links",),
        ("process_flow", "links"),
    ),
    "ai_inferred_item": (("ai_inferred_items",),),
}

_TARGET_ID_FIELDS = {
    "evidence": ("evidence_id", "id"),
    "process_step": ("process_step_id", "id", "step_no"),
    "failure_mode_candidate": ("candidate_id", "id"),
    "failure_mode": ("pfmea_id", "id"),
    "control_item": ("control_plan_id", "id"),
    "trace_link": ("trace_link_id", "link_id", "id"),
    "ai_inferred_item": (
        "item_id",
        "id",
        "field",
        "evidence_id",
        "process_step_id",
        "candidate_id",
        "pfmea_id",
        "control_plan_id",
        "trace_link_id",
    ),
}


def build_review_patch_template(draft_result_or_chain: dict[str, Any]) -> dict[str, Any]:
    """Build a human-fillable review patch template from a draft result.

    The template lists pending fields, confirmation needs, AI-inferred items, and
    manual review items. It intentionally leaves reviewer identity, timestamp,
    reasons, and evidence/manual confirmation basis blank so callers cannot treat
    the template as an approved review patch.
    """

    chain_payload = _draft_chain_payload(draft_result_or_chain)
    from .quality_gates import evaluate_export_gate

    gate = evaluate_export_gate(chain_payload)
    items: list[dict[str, Any]] = []
    for field_path in gate.pending_fields:
        items.append(
            _template_item(
                action="correct",
                target=f"pending_field:{field_path}",
                review_category="pending_field",
                value="REPLACE_WITH_REVIEWED_VALUE",
            )
        )
    for target in gate.needs_confirmation_items:
        items.append(
            _template_item(
                action="confirm",
                target=_normalize_template_target(target),
                review_category="needs_confirmation",
            )
        )
    for target in gate.ai_inferred_items:
        items.append(
            _template_item(
                action="confirm",
                target=_normalize_template_target(target),
                review_category="ai_inferred_manual_review",
            )
        )
    for item in gate.manual_review_items:
        item_id = _manual_review_item_id(item)
        items.append(
            _template_item(
                action="confirm",
                target=_normalize_template_target(item_id),
                review_category="manual_review",
                manual_review_note=_manual_review_message(item),
            )
        )
    return {
        "review_patch_version": REVIEW_PATCH_VERSION,
        "template_status": "requires_human_review_before_apply_review",
        "confirmed_by": "",
        "confirmed_at": "",
        "reason": "",
        "manual_confirmation_event": "",
        "evidence_refs": [],
        "quality_gate": gate.model_dump(),
        "items": _dedupe_template_items(items),
    }


def _draft_chain_payload(draft_result_or_chain: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(draft_result_or_chain, dict):
        raise TypeError("draft_result_or_chain must be a JSON object")
    if draft_result_or_chain.get("document_type") == "apqp_chain_draft_result":
        draft = draft_result_or_chain.get("draft")
        if not isinstance(draft, dict):
            raise ReviewPatchError("apqp_chain_draft_result.draft must be a JSON object")
        return draft
    if draft_result_or_chain.get("document_type") == "apqp_chain_review_result":
        patched_chain = draft_result_or_chain.get("patched_chain")
        if not isinstance(patched_chain, dict):
            raise ReviewPatchError(
                "apqp_chain_review_result.patched_chain must be a JSON object"
            )
        return patched_chain
    return draft_result_or_chain


def _template_item(
    *,
    action: str,
    target: str,
    review_category: str,
    value: Any = None,
    manual_review_note: str = "",
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "action": action,
        "target": target,
        "review_category": review_category,
        "confirmed_by": "",
        "confirmed_at": "",
        "reason": "",
        "evidence_refs": [],
        "manual_confirmation_event": "",
    }
    if action == "correct":
        item["value"] = value
    if manual_review_note:
        item["manual_review_note"] = manual_review_note
    return item


def _normalize_template_target(target: Any) -> str:
    text = str(target).strip()
    if not text:
        return "manual_review:REPLACE_WITH_TARGET_ID"
    if " -> " in text:
        _, evidence_ref = text.rsplit(" -> ", 1)
        evidence_ref = evidence_ref.strip()
        if evidence_ref.startswith("EV-"):
            return f"evidence:{evidence_ref}"
    if ":" in text:
        return text
    if text.startswith("EV-"):
        return f"evidence:{text}"
    if text.startswith("CP-"):
        return f"control_item:{text}"
    if text.startswith("PFMEA-"):
        return f"failure_mode:{text}"
    if text.startswith("P"):
        return f"process_step:{text}"
    return f"ai_inferred_item:{text}"


def _manual_review_item_id(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("item_id", item.get("target", ""))).strip()
    return str(getattr(item, "item_id", "")).strip()


def _manual_review_message(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("message", "")).strip()
    return str(getattr(item, "message", "")).strip()


def _dedupe_template_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        key = (item["action"], item["target"], item["review_category"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


class ReviewPatchError(ValueError):
    """Raised when a review patch is structurally invalid."""


def apply_review_patch(
    chain_or_payload: APQPChain | dict[str, Any], patch: dict[str, Any]
) -> dict[str, Any]:
    """Apply a minimal human review patch to an APQP chain payload.

    Patch format::

        {
            "review_patch_version": "minos-core.review_patch.v1",
            "confirmed_by": "qa.engineer",
            "confirmed_at": "2026-04-25T10:00:00Z",
            "items": [
                {
                    "action": "confirm",
                    "target": "evidence:EV-001",
                    "reason": "Reviewed against signed drawing",
                    "evidence_refs": ["EV-001"]
                },
                {
                    "action": "correct",
                    "target": "control_item:CP-001",
                    "field": "specification",
                    "value": "2.00 +/- 0.10 mm",
                    "reason": "Entered value from released drawing",
                    "evidence_refs": ["EV-DRAWING-001"]
                }
            ]
        }

    Every item must carry confirmed_by, confirmed_at, and reason either directly or
    through top-level defaults. Every item must reference existing evidence via
    evidence_refs or name an explicit manual_confirmation_event. The function
    returns a copied, updated payload and records normalized confirmations in
    metadata.review_confirmations.
    """

    payload = _payload_copy(chain_or_payload)
    if not isinstance(patch, dict):
        raise TypeError("review patch must be a JSON object")
    if patch.get("review_patch_version") != REVIEW_PATCH_VERSION:
        raise ReviewPatchError(
            f"review_patch_version must be {REVIEW_PATCH_VERSION!r}"
        )
    if patch.get("template_status"):
        raise ReviewPatchError(
            "review patch templates must be completed by a human before apply_review"
        )
    items = patch.get("items")
    if not isinstance(items, list) or not items:
        raise ReviewPatchError("review patch items must be a non-empty list")

    evidence_ids = _collect_evidence_ids(payload)
    records: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        record = _normalize_item(patch, item, index, evidence_ids)
        _apply_item(payload, record)
        records.append(_metadata_record(record))

    metadata = payload.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        raise ReviewPatchError("payload.metadata must be an object")
    confirmations = metadata.setdefault(REVIEW_CONFIRMATIONS_KEY, [])
    if not isinstance(confirmations, list):
        raise ReviewPatchError(
            f"payload.metadata.{REVIEW_CONFIRMATIONS_KEY} must be a list"
        )
    confirmations.extend(records)
    return payload


def _payload_copy(chain_or_payload: APQPChain | dict[str, Any]) -> dict[str, Any]:
    if isinstance(chain_or_payload, APQPChain):
        return copy.deepcopy(chain_or_payload.model_dump())
    if isinstance(chain_or_payload, dict):
        return copy.deepcopy(chain_or_payload)
    if hasattr(chain_or_payload, "model_dump"):
        dumped = chain_or_payload.model_dump()
        if isinstance(dumped, dict):
            return copy.deepcopy(dumped)
    raise TypeError("chain_or_payload must be an APQPChain or dict payload")


def _normalize_item(
    patch: dict[str, Any],
    item: Any,
    index: int,
    evidence_ids: set[str],
) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ReviewPatchError(f"review patch item {index} must be an object")
    action = _required_text(item, patch, "action", index)
    if action not in {"confirm", "correct"}:
        raise ReviewPatchError(
            f"review patch item {index} action must be 'confirm' or 'correct'"
        )
    target = _required_text(item, patch, "target", index)
    target_type, target_id = _parse_target(target, index)
    field = _optional_text(item.get("field"))
    if action == "correct" and "value" not in item:
        raise ReviewPatchError(f"review patch item {index} correction requires value")
    if action == "correct" and target_type != "pending_field" and not field:
        raise ReviewPatchError(f"review patch item {index} correction requires field")

    evidence_refs = _string_list(item.get("evidence_refs", patch.get("evidence_refs", [])))
    manual_event = _optional_text(
        item.get("manual_confirmation_event", patch.get("manual_confirmation_event", ""))
    )
    if not evidence_refs and not manual_event:
        raise ReviewPatchError(
            f"review patch item {index} must cite evidence_refs or manual_confirmation_event"
        )
    missing_refs = [ref for ref in evidence_refs if ref not in evidence_ids]
    if missing_refs:
        raise ReviewPatchError(
            f"review patch item {index} references missing evidence: {', '.join(missing_refs)}"
        )

    field_path = _field_path_for(target_type, target_id, field)
    return {
        "action": action,
        "target": f"{target_type}:{target_id}",
        "target_type": target_type,
        "target_id": target_id,
        "field": field,
        "field_path": field_path,
        "value": item.get("value"),
        "confirmed_by": _required_text(item, patch, "confirmed_by", index),
        "confirmed_at": _required_text(item, patch, "confirmed_at", index),
        "reason": _required_text(item, patch, "reason", index),
        "evidence_refs": evidence_refs,
        "manual_confirmation_event": manual_event,
    }


def _metadata_record(record: dict[str, Any]) -> dict[str, Any]:
    metadata_record = {
        "action": record["action"],
        "target": record["target"],
        "confirmed_by": record["confirmed_by"],
        "confirmed_at": record["confirmed_at"],
        "reason": record["reason"],
        "evidence_refs": list(record["evidence_refs"]),
    }
    if record.get("field"):
        metadata_record["field"] = record["field"]
    if record.get("field_path"):
        metadata_record["field_path"] = record["field_path"]
    if record.get("manual_confirmation_event"):
        metadata_record["manual_confirmation_event"] = record[
            "manual_confirmation_event"
        ]
    return metadata_record


def _apply_item(payload: dict[str, Any], record: dict[str, Any]) -> None:
    target_type = record["target_type"]
    if target_type == "pending_field":
        _remove_pending_field(payload, record["target_id"])
        if record["action"] == "correct":
            row, field = _resolve_field_path_target(payload, record["target_id"])
            row[field] = record["value"]
        return

    row = _find_target(payload, target_type, record["target_id"])
    if row is None:
        raise ReviewPatchError(f"review patch target not found: {record['target']}")
    if record["action"] == "correct":
        row[record["field"]] = record["value"]
    if "needs_confirmation" in row:
        row["needs_confirmation"] = False
    if record.get("field"):
        for pending_field in _pending_field_candidates(record):
            _remove_pending_field(payload, pending_field)


def _parse_target(target: str, index: int) -> tuple[str, str]:
    if ":" not in target:
        raise ReviewPatchError(f"review patch item {index} target must use type:id")
    target_type, target_id = target.split(":", 1)
    target_type = _TARGET_ALIASES.get(target_type.strip(), target_type.strip())
    target_id = target_id.strip()
    if not target_type or not target_id:
        raise ReviewPatchError(f"review patch item {index} target must use type:id")
    if target_type != "pending_field" and target_type not in _TARGET_LIST_PATHS:
        raise ReviewPatchError(f"review patch item {index} target type is unsupported")
    return target_type, target_id


def _find_target(
    payload: dict[str, Any], target_type: str, target_id: str
) -> dict[str, Any] | None:
    for row in _target_rows(payload, target_type):
        if not isinstance(row, dict):
            continue
        if target_type == "trace_link" and _trace_link_label(row) == target_id:
            return row
        for field_name in _TARGET_ID_FIELDS[target_type]:
            if str(row.get(field_name, "")).strip() == target_id:
                return row
    return None


def _resolve_field_path_target(
    payload: dict[str, Any], field_path: str
) -> tuple[dict[str, Any], str]:
    object_id, separator, field = field_path.rpartition(".")
    if not separator or not object_id or not field:
        raise ReviewPatchError(
            f"pending_field correction target must be object_id.field: {field_path}"
        )
    for target_type in (
        "process_step",
        "failure_mode_candidate",
        "failure_mode",
        "control_item",
        "evidence",
        "trace_link",
        "ai_inferred_item",
    ):
        row = _find_target(payload, target_type, object_id)
        if row is not None:
            return row, field
    if ":" in object_id:
        target_type, target_id = object_id.split(":", 1)
        target_type = _TARGET_ALIASES.get(target_type.strip(), target_type.strip())
        if target_type in _TARGET_LIST_PATHS:
            row = _find_target(payload, target_type, target_id.strip())
            if row is not None:
                return row, field
    raise ReviewPatchError(f"pending_field correction target not found: {field_path}")


def _target_rows(payload: dict[str, Any], target_type: str) -> list[Any]:
    rows: list[Any] = []
    for path in _TARGET_LIST_PATHS[target_type]:
        value: Any = payload
        for part in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(part)
        if isinstance(value, list):
            rows.extend(value)
    return rows


def _remove_pending_field(payload: dict[str, Any], field_path: str) -> None:
    for container in _pending_field_containers(payload):
        pending_fields = container.get("pending_fields")
        if isinstance(pending_fields, list):
            container["pending_fields"] = [
                item
                for item in pending_fields
                if not _pending_item_matches(item, field_path)
            ]
        elif isinstance(pending_fields, str) and _field_matches(pending_fields, field_path):
            container["pending_fields"] = []


def _pending_field_containers(payload: dict[str, Any]) -> list[dict[str, Any]]:
    containers: list[dict[str, Any]] = []
    if "pending_fields" in payload:
        containers.append(payload)
    for key in (
        "process_flow",
        "failure_mode_candidates",
        "pfmea",
        "control_plan",
        "analysis_bundle",
    ):
        value = payload.get(key)
        if isinstance(value, dict) and "pending_fields" in value:
            containers.append(value)
    return containers


def _pending_item_matches(item: Any, field_path: str) -> bool:
    if isinstance(item, str):
        return _field_matches(item, field_path)
    if isinstance(item, dict):
        candidates = []
        if item.get("field"):
            candidates.append(str(item.get("field", "")).strip())
            candidates.append(
                f"{item.get('source_ref', '')}.{item.get('field', '')}".strip(".")
            )
        if item.get("path"):
            candidates.append(str(item.get("path", "")).strip())
        return any(_field_matches(candidate, field_path) for candidate in candidates)
    return False


def _field_matches(candidate: str, field_path: str) -> bool:
    candidate = candidate.strip()
    field_path = field_path.strip()
    if not candidate or not field_path:
        return False
    if candidate == field_path or candidate == f"pending_field:{field_path}":
        return True
    if ":" in candidate:
        _, candidate_tail = candidate.split(":", 1)
        return candidate_tail == field_path
    if ":" in field_path:
        _, field_tail = field_path.split(":", 1)
        return candidate == field_tail
    return False


def _pending_field_candidates(record: dict[str, Any]) -> set[str]:
    candidates = {record["target_id"]}
    field = record.get("field")
    if field:
        candidates.add(f"{record['target_id']}.{field}")
        candidates.add(f"{record['target']}.{field}")
    if record.get("field_path"):
        candidates.add(record["field_path"])
    return {candidate for candidate in candidates if candidate}


def _field_path_for(target_type: str, target_id: str, field: str) -> str:
    if target_type == "pending_field":
        return target_id
    return f"{target_id}.{field}" if field else ""


def _collect_evidence_ids(value: Any) -> set[str]:
    ids: set[str] = set()
    if isinstance(value, dict):
        evidence_id = str(value.get("evidence_id", "")).strip()
        if evidence_id:
            ids.add(evidence_id)
        for child in value.values():
            ids.update(_collect_evidence_ids(child))
    elif isinstance(value, list):
        for child in value:
            ids.update(_collect_evidence_ids(child))
    return ids


def _trace_link_label(row: dict[str, Any]) -> str:
    link_id = str(row.get("trace_link_id", row.get("link_id", row.get("id", "")))).strip()
    if link_id:
        return link_id
    from_id = str(row.get("from", row.get("from_id", ""))).strip()
    to_id = str(row.get("to", row.get("to_id", ""))).strip()
    return f"{from_id}->{to_id}" if from_id or to_id else ""


def _required_text(
    item: dict[str, Any], patch: dict[str, Any], key: str, index: int
) -> str:
    value = item.get(key, patch.get(key, ""))
    text = _optional_text(value)
    if not text:
        raise ReviewPatchError(f"review patch item {index} requires {key}")
    return text


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ReviewPatchError("evidence_refs must be a string or list of strings")
