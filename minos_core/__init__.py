"""MINOS Core public API."""

from .audit import AuditItem, AuditReport, audit_chain
from .analyze import analyze_evidence_bundle, analyze_evidence_bundle_with_ai
from .brainstorm import brainstorm_failure_modes_from_pfd
from .config import SampleMetadata, list_samples, load_sample_metadata
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
from .generate_pfd import generate_pfd_from_analysis
from .generate_pfmea import generate_pfmea_from_candidates
from .generate_control_plan import generate_control_plan_from_pfmea
from .ingest import ingest_evidence_bundle
from .pipeline import apply_review
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
from .review_patch import REVIEW_PATCH_VERSION, ReviewPatchError, apply_review_patch
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
    "AuditItem",
    "AuditReport",
    "BundleSchemaError",
    "BundleSchemaTypeError",
    "Characteristic",
    "ControlItem",
    "Drawing",
    "Evidence",
    "FailureMode",
    "ProcessStep",
    "Product",
    "REVIEW_PATCH_VERSION",
    "RUN_MANIFEST_SCHEMA_VERSION",
    "ReviewPatchError",
    "SampleMetadata",
    "StageContext",
    "StageQualityGate",
    "StageResult",
    "TraceLink",
    "analyze_evidence_bundle",
    "analyze_evidence_bundle_with_ai",
    "apply_review",
    "apply_review_patch",
    "assemble_generated_apqp_chain",
    "artifact_sha256",
    "audit_chain",
    "brainstorm_failure_modes_from_pfd",
    "build_run_manifest",
    "evaluate_analysis_bundle_gate",
    "evaluate_brainstorm_failure_modes_input_gate",
    "evaluate_control_plan_bundle_gate",
    "evaluate_failure_mode_candidates_gate",
    "evaluate_pfmea_bundle_gate",
    "evaluate_pfd_bundle_gate",
    "evaluate_stage_gate",
    "generate_control_plan_from_pfmea",
    "generate_pfd_from_analysis",
    "generate_pfmea_from_candidates",
    "ingest_evidence_bundle",
    "list_samples",
    "load_sample_metadata",
    "run_stage",
    "sha256_bytes",
    "sha256_file",
    "sha256_json",
    "validate_bundle_schema",
    "validate_chain",
]
