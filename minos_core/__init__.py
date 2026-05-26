"""MINOS Core public API."""

__version__ = "2.0.0"

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
    EntityType,
    Evidence,
    FailureMode,
    ProcessStep,
    Product,
    TraceLink,
    TraceLinkType,
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
from .knowledge_recommendation import (
    recommend_from_knowledge,
    recommend_from_local_knowledge,
    unresolved_recommendations,
)
from .part_family_classifier import classify_part_family, get_default_family_index
from .part_family_knowledge import load_part_family_index, load_part_family_knowledge
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
from .three_table_linkage import (
    build_three_table_linkage_map,
    evaluate_three_table_linkage,
    find_linkage_gaps,
)
from .characteristic_registry import (
    build_characteristic_registry,
    attach_characteristics_to_three_tables,
)
from .change_management import (
    compare_three_table_baseline,
    analyze_linked_change_impacts,
)
from .risk_structure import (
    build_risk_structure,
)

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
    "EntityType",
    "TraceLink",
    "TraceLinkType",
    "analyze_drawing_pages",
    "analyze_evidence_bundle",
    "analyze_evidence_bundle_with_ai",
    "analyze_linked_change_impacts",
    "apply_review",
    "apply_edit_patch",
    "apply_review_patch",
    "assemble_generated_apqp_chain",
    "artifact_sha256",
    "attach_characteristics_to_three_tables",
    "audit_chain",
    "automation_review_issue",
    "brainstorm_failure_modes_from_pfd",
    "build_review_patch_template",
    "build_review_issue",
    "build_automation_review",
    "build_batch_confirm_patch",
    "build_characteristic_registry",
    "build_risk_structure",
    "build_run_manifest",
    "build_three_table_linkage_map",
    "classify_part_family",
    "compare_three_table_baseline",
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
    "evaluate_three_table_linkage",
    "export_draft_fixture",
    "export_edited_three_tables",
    "export_fixture",
    "find_linkage_gaps",
    "generate_control_plan_from_pfmea",
    "generate_draft",
    "generate_three_tables_from_drawing",
    "generate_pfd_from_analysis",
    "generate_pfmea_from_candidates",
    "get_default_family_index",
    "ingest_evidence_bundle",
    "infer_pfmea_from_process_flow",
    "infer_process_flow_from_drawing",
    "list_samples",
    "load_drawing_source",
    "load_part_family_index",
    "load_part_family_knowledge",
    "load_sample_metadata",
    "recommend_from_knowledge",
    "recommend_from_local_knowledge",
    "render_drawing_pages",
    "run_stage",
    "sha256_bytes",
    "sha256_file",
    "sha256_json",
    "validate_bundle_schema",
    "validate_chain",
    "unresolved_recommendations",
    "unresolved_review_issues",
]
