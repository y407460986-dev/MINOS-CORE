"""Review patch application and export operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..exporters import export_apqp_workbook
from ..quality_gates import evaluate_export_gate, require_export_gate
from ..review_patch import REVIEW_CONFIRMATIONS_KEY, apply_review_patch
from .utilities import (
    _build_chain,
    _default_output_path,
    _dump_json_value,
    _load_review_patch_payload,
    _load_review_source_payload,
    _write_json_file,
    _write_manifest_file,
)

# Warning messages
DRAFT_WARNING = (
    "当前结果仅为 APQP 工程草案，不是正式导出文件；必须经过质量门检查和人工工程复核后，"
    "才能用于正式放行。"
)


def apply_review(
    draft_result_or_chain: str | Path | dict[str, Any],
    review_patch: str | Path | dict[str, Any],
    output_path: str | Path | None = None,
    manifest_output: str | Path | None = None,
) -> dict[str, Any]:
    """Apply a human review patch and return a reviewed APQPChain envelope.

    ``draft_result_or_chain`` may be an ``apqp_chain_draft_result`` envelope, an
    ``apqp_chain_review_result`` envelope, a raw APQPChain JSON file, or a fixture
    directory. ``review_patch`` must be a review patch JSON object accepted by
    :func:`review_patch.apply_review_patch`.
    """

    source_payload = _load_review_source_payload(draft_result_or_chain)
    patch_payload = _load_review_patch_payload(review_patch)
    patched_chain = apply_review_patch(source_payload, patch_payload)
    quality_gate = evaluate_export_gate(patched_chain)
    envelope = {
        "document_type": "apqp_chain_review_result",
        "patched_chain": patched_chain,
        "quality_gate": quality_gate.model_dump(),
        "review_confirmations": list(
            patched_chain.get("metadata", {}).get(REVIEW_CONFIRMATIONS_KEY, [])
        ),
        "manual_review": {
            "required": bool(quality_gate.needs_human_review),
            "items": [_dump_json_value(item) for item in quality_gate.manual_review_items],
        },
        "final_export_allowed": bool(quality_gate.allow_user_export),
    }
    if output_path is not None:
        _write_json_file(output_path, envelope)
    if manifest_output is not None:
        _write_manifest_file(
            manifest_output,
            inputs={"source": draft_result_or_chain, "review_patch": review_patch},
            outputs=envelope,
            stage_results=[],
            quality_gates=[envelope.get("quality_gate")],
            review_confirmations=envelope.get("review_confirmations", []),
            artifacts={"review_result": envelope, "patched_chain": patched_chain},
            warnings=[]
            if quality_gate.allow_user_export
            else ["导出质量门未通过，当前结果不允许正式导出。"],
        )
    return envelope


def apply_edit_patch(source: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Apply a human edit patch to a three-table result or APQP chain."""

    from ..edit_patch import apply_edit_patch as _apply_edit_patch

    return _apply_edit_patch(source, patch)


def evaluate_edit_export_gate(source: dict[str, Any]) -> dict[str, Any]:
    """Evaluate whether an edited three-table payload may be final-exported."""

    from ..edit_patch import evaluate_edit_export_gate as _evaluate_edit_export_gate

    return _evaluate_edit_export_gate(source)


def export_edited_three_tables(
    source: dict[str, Any],
    output_dir: str | Path,
    export_mode: str = "draft",
) -> dict[str, Any]:
    """Export edited three-table workbooks after applying edit gate rules."""

    from ..edit_patch import export_edited_three_tables as _export_edited_three_tables

    return _export_edited_three_tables(source, output_dir, export_mode)


def validate_fixture(fixture: str | Path | dict[str, Any]) -> Any:
    """Load an APQP fixture, build the domain chain, and validate it."""
    from ..adapters.fixture_json import load_fixture_payload
    from ..validation import validate_chain

    payload = load_fixture_payload(fixture)
    chain = _build_chain(payload)
    result = validate_chain(chain)
    if not result:
        raise ValueError("APQP chain validation failed:\n" + "\n".join(result.messages))
    return result


def export_fixture(
    fixture: str | Path | dict[str, Any],
    output_path: str | Path | None = None,
    manifest_output: str | Path | None = None,
) -> Path:
    """Run the shared final export gate and export the fixed Chinese workbook."""
    from ..adapters.fixture_json import load_fixture_payload

    payload = load_fixture_payload(fixture)
    chain = _build_chain(payload)
    require_export_gate(chain)
    destination = (
        Path(output_path)
        if output_path is not None
        else _default_output_path(fixture, chain)
    )
    exported = export_apqp_workbook(
        chain, destination, require_gate=False, export_mode="final"
    )
    if manifest_output is not None:
        gate = evaluate_export_gate(chain)
        _write_manifest_file(
            manifest_output,
            inputs=fixture,
            outputs={"export_path": exported},
            stage_results=[],
            quality_gates=[gate.model_dump()],
            review_confirmations=list(
                payload.get("metadata", {}).get(REVIEW_CONFIRMATIONS_KEY, [])
            ),
            artifacts={"final_export": exported},
            warnings=[],
        )
    return exported


def export_draft_fixture(
    fixture: str | Path | dict[str, Any],
    output_path: str | Path | None = None,
    manifest_output: str | Path | None = None,
) -> Path:
    """Export a draft-only APQP workbook with review warnings and gate details."""
    from ..adapters.fixture_json import load_fixture_payload

    payload = load_fixture_payload(fixture)
    chain = _build_chain(payload)
    quality_gate = evaluate_export_gate(chain)
    destination = (
        Path(output_path)
        if output_path is not None
        else _default_output_path(fixture, chain)
    )
    exported = export_apqp_workbook(
        chain,
        destination,
        require_gate=False,
        export_mode="draft",
        quality_gate=quality_gate,
    )
    if manifest_output is not None:
        _write_manifest_file(
            manifest_output,
            inputs=fixture,
            outputs={"export_path": exported},
            stage_results=[],
            quality_gates=[quality_gate.model_dump()],
            review_confirmations=list(
                payload.get("metadata", {}).get(REVIEW_CONFIRMATIONS_KEY, [])
            ),
            artifacts={"draft_export": exported},
            warnings=[DRAFT_WARNING],
        )
    return exported
