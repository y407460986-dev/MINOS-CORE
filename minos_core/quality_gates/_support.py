"""Support utilities: evidence, confirmations, batch safety, review issues, tools.

This module re-exports all functions from the split modules for backward compatibility.
"""
from __future__ import annotations

# Re-export from core_evaluators
from .core_evaluators import (
    _ai_inferred_items,
    _confirmation_matches_value,
    _confirmed_field_paths,
    _confirmed_targets,
    _dedupe_preserve_order,
    _flagged_evidence_ids,
    _flagged_item_label,
    _flagged_item_labels,
    _float_value,
    _is_confirmed,
    _is_mechanical_trace_link,
    _metadata_list,
    _pending_field_paths,
    _pending_fields,
    _review_confirmations,
    _row_mapping_id,
    _row_needs_confirmation_items,
    _strict_aiag_vda_pfmea_gate_enabled,
    _trace_link_label,
    _without_confirmed,
)

# Re-export from evidence_coverage
from .evidence_coverage import (
    _evidence_coverage_report,
    _evidence_manual_review_items,
    _evidence_sufficient,
    _ingest_evidence_report,
    _iter_evidence_required_items,
    _stage_validation,
)

# Re-export from export_gate
from .export_gate import (
    _safe_ai_batch_confirmation_targets,
    _safe_ai_batch_row,
    _unsafe_ai_batch_review_issues,
    _with_safe_ai_batch_confirmations,
)

# Re-export from report_projections
from .report_projections import (
    _dedupe_review_issues,
    _dict_manual_review_items,
    _recommendation_manual_review_items,
    _review_issues_from_gate_debts,
    _row_needs_confirmation_manual_review_items,
)

__all__ = [
    "_ai_inferred_items",
    "_confirmation_matches_value",
    "_confirmed_field_paths",
    "_confirmed_targets",
    "_dedupe_preserve_order",
    "_dedupe_review_issues",
    "_dict_manual_review_items",
    "_evidence_coverage_report",
    "_evidence_manual_review_items",
    "_evidence_sufficient",
    "_flagged_evidence_ids",
    "_flagged_item_label",
    "_flagged_item_labels",
    "_float_value",
    "_ingest_evidence_report",
    "_is_confirmed",
    "_is_mechanical_trace_link",
    "_iter_evidence_required_items",
    "_metadata_list",
    "_pending_field_paths",
    "_pending_fields",
    "_recommendation_manual_review_items",
    "_review_confirmations",
    "_review_issues_from_gate_debts",
    "_row_mapping_id",
    "_row_needs_confirmation_items",
    "_row_needs_confirmation_manual_review_items",
    "_safe_ai_batch_confirmation_targets",
    "_safe_ai_batch_row",
    "_stage_validation",
    "_strict_aiag_vda_pfmea_gate_enabled",
    "_trace_link_label",
    "_unsafe_ai_batch_review_issues",
    "_with_safe_ai_batch_confirmations",
    "_without_confirmed",
]
