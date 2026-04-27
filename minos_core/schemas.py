"""Versioned top-level bundle schema checks for MINOS-CORE."""

from __future__ import annotations

from typing import Any


REVIEW_PATCH_VERSION = "minos-core.review_patch.v1"
EDIT_PATCH_VERSION = "minos-core.edit_patch.v1"

SCHEMA_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "evidence_bundle": ("evidence",),
    "drawing_analysis_bundle": (
        "drawing_identity",
        "materials",
        "dimensions",
        "special_characteristics",
        "technical_requirements",
        "manufacturing_clues",
        "evidence",
    ),
    "analysis_bundle": ("drawings", "characteristics", "process_clues", "evidence"),
    "process_flow": ("steps", "links", "evidence"),
    "failure_mode_candidates": ("candidates", "evidence"),
    "pfmea": ("rows", "evidence"),
    "control_plan": ("rows", "evidence"),
    "apqp_chain": ("process_steps", "failure_modes", "controls", "evidence"),
    "input_package": (
        "document_type",
        "schema_version",
        "package_id",
        "evidence_path",
        "metadata",
    ),
    "run_manifest": ("run_id", "stages"),
    "review_patch": ("review_patch_version", "items"),
    "edit_patch": ("edit_patch_version", "items"),
    "apqp_chain_draft_result": (
        "status",
        "draft_notice",
        "draft_is_formal_export",
        "draft",
        "quality_gate",
        "manual_review",
        "stage_results",
    ),
    "three_table_generation_result": (
        "status",
        "drawing_analysis",
        "process_flow",
        "pfmea",
        "control_plan",
        "quality_gate",
        "exports",
        "manifest",
    ),
    "apqp_chain_review_result": (
        "status",
        "reviewed_chain",
        "quality_gate",
    ),
}

SUPPORTED_DOCUMENT_TYPES = tuple(SCHEMA_REQUIRED_FIELDS)


class BundleSchemaError(ValueError):
    """Raised when a bundle does not match its versioned top-level schema."""


class BundleSchemaTypeError(TypeError):
    """Raised when a bundle payload is not a mapping."""


_FIELD_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "apqp_chain": {
        "process_steps": ("process_flow.steps",),
        "failure_modes": ("pfmea.rows",),
        "controls": ("control_plan.rows",),
    },
    "apqp_chain_review_result": {
        "review_patch": ("patch", "applied_patch"),
        "reviewed_chain": ("chain", "apqp_chain", "draft", "patched_chain"),
        "quality_gate": ("export_gate",),
    },
}

_SCHEMA_VERSION_COMPATIBLE_DOCUMENT_TYPES = {
    "apqp_chain",
    "apqp_chain_draft_result",
    "apqp_chain_review_result",
}


class _ContractFailureCollector:
    def __init__(self, document_type: str) -> None:
        self.document_type = document_type
        self.messages: list[str] = []

    def add(self, message: str) -> None:
        self.messages.append(message)

    def raise_if_any(self) -> None:
        if not self.messages:
            return
        joined_messages = "; ".join(self.messages)
        raise BundleSchemaError(
            f"{self.document_type} schema validation failed: {joined_messages}"
        )


def validate_bundle_schema(
    payload: dict[str, Any], document_type: str | None = None
) -> bool:
    """Validate the top-level schema for a supported MINOS bundle.

    The check intentionally stays lightweight: it verifies that the payload is a
    dictionary, resolves and checks the document type, requires a schema version
    where the current contract requires one, and confirms that each supported
    bundle exposes its required top-level blocks. Legacy APQP fixtures and the
    current generate-draft/review-patch envelopes stay accepted so older fixtures
    and generated outputs remain readable.
    """

    if not isinstance(payload, dict):
        raise BundleSchemaTypeError("bundle schema validation failed: payload must be dict")

    expected_document_type = _clean_text(document_type)
    payload_document_type = _clean_text(payload.get("document_type"))
    resolved_document_type = _resolve_document_type(
        payload, payload_document_type, expected_document_type
    )

    if expected_document_type and payload_document_type:
        if payload_document_type != expected_document_type:
            raise BundleSchemaError(
                f"{expected_document_type} schema validation failed: "
                "document_type mismatch: "
                f"expected {expected_document_type}, got {payload_document_type}"
            )

    if not resolved_document_type:
        raise BundleSchemaError(
            "unknown schema validation failed: missing required field(s): document_type"
        )

    if resolved_document_type not in SCHEMA_REQUIRED_FIELDS:
        raise BundleSchemaError(
            f"{resolved_document_type} schema validation failed: "
            f"unsupported document_type: {resolved_document_type}"
        )

    missing_fields: list[str] = []
    if not _has_schema_version(payload, resolved_document_type):
        missing_fields.append("schema_version")

    for field_name in SCHEMA_REQUIRED_FIELDS[resolved_document_type]:
        if not _has_required_field(payload, resolved_document_type, field_name):
            missing_fields.append(field_name)

    if missing_fields:
        joined_fields = ", ".join(missing_fields)
        raise BundleSchemaError(
            f"{resolved_document_type} schema validation failed: "
            f"missing required field(s): {joined_fields}"
        )

    _validate_contract_fields(payload, resolved_document_type)
    return True


def _clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _resolve_document_type(
    payload: dict[str, Any], payload_document_type: str, expected_document_type: str
) -> str:
    if expected_document_type:
        return expected_document_type
    if payload_document_type:
        return payload_document_type
    if _looks_like_review_patch(payload):
        return "review_patch"
    if _looks_like_edit_patch(payload):
        return "edit_patch"
    if _looks_like_legacy_apqp_chain(payload):
        return "apqp_chain"
    return ""


def _has_schema_version(payload: dict[str, Any], document_type: str) -> bool:
    if _clean_text(payload.get("schema_version")):
        return True
    if document_type == "review_patch":
        return _clean_text(payload.get("review_patch_version")) == REVIEW_PATCH_VERSION
    if document_type == "edit_patch":
        return _clean_text(payload.get("edit_patch_version")) == EDIT_PATCH_VERSION
    if document_type not in _SCHEMA_VERSION_COMPATIBLE_DOCUMENT_TYPES:
        return False
    if document_type == "apqp_chain":
        return _looks_like_legacy_apqp_chain(payload)
    return True


def _has_required_field(
    payload: dict[str, Any], document_type: str, field_name: str
) -> bool:
    if field_name in payload:
        return True
    return _get_field_value(payload, document_type, field_name, missing=None) is not None


def _get_field_value(
    payload: dict[str, Any],
    document_type: str,
    field_name: str,
    *,
    missing: Any = None,
) -> Any:
    if field_name in payload:
        return payload[field_name]
    for alias in _FIELD_ALIASES.get(document_type, {}).get(field_name, ()):  # noqa: SIM118
        value = _get_dotted_value(payload, alias, missing=missing)
        if value is not missing:
            return value
    return missing


def _get_dotted_value(payload: dict[str, Any], path: str, *, missing: Any = None) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return missing
        current = current[part]
    return current


def _looks_like_review_patch(payload: dict[str, Any]) -> bool:
    return bool(payload.get("review_patch_version") and "items" in payload)


def _looks_like_edit_patch(payload: dict[str, Any]) -> bool:
    return bool(payload.get("edit_patch_version") and "items" in payload)


def _looks_like_legacy_apqp_chain(payload: dict[str, Any]) -> bool:
    normalized_fields = {"process_steps", "failure_modes", "controls", "evidence"}
    if normalized_fields.issubset(payload):
        return True

    process_flow = payload.get("process_flow")
    pfmea = payload.get("pfmea")
    control_plan = payload.get("control_plan")
    return bool(
        isinstance(process_flow, dict)
        and "steps" in process_flow
        and isinstance(pfmea, dict)
        and "rows" in pfmea
        and isinstance(control_plan, dict)
        and "rows" in control_plan
        and "evidence" in payload
    )


def _validate_contract_fields(payload: dict[str, Any], document_type: str) -> None:
    validators = {
        "drawing_analysis_bundle": _validate_drawing_analysis_bundle,
        "input_package": _validate_input_package,
        "run_manifest": _validate_run_manifest,
        "review_patch": _validate_review_patch,
        "edit_patch": _validate_edit_patch,
        "apqp_chain_draft_result": _validate_apqp_chain_draft_result,
        "three_table_generation_result": _validate_three_table_generation_result,
        "apqp_chain_review_result": _validate_apqp_chain_review_result,
    }
    validator = validators.get(document_type)
    if validator is not None:
        validator(payload, document_type)


def _validate_drawing_analysis_bundle(payload: dict[str, Any], document_type: str) -> None:
    failures = _ContractFailureCollector(document_type)
    if payload.get("schema_version") != "minos-core.drawing_analysis.v1":
        failures.add("schema_version must be 'minos-core.drawing_analysis.v1'")
    if not isinstance(payload.get("drawing_identity"), dict):
        failures.add("drawing_identity must be an object")
    for field_name in (
        "materials",
        "dimensions",
        "special_characteristics",
        "technical_requirements",
        "inspection_requirements",
        "manufacturing_clues",
        "uncertainties",
        "evidence",
    ):
        _optional_list(payload, failures, field_name)
    failures.raise_if_any()


def _validate_input_package(payload: dict[str, Any], document_type: str) -> None:
    failures = _ContractFailureCollector(document_type)
    if payload.get("schema_version") != "minos-core.input_package.v1":
        failures.add("schema_version must be 'minos-core.input_package.v1'")
    if not _clean_text(payload.get("package_id")):
        failures.add("package_id must be a non-empty string")
    if not _clean_text(payload.get("evidence_path")):
        failures.add("evidence_path must be a non-empty string")
    if "review_patch_path" in payload and not _clean_text(payload.get("review_patch_path")):
        failures.add("review_patch_path must be a non-empty string when provided")
    if not isinstance(payload.get("metadata"), dict):
        failures.add("metadata must be an object")
    _optional_list(payload, failures, "source_documents")
    failures.raise_if_any()


def _validate_run_manifest(payload: dict[str, Any], document_type: str) -> None:
    failures = _ContractFailureCollector(document_type)
    if not _clean_text(payload.get("run_id")):
        failures.add("run_id must be a non-empty string")
    stages = payload.get("stages")
    if not isinstance(stages, list):
        failures.add("stages must be a list")
    else:
        for index, stage in enumerate(stages):
            if not isinstance(stage, dict):
                failures.add(f"stages[{index}] must be an object")
                continue
            if not _clean_text(stage.get("stage")):
                failures.add(f"stages[{index}].stage must be a non-empty string")
            if not _clean_text(stage.get("status")):
                failures.add(f"stages[{index}].status must be a non-empty string")
    _optional_object(payload, failures, "metadata")
    _optional_object(payload, failures, "inputs", allow_none=True)
    _optional_object(payload, failures, "outputs", allow_none=True)
    _optional_list(payload, failures, "stage_results")
    _optional_list(payload, failures, "quality_gates")
    _optional_list(payload, failures, "review_confirmations")
    _optional_object(payload, failures, "artifact_hashes")
    _optional_list(payload, failures, "warnings")
    failures.raise_if_any()


def _validate_review_patch(payload: dict[str, Any], document_type: str) -> None:
    failures = _ContractFailureCollector(document_type)
    if payload.get("review_patch_version") != REVIEW_PATCH_VERSION:
        failures.add(f"review_patch_version must be {REVIEW_PATCH_VERSION!r}")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        failures.add("items must be a non-empty list")
        failures.raise_if_any()
        return
    for index, item in enumerate(items):
        _validate_review_patch_item(payload, item, index, failures)
    failures.raise_if_any()


def _validate_review_patch_item(
    patch: dict[str, Any],
    item: Any,
    index: int,
    failures: _ContractFailureCollector,
) -> None:
    if not isinstance(item, dict):
        failures.add(f"items[{index}] must be an object")
        return
    action = _clean_text(item.get("action", patch.get("action")))
    if action not in {"confirm", "correct"}:
        failures.add(f"items[{index}].action must be 'confirm' or 'correct'")
    target = _clean_text(item.get("target", patch.get("target")))
    if ":" not in target:
        failures.add(f"items[{index}].target must use type:id")
    if not _clean_text(item.get("confirmed_by", patch.get("confirmed_by"))):
        failures.add(f"items[{index}].confirmed_by must be a non-empty string")
    if not _clean_text(item.get("confirmed_at", patch.get("confirmed_at"))):
        failures.add(f"items[{index}].confirmed_at must be a non-empty string")
    if not _clean_text(item.get("reason", patch.get("reason"))):
        failures.add(f"items[{index}].reason must be a non-empty string")
    if action == "correct" and "value" not in item:
        failures.add(f"items[{index}].value is required for correction")
    if action == "correct" and not target.startswith("pending_field:"):
        if not _clean_text(item.get("field")):
            failures.add(f"items[{index}].field is required for correction")
    evidence_refs = item.get("evidence_refs", patch.get("evidence_refs", []))
    if evidence_refs is None:
        evidence_refs = []
    if not isinstance(evidence_refs, list) or not all(
        isinstance(ref, str) and ref.strip() for ref in evidence_refs
    ):
        failures.add(f"items[{index}].evidence_refs must be a list of strings")
    manual_event = _clean_text(
        item.get("manual_confirmation_event", patch.get("manual_confirmation_event"))
    )
    if isinstance(evidence_refs, list) and not evidence_refs and not manual_event:
        failures.add(
            f"items[{index}] must cite evidence_refs or manual_confirmation_event"
        )


def _validate_edit_patch(payload: dict[str, Any], document_type: str) -> None:
    failures = _ContractFailureCollector(document_type)
    if payload.get("edit_patch_version") != EDIT_PATCH_VERSION:
        failures.add(f"edit_patch_version must be {EDIT_PATCH_VERSION!r}")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        failures.add("items must be a non-empty list")
        failures.raise_if_any()
        return
    for index, item in enumerate(items):
        _validate_edit_patch_item(item, index, failures)
    failures.raise_if_any()


def _validate_edit_patch_item(
    item: Any,
    index: int,
    failures: _ContractFailureCollector,
) -> None:
    if not isinstance(item, dict):
        failures.add(f"items[{index}] must be an object")
        return
    action = _clean_text(item.get("action"))
    if action not in {"add", "update", "soft_delete", "confirm"}:
        failures.add(
            f"items[{index}].action must be add, update, soft_delete, or confirm"
        )
    table = _clean_text(item.get("table"))
    if table not in {"process_flow", "pfmea", "control_plan"}:
        failures.add(
            f"items[{index}].table must be process_flow, pfmea, or control_plan"
        )
    if action == "add":
        if not isinstance(item.get("row"), dict):
            failures.add(f"items[{index}].row is required for add")
    elif not _clean_text(item.get("target_id")):
        failures.add(f"items[{index}].target_id must be a non-empty string")
    if action == "update" and not isinstance(item.get("changes"), dict):
        failures.add(f"items[{index}].changes must be an object for update")


def _validate_apqp_chain_draft_result(payload: dict[str, Any], document_type: str) -> None:
    failures = _ContractFailureCollector(document_type)
    status = _clean_text(payload.get("status"))
    if status not in {"draft_ready", "blocked"}:
        failures.add("status must be 'draft_ready' or 'blocked'")
    if payload.get("draft_is_formal_export") is not False:
        failures.add("draft_is_formal_export must be false")
    draft = payload.get("draft")
    if draft is not None:
        _validate_nested_apqp_chain(draft, failures, "draft")
    _optional_object(payload, failures, "quality_gate", allow_none=True)
    manual_review = payload.get("manual_review")
    if not isinstance(manual_review, dict):
        failures.add("manual_review must be an object")
    else:
        if not isinstance(manual_review.get("required"), bool):
            failures.add("manual_review.required must be boolean")
        if not isinstance(manual_review.get("items"), list):
            failures.add("manual_review.items must be a list")
    stage_results = payload.get("stage_results")
    if not isinstance(stage_results, list):
        failures.add("stage_results must be a list")
    else:
        for index, result in enumerate(stage_results):
            if not isinstance(result, dict):
                failures.add(f"stage_results[{index}] must be an object")
    failures.raise_if_any()


def _validate_three_table_generation_result(payload: dict[str, Any], document_type: str) -> None:
    failures = _ContractFailureCollector(document_type)
    status = _clean_text(payload.get("status"))
    if status not in {"draft_ready", "needs_review", "blocked"}:
        failures.add("status must be 'draft_ready', 'needs_review', or 'blocked'")
    for field_name in ("quality_gate", "exports", "manifest"):
        _optional_object(payload, failures, field_name)
    for field_name in (
        "drawing_analysis",
        "process_flow",
        "pfmea",
        "control_plan",
    ):
        value = payload.get(field_name)
        if value is not None and not isinstance(value, dict):
            failures.add(f"{field_name} must be an object or null")
    manual_review = payload.get("manual_review")
    if manual_review is not None and not isinstance(manual_review, dict):
        failures.add("manual_review must be an object")
    failures.raise_if_any()


def _validate_apqp_chain_review_result(payload: dict[str, Any], document_type: str) -> None:
    failures = _ContractFailureCollector(document_type)
    if not _clean_text(payload.get("status")):
        failures.add("status must be a non-empty string")
    review_patch = _get_field_value(payload, document_type, "review_patch")
    if review_patch is not None:
        if not isinstance(review_patch, dict):
            failures.add("review_patch must be an object")
        else:
            try:
                validate_bundle_schema(review_patch, "review_patch")
            except (BundleSchemaError, BundleSchemaTypeError) as exc:
                failures.add(f"review_patch is invalid: {exc}")
    confirmations = payload.get("review_confirmations")
    if confirmations is not None and not isinstance(confirmations, list):
        failures.add("review_confirmations must be a list")
    reviewed_chain = _get_field_value(payload, document_type, "reviewed_chain")
    _validate_nested_apqp_chain(reviewed_chain, failures, "reviewed_chain")
    _optional_object(payload, failures, "quality_gate", allow_none=True)
    _optional_object(payload, failures, "manual_review", allow_none=True)
    failures.raise_if_any()


def _validate_nested_apqp_chain(
    value: Any, failures: _ContractFailureCollector, field_name: str
) -> None:
    if not isinstance(value, dict):
        failures.add(f"{field_name} must be an apqp_chain object")
        return
    try:
        validate_bundle_schema(value, "apqp_chain")
    except (BundleSchemaError, BundleSchemaTypeError) as exc:
        failures.add(f"{field_name} is not a valid apqp_chain: {exc}")


def _optional_object(
    payload: dict[str, Any],
    failures: _ContractFailureCollector,
    field_name: str,
    *,
    allow_none: bool = False,
) -> None:
    if field_name not in payload:
        return
    value = payload[field_name]
    if value is None and allow_none:
        return

    if not isinstance(value, dict):
        failures.add(f"{field_name} must be an object")


def _optional_list(
    payload: dict[str, Any],
    failures: _ContractFailureCollector,
    field_name: str,
    *,
    allow_none: bool = False,
) -> None:
    if field_name not in payload:
        return
    value = payload[field_name]
    if value is None and allow_none:
        return
    if not isinstance(value, list):
        failures.add(f"{field_name} must be a list")
