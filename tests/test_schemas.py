import copy
import unittest

from minos_core.schemas import (
    BundleSchemaError,
    BundleSchemaTypeError,
    validate_bundle_schema,
)

BASE_EVIDENCE = [
    {
        "evidence_id": "EV-001",
        "source": "fixture",
        "content": "Released evidence",
    }
]

BASE_APQP_CHAIN = {
    "document_type": "apqp_chain",
    "schema_version": "minos-core.generated.v1",
    "process_steps": [],
    "failure_modes": [],
    "controls": [],
    "evidence": BASE_EVIDENCE,
}

BASE_QUALITY_GATE = {
    "stage": "validate",
    "can_continue": True,
    "allow_user_export": False,
}

BASE_REVIEW_PATCH = {
    "review_patch_version": "minos-core.review_patch.v1",
    "confirmed_by": "qa.engineer",
    "confirmed_at": "2026-04-25T10:00:00Z",
    "reason": "人工复核已确认",
    "evidence_refs": ["EV-001"],
    "items": [
        {
            "action": "confirm",
            "target": "evidence:EV-001",
        }
    ],
}

BASE_EDIT_PATCH = {
    "edit_patch_version": "minos-core.edit_patch.v1",
    "edited_by": "process.engineer",
    "edited_at": "2026-04-26T10:00:00Z",
    "reason": "人工编辑三表草案",
    "items": [
        {
            "action": "update",
            "table": "pfmea",
            "target_id": "PFMEA-P10-001",
            "changes": {"failure_mode": "人工修正后的失效模式"},
        }
    ],
}


VALID_BUNDLES = {
    "evidence_bundle": {
        "document_type": "evidence_bundle",
        "schema_version": "0.1",
        "evidence": BASE_EVIDENCE,
    },
    "drawing_analysis_bundle": {
        "document_type": "drawing_analysis_bundle",
        "schema_version": "minos-core.drawing_analysis.v1",
        "drawing_identity": {},
        "materials": [],
        "surface_treatments": [],
        "dimensions": [],
        "tolerances": [],
        "special_characteristics": [],
        "technical_requirements": [],
        "inspection_requirements": [],
        "manufacturing_clues": [],
        "uncertainties": [],
        "evidence": BASE_EVIDENCE,
    },
    "analysis_bundle": {
        "document_type": "analysis_bundle",
        "schema_version": "0.1",
        "drawings": [],
        "characteristics": [],
        "process_clues": [],
        "evidence": BASE_EVIDENCE,
    },
    "process_flow": {
        "document_type": "process_flow",
        "schema_version": "minos-core.generated.v1",
        "steps": [],
        "links": [],
        "evidence": BASE_EVIDENCE,
    },
    "failure_mode_candidates": {
        "document_type": "failure_mode_candidates",
        "schema_version": "minos-core.generated.v1",
        "candidates": [],
        "evidence": BASE_EVIDENCE,
    },
    "pfmea": {
        "document_type": "pfmea",
        "schema_version": "minos-core.generated.v1",
        "rows": [],
        "evidence": BASE_EVIDENCE,
    },
    "control_plan": {
        "document_type": "control_plan",
        "schema_version": "minos-core.generated.v1",
        "rows": [],
        "evidence": BASE_EVIDENCE,
    },
    "apqp_chain": BASE_APQP_CHAIN,
    "input_package": {
        "document_type": "input_package",
        "schema_version": "minos-core.input_package.v1",
        "package_id": "UNIT-INPUT-PACKAGE-001",
        "evidence_path": "evidence.json",
        "review_patch_path": "review_patch.json",
        "metadata": {"source": "unit-test"},
    },
    "run_manifest": {
        "document_type": "run_manifest",
        "schema_version": "minos-core.run_manifest.v1",
        "run_id": "RUN-001",
        "created_at": "2026-04-25T10:00:00Z",
        "inputs": {"source": "fixture"},
        "outputs": {"draft": "draft-result.json"},
        "stages": [
            {
                "stage": "ingest",
                "status": "ok",
            }
        ],
        "stage_results": [
            {
                "stage": "ingest",
                "status": "ok",
            }
        ],
        "quality_gates": [BASE_QUALITY_GATE],
        "review_confirmations": [],
        "artifact_hashes": {"draft_result": "a" * 64},
        "warnings": [],
    },
    "review_patch": BASE_REVIEW_PATCH,
    "edit_patch": BASE_EDIT_PATCH,
    "apqp_chain_draft_result": {
        "document_type": "apqp_chain_draft_result",
        "status": "draft_ready",
        "draft_notice": "Generated APQPChain draft only.",
        "draft_is_formal_export": False,
        "draft": BASE_APQP_CHAIN,
        "quality_gate": BASE_QUALITY_GATE,
        "manual_review": {"required": True, "items": []},
        "stage_results": [{"stage": "ingest", "status": "ok"}],
    },
    "apqp_chain_review_result": {
        "document_type": "apqp_chain_review_result",
        "status": "reviewed",
        "review_patch": BASE_REVIEW_PATCH,
        "reviewed_chain": BASE_APQP_CHAIN,
        "quality_gate": BASE_QUALITY_GATE,
    },
}


class BundleSchemaTests(unittest.TestCase):
    def test_validate_bundle_schema_accepts_supported_document_types(self):
        for document_type, payload in VALID_BUNDLES.items():
            with self.subTest(document_type=document_type):
                self.assertTrue(validate_bundle_schema(copy.deepcopy(payload)))
                self.assertTrue(
                    validate_bundle_schema(copy.deepcopy(payload), document_type)
                )

    def test_validate_bundle_schema_requires_dict_payload(self):
        with self.assertRaisesRegex(BundleSchemaTypeError, "payload must be dict"):
            validate_bundle_schema([], "evidence_bundle")

    def test_validate_bundle_schema_rejects_document_type_mismatch(self):
        payload = copy.deepcopy(VALID_BUNDLES["process_flow"])

        with self.assertRaisesRegex(
            BundleSchemaError,
            "pfmea.*document_type mismatch.*expected pfmea, got process_flow",
        ):
            validate_bundle_schema(payload, "pfmea")

    def test_validate_bundle_schema_requires_schema_version_for_stage_bundles(self):
        payload = copy.deepcopy(VALID_BUNDLES["process_flow"])
        del payload["schema_version"]

        with self.assertRaisesRegex(
            BundleSchemaError,
            "process_flow.*schema_version",
        ):
            validate_bundle_schema(payload)

    def test_validate_bundle_schema_reports_document_type_and_missing_fields(self):
        payload = {
            "document_type": "analysis_bundle",
            "schema_version": "0.1",
            "drawings": [],
            "evidence": BASE_EVIDENCE,
        }

        with self.assertRaisesRegex(
            BundleSchemaError,
            "analysis_bundle.*characteristics.*process_clues",
        ):
            validate_bundle_schema(payload)

    def test_validate_bundle_schema_rejects_unsupported_document_type(self):
        with self.assertRaisesRegex(
            BundleSchemaError,
            "unknown_bundle.*unsupported document_type",
        ):
            validate_bundle_schema(
                {"document_type": "unknown_bundle", "schema_version": "1"}
            )

    def test_validate_bundle_schema_keeps_minimal_apqp_chain_legacy_compatibility(self):
        payload = {
            "process_steps": [],
            "failure_modes": [],
            "controls": [],
            "evidence": BASE_EVIDENCE,
        }

        self.assertTrue(validate_bundle_schema(payload, "apqp_chain"))

    def test_validate_bundle_schema_accepts_legacy_combined_apqp_fixture(self):
        payload = {
            "process_flow": {"steps": [], "links": []},
            "pfmea": {"rows": []},
            "control_plan": {"rows": []},
            "evidence": BASE_EVIDENCE,
        }

        self.assertTrue(validate_bundle_schema(payload, "apqp_chain"))
        self.assertTrue(validate_bundle_schema(payload))

    def test_validate_bundle_schema_still_requires_apqp_chain_core_fields(self):
        payload = {
            "document_type": "apqp_chain",
            "schema_version": "minos-core.generated.v1",
            "process_steps": [],
            "failure_modes": [],
            "evidence": BASE_EVIDENCE,
        }

        with self.assertRaisesRegex(BundleSchemaError, "apqp_chain.*controls"):
            validate_bundle_schema(payload)

    def test_validate_bundle_schema_accepts_review_patch_without_document_type(self):
        payload = copy.deepcopy(BASE_REVIEW_PATCH)

        self.assertTrue(validate_bundle_schema(payload))
        self.assertTrue(validate_bundle_schema(payload, "review_patch"))

    def test_validate_bundle_schema_accepts_edit_patch_without_document_type(self):
        payload = copy.deepcopy(BASE_EDIT_PATCH)

        self.assertTrue(validate_bundle_schema(payload))
        self.assertTrue(validate_bundle_schema(payload, "edit_patch"))

    def test_validate_edit_patch_reports_action_table_and_target_errors(self):
        payload = {
            "document_type": "edit_patch",
            "edit_patch_version": "minos-core.edit_patch.v1",
            "items": [
                {
                    "action": "replace",
                    "table": "unknown",
                    "changes": [],
                }
            ],
        }

        with self.assertRaisesRegex(
            BundleSchemaError,
            r"edit_patch.*items\[0\]\.action.*items\[0\]\.table.*target_id",
        ):
            validate_bundle_schema(payload)

    def test_validate_review_patch_reports_action_target_and_basis_errors(self):
        payload = {
            "document_type": "review_patch",
            "review_patch_version": "minos-core.review_patch.v1",
            "items": [
                {
                    "action": "approve",
                    "target": "bad-target",
                    "confirmed_by": "qa.engineer",
                    "confirmed_at": "2026-04-25T10:00:00Z",
                    "reason": "invalid item should be rejected",
                }
            ],
        }

        with self.assertRaisesRegex(
            BundleSchemaError,
            r"review_patch.*items\[0\]\.action.*items\[0\]\.target.*evidence_refs",
        ):
            validate_bundle_schema(payload)

    def test_validate_input_package_requires_package_id_and_evidence_path(self):
        payload = {
            "document_type": "input_package",
            "schema_version": "minos-core.input_package.v1",
            "metadata": {},
        }

        with self.assertRaisesRegex(
            BundleSchemaError,
            "input_package.*package_id.*evidence_path",
        ):
            validate_bundle_schema(payload)

    def test_validate_input_package_requires_metadata_object(self):
        payload = copy.deepcopy(VALID_BUNDLES["input_package"])
        payload["metadata"] = []

        with self.assertRaisesRegex(
            BundleSchemaError,
            "input_package.*metadata must be an object",
        ):
            validate_bundle_schema(payload)

    def test_validate_input_package_requires_v1_schema_version(self):
        payload = copy.deepcopy(VALID_BUNDLES["input_package"])
        payload["schema_version"] = "minos-core.trusted_delivery.v1"

        with self.assertRaisesRegex(
            BundleSchemaError,
            "input_package.*schema_version must be 'minos-core.input_package.v1'",
        ):
            validate_bundle_schema(payload)

    def test_validate_input_package_accepts_source_documents_metadata(self):
        payload = copy.deepcopy(VALID_BUNDLES["input_package"])
        payload["source_documents"] = [
            {"document_id": "DOC-001", "path": "drawing.pdf"}
        ]

        self.assertTrue(validate_bundle_schema(payload))

    def test_validate_run_manifest_reports_stage_status_paths(self):
        payload = {
            "document_type": "run_manifest",
            "schema_version": "minos-core.trusted_delivery.v1",
            "run_id": "RUN-001",
            "stages": [{"stage": "ingest"}],
        }

        with self.assertRaisesRegex(
            BundleSchemaError,
            r"run_manifest.*stages\[0\]\.status",
        ):
            validate_bundle_schema(payload)

    def test_validate_run_manifest_accepts_empty_stage_list_for_non_stage_artifacts(self):
        payload = copy.deepcopy(VALID_BUNDLES["run_manifest"])
        payload["stages"] = []
        payload["stage_results"] = []

        self.assertTrue(validate_bundle_schema(payload))

    def test_validate_run_manifest_reports_optional_audit_field_shapes(self):
        payload = copy.deepcopy(VALID_BUNDLES["run_manifest"])
        payload["artifact_hashes"] = []
        payload["warnings"] = {}

        with self.assertRaisesRegex(
            BundleSchemaError,
            "run_manifest.*artifact_hashes must be an object.*warnings must be a list",
        ):
            validate_bundle_schema(payload)

    def test_validate_draft_result_preserves_current_generate_draft_compatibility(self):
        payload = copy.deepcopy(VALID_BUNDLES["apqp_chain_draft_result"])
        payload["blocked_stage"] = None

        self.assertTrue(validate_bundle_schema(payload))

    def test_validate_draft_result_requires_draft_only_flag(self):
        payload = copy.deepcopy(VALID_BUNDLES["apqp_chain_draft_result"])
        payload["draft_is_formal_export"] = True

        with self.assertRaisesRegex(
            BundleSchemaError,
            "apqp_chain_draft_result.*draft_is_formal_export must be false",
        ):
            validate_bundle_schema(payload)

    def test_validate_review_result_accepts_legacy_alias_fields(self):
        payload = {
            "document_type": "apqp_chain_review_result",
            "status": "reviewed",
            "patch": copy.deepcopy(BASE_REVIEW_PATCH),
            "chain": copy.deepcopy(BASE_APQP_CHAIN),
            "export_gate": BASE_QUALITY_GATE,
        }

        self.assertTrue(validate_bundle_schema(payload))

    def test_validate_review_result_reports_nested_contract_errors(self):
        payload = copy.deepcopy(VALID_BUNDLES["apqp_chain_review_result"])
        payload["reviewed_chain"] = {"document_type": "apqp_chain"}

        with self.assertRaisesRegex(
            BundleSchemaError,
            "apqp_chain_review_result.*reviewed_chain.*process_steps.*failure_modes.*controls.*evidence",
        ):
            validate_bundle_schema(payload)


if __name__ == "__main__":
    unittest.main()
