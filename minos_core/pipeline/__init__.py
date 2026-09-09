"""Pipeline entry points for APQP workflow orchestration.

This module has been refactored into smaller submodules for better maintainability.
All public APIs are re-exported here to maintain backward compatibility.
"""

from __future__ import annotations

# Re-export exporter functions (used by tests)
from ..exporters.three_table_workbooks import (
    export_split_three_table_workbooks,
    export_three_table_workbook,
)

# Re-export quality gate functions (used by tests and other modules)
from ..quality_gates import evaluate_export_gate
from ..three_table_result import (
    dedupe_strings as _dedupe_strings,
)
from ..three_table_result import (
    three_table_manual_review as _three_table_manual_review,
)

# Re-export drawing analysis functions
# Re-export internal functions for testing
from .drawing_analysis import (
    ANALYSIS_MODES,
    DEFAULT_OCR_ENGINE,
    HYBRID_OCR_FALLBACK_WARNING,
    HYBRID_VISION_MAX_RETRIES,
    HYBRID_VISION_TIMEOUT_SECONDS,
    OCR_ENGINES,
    OCR_UNAVAILABLE_WARNING,
    _analyze_drawing_pages_for_mode,
    _attach_analysis_metadata,
    _effective_analysis_mode,
    _effective_ocr_engine,
    analyze_drawing_for_three_table_chain,
)
from .family_context import (
    OCR_FAMILY_LOCK_CONFIDENCE,
    _part_family_context_from_drawing,
)
from .hybrid_fusion import (
    OCR_IDENTITY_LOCK_CONFIDENCE,
    OCR_IDENTITY_LOCK_FIELDS,
)

# Re-export constants
# Re-export main orchestration functions
from .orchestration import (
    DRAFT_WARNING,
    GENERATED_DRAFT_STAGES,
    PIPELINE_STAGES,
    THREE_TABLE_DRAFT_WARNING,
    _three_table_generation_envelope,
    assemble_generated_apqp_chain,
    generate_draft,
    generate_three_tables_from_drawing,
)

# Re-export review and export functions
from .review_export import (
    apply_edit_patch,
    apply_review,
    evaluate_edit_export_gate,
    export_draft_fixture,
    export_edited_three_tables,
    export_fixture,
    validate_fixture,
)

__all__ = [
    # Constants
    "PIPELINE_STAGES",
    "GENERATED_DRAFT_STAGES",
    "DRAFT_WARNING",
    "THREE_TABLE_DRAFT_WARNING",
    "ANALYSIS_MODES",
    "OCR_ENGINES",
    "DEFAULT_OCR_ENGINE",
    "HYBRID_VISION_TIMEOUT_SECONDS",
    "HYBRID_VISION_MAX_RETRIES",
    "HYBRID_OCR_FALLBACK_WARNING",
    "OCR_UNAVAILABLE_WARNING",
    "OCR_IDENTITY_LOCK_CONFIDENCE",
    "OCR_IDENTITY_LOCK_FIELDS",
    "OCR_FAMILY_LOCK_CONFIDENCE",
    # Main orchestration
    "generate_draft",
    "generate_three_tables_from_drawing",
    "assemble_generated_apqp_chain",
    # Drawing analysis
    "analyze_drawing_for_three_table_chain",
    # Review and export
    "apply_review",
    "apply_edit_patch",
    "evaluate_edit_export_gate",
    "export_edited_three_tables",
    "validate_fixture",
    "export_fixture",
    "export_draft_fixture",
    # Internal functions (for testing)
    "_analyze_drawing_pages_for_mode",
    "_attach_analysis_metadata",
    "_effective_analysis_mode",
    "_effective_ocr_engine",
    "_dedupe_strings",
    "_three_table_manual_review",
    "_three_table_generation_envelope",
    "_part_family_context_from_drawing",
    # Quality gate functions
    "evaluate_export_gate",
    # Exporter functions (for testing)
    "export_three_table_workbook",
    "export_split_three_table_workbooks",
]
