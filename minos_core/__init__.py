"""MINOS Core public API."""

from .audit import AuditItem, AuditReport, audit_chain
from .analyze import analyze_evidence_bundle, analyze_evidence_bundle_with_ai
from .automation_review import (
    AUTOMATION_REVIEW_VERSION,
    DEFAULT_BATCH_CONFIRM_CONFIDENCE,
    automation_review_issue,
    build_automation_review,
    build_batch_confirm_patch,
)
from .brainstorm import brainstorm_failure_modes_from_pfd
from .config import SampleMetadata, list_samples, load_sample_metadata
from .adapters.multimodal import (
    FakeMultimodalDrawingAnalyzer,
    MultimodalDrawingAnalyzer,
    MultimodalDrawingResult,
    NotConfiguredMultimodalDrawingAnalyzer,
    OpenAIMultimodalError,
    OpenAIResponsesMultimodalDrawingAnalyzer,
)
from .domain import (
    APQPChain,
    Characteristic,
    ControlItem,
    Drawing,
    Evidence,
    FailureMode,
    ProcessStep,
    Product,
    TraceLink,
)
from .drawing_analysis import (
    DRAWING_ANALYSIS_SCHEMA_VERSION,
    DrawingAnalysisBundle,
    DrawingAnalysisError,
    DrawingRecognitionGate,
    analyze_drawing_pages,
    evaluate_drawing_recognition_gate,
)
from .drawing_input import (
    DrawingInputError,
    DrawingPageEvidence,
    DrawingSource,
    drawing_pages_to_evidence_bundle,
    load_drawing_source,
    render_drawing_pages,
)
from .drawing_to_pfd import infer_process_flow_from_drawing
from .edit_patch import (
    EDIT_PATCH_VERSION,
    EditPatchError,
    apply_edit_patch,
    evaluate_edit_export_gate,
    export_edited_three_tables,
)
from .generate_pfd import generate_pfd_from_analysis
from .generate_pfmea import generate_pfmea_from_candidates
from .generate_control_plan import generate_control_plan_from_pfmea
from .ingest import ingest_evidence_bundle
from .pipeline import (
    apply_review,
    export_draft_fixture,
    export_fixture,
    generate_draft,
    generate_three_tables_from_drawing,
)
from .pfd_to_pfmea_ai import infer_pfmea_from_process_flow
from .quality_gates import (
    StageQualityGate,
    evaluate_analysis_bundle_gate,
    evaluate_brainstorm_failure_modes_input_gate,
    evaluate_control_plan_bundle_gate,
    evaluate_failure_mode_candidates_gate,
    evaluate_pfmea_bundle_gate,
    evaluate_pfd_bundle_gate,
    evaluate_stage_gate,
)
from .review_patch import (
    REVIEW_PATCH_VERSION,
    ReviewPatchError,
    apply_review_patch,
    build_review_patch_template,
)
from .review_issues import (
    REVIEW_ISSUE_VERSION,
    ReviewIssue,
    build_review_issue,
    unresolved_review_issues,
)
from .run_manifest import (
    RUN_MANIFEST_SCHEMA_VERSION,
    artifact_sha256,
    build_run_manifest,
    sha256_bytes,
    sha256_file,
    sha256_json,
)
from .schemas import BundleSchemaError, BundleSchemaTypeError, validate_bundle_schema
from .stage import (
    StageContext,
    StageResult,
    assemble_generated_apqp_chain,
    run_stage,
)
from .validation import validate_chain

__all__ = [
    "APQPChain",
    "AUTOMATION_REVIEW_VERSION",
    "AuditItem",
    "AuditReport",
    "BundleSchemaError",
    "BundleSchemaTypeError",
    "Characteristic",
    "ControlItem",
    "DRAWING_ANALYSIS_SCHEMA_VERSION",
    "DEFAULT_BATCH_CONFIRM_CONFIDENCE",
    "Drawing",
    "DrawingAnalysisBundle",
    "DrawingAnalysisError",
    "DrawingInputError",
    "DrawingPageEvidence",
    "DrawingRecognitionGate",
    "DrawingSource",
    "EDIT_PATCH_VERSION",
    "EditPatchError",
    "Evidence",
    "FakeMultimodalDrawingAnalyzer",
    "FailureMode",
    "MultimodalDrawingAnalyzer",
    "MultimodalDrawingResult",
    "NotConfiguredMultimodalDrawingAnalyzer",
    "OpenAIMultimodalError",
    "OpenAIResponsesMultimodalDrawingAnalyzer",
    "ProcessStep",
    "Product",
    "REVIEW_PATCH_VERSION",
    "REVIEW_ISSUE_VERSION",
    "RUN_MANIFEST_SCHEMA_VERSION",
    "ReviewPatchError",
    "ReviewIssue",
    "SampleMetadata",
    "StageContext",
    "StageQualityGate",
    "StageResult",
    "TraceLink",
    "analyze_drawing_pages",
    "analyze_evidence_bundle",
    "analyze_evidence_bundle_with_ai",
    "apply_review",
    "apply_edit_patch",
    "apply_review_patch",
    "assemble_generated_apqp_chain",
    "artifact_sha256",
    "audit_chain",
    "automation_review_issue",
    "brainstorm_failure_modes_from_pfd",
    "build_review_patch_template",
    "build_review_issue",
    "build_automation_review",
    "build_batch_confirm_patch",
    "build_run_manifest",
    "drawing_pages_to_evidence_bundle",
    "evaluate_analysis_bundle_gate",
    "evaluate_brainstorm_failure_modes_input_gate",
    "evaluate_control_plan_bundle_gate",
    "evaluate_failure_mode_candidates_gate",
    "evaluate_pfmea_bundle_gate",
    "evaluate_pfd_bundle_gate",
    "evaluate_drawing_recognition_gate",
    "evaluate_edit_export_gate",
    "evaluate_stage_gate",
    "export_draft_fixture",
    "export_edited_three_tables",
    "export_fixture",
    "generate_control_plan_from_pfmea",
    "generate_draft",
    "generate_three_tables_from_drawing",
    "generate_pfd_from_analysis",
    "generate_pfmea_from_candidates",
    "ingest_evidence_bundle",
    "infer_pfmea_from_process_flow",
    "infer_process_flow_from_drawing",
    "list_samples",
    "load_drawing_source",
    "load_sample_metadata",
    "render_drawing_pages",
    "run_stage",
    "sha256_bytes",
    "sha256_file",
    "sha256_json",
    "validate_bundle_schema",
    "validate_chain",
    "unresolved_review_issues",
]
