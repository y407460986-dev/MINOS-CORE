from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from minos_core.adapters.fixture_json import load_fixture_payload
from minos_core.pipeline import apply_review, generate_draft
from minos_core.schemas import BundleSchemaError, validate_bundle_schema
from minos_core.stage import run_stage

ROOT = Path(__file__).resolve().parents[1]
DEMO_PACKAGE = ROOT / "tests" / "fixtures" / "demo_input_package"
REALISTIC_PACKAGE = ROOT / "tests" / "fixtures" / "realistic_input_package"
REAL_PROJECT_TEMPLATE = ROOT / "tests" / "fixtures" / "real_project_input_package_template"
NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _workbook_text(path: Path) -> str:
    values = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith("xl/worksheets/sheet") or not name.endswith(".xml"):
                continue
            xml = ElementTree.fromstring(archive.read(name))
            for text_node in xml.findall(".//main:t", NS):
                values.append(text_node.text or "")
    return "\n".join(values)


def _sheet_names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        workbook_xml = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    return [node.attrib["name"] for node in workbook_xml.findall(".//main:sheet", NS)]


class InputPackageTests(unittest.TestCase):
    def test_demo_input_package_json_matches_schema_contract(self):
        payload = json.loads((DEMO_PACKAGE / "input_package.json").read_text(encoding="utf-8"))

        self.assertTrue(validate_bundle_schema(payload, "input_package"))

    def test_input_package_schema_rejects_missing_evidence_path(self):
        payload = json.loads((DEMO_PACKAGE / "input_package.json").read_text(encoding="utf-8"))
        payload.pop("evidence_path")

        with self.assertRaisesRegex(BundleSchemaError, "input_package.*evidence_path"):
            validate_bundle_schema(payload, "input_package")

    def test_input_package_schema_rejects_missing_package_id(self):
        payload = json.loads((DEMO_PACKAGE / "input_package.json").read_text(encoding="utf-8"))
        payload.pop("package_id")

        with self.assertRaisesRegex(BundleSchemaError, "input_package.*package_id"):
            validate_bundle_schema(payload, "input_package")

    def test_adapter_rejects_input_package_missing_evidence_path(self):
        payload = json.loads((DEMO_PACKAGE / "input_package.json").read_text(encoding="utf-8"))
        payload.pop("evidence_path")

        with self.assertRaisesRegex(BundleSchemaError, "input_package.*evidence_path"):
            load_fixture_payload(payload)

    def test_fixture_json_loads_input_package_directory_as_evidence_bundle(self):
        payload = load_fixture_payload(DEMO_PACKAGE)

        self.assertEqual(payload["document_type"], "evidence_bundle")
        self.assertEqual(payload["metadata"]["ingest_mode"], "input_package")
        self.assertEqual(payload["metadata"]["input_package_id"], "DEMO-INPUT-PACKAGE-001")
        self.assertEqual(
            payload["metadata"]["review_patch"]["review_patch_version"],
            "minos-core.review_patch.v1",
        )
        self.assertEqual(len(payload["evidence"]), 6)
        self.assertTrue(
            any(
                item["evidence_id"] == "EV-DEMO-REQ-001"
                and item["needs_confirmation"]
                for item in payload["evidence"]
            )
        )

    def test_ingest_accepts_input_package_directory_and_json_file(self):
        directory_result = run_stage(DEMO_PACKAGE, stage="ingest")
        file_result = run_stage(DEMO_PACKAGE / "input_package.json", stage="ingest")

        for result in (directory_result, file_result):
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.output["document_type"], "evidence_bundle")
            self.assertEqual(result.output["metadata"]["ingest_mode"], "input_package")
            self.assertIn("EV-DEMO-REQ-001", result.quality_gate.needs_confirmation_items)
            self.assertFalse(result.quality_gate.allow_user_export)

    def test_demo_package_generates_review_required_draft_then_review_allows_export(self):
        draft_result = generate_draft(DEMO_PACKAGE)
        review_patch = load_fixture_payload(DEMO_PACKAGE)["metadata"]["review_patch"]
        review_result = apply_review(draft_result, review_patch)

        self.assertEqual(draft_result["status"], "draft_ready")
        self.assertFalse(draft_result["draft_is_formal_export"])
        self.assertTrue(draft_result["manual_review"]["required"])
        self.assertIn(
            "EV-DEMO-REQ-001",
            "\n".join(draft_result["quality_gate"]["needs_confirmation_items"]),
        )
        self.assertTrue(review_result["final_export_allowed"])
        self.assertTrue(review_result["quality_gate"]["allow_user_export"])

    def test_embedded_input_package_json_needs_no_local_paths(self):
        embedded = json.loads((DEMO_PACKAGE / "input_package.json").read_text(encoding="utf-8"))
        embedded["evidence"] = json.loads((DEMO_PACKAGE / "evidence.json").read_text(encoding="utf-8"))
        embedded["review_patch"] = json.loads(
            (DEMO_PACKAGE / "review_patch.json").read_text(encoding="utf-8")
        )

        result = run_stage(embedded, stage="ingest")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.output["metadata"]["ingest_mode"], "input_package")
        self.assertEqual(len(result.evidence), 6)

    def test_demo_reviewed_chain_can_be_exported_to_workbook(self):
        draft_result = generate_draft(DEMO_PACKAGE)
        review_patch = load_fixture_payload(DEMO_PACKAGE)["metadata"]["review_patch"]
        reviewed = apply_review(draft_result, review_patch)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "demo.xlsx"
            export_result = run_stage(
                reviewed["patched_chain"], stage="export", output_path=output_path
            )

            self.assertEqual(export_result.status, "ok")
            self.assertTrue(output_path.exists())
            self.assertGreater(output_path.stat().st_size, 0)

    def test_demo_input_package_cli_end_to_end_flow_exports_final_and_manifests(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            draft_json = tmp_path / "draft_result.json"
            draft_xlsx = tmp_path / "draft.xlsx"
            review_json = tmp_path / "review_result.json"
            final_xlsx = tmp_path / "final.xlsx"
            draft_manifest = tmp_path / "draft_manifest.json"
            draft_export_manifest = tmp_path / "draft_export_manifest.json"
            review_manifest = tmp_path / "review_manifest.json"
            final_manifest = tmp_path / "final_manifest.json"
            review_patch = DEMO_PACKAGE / "review_patch.json"

            commands = [
                [
                    sys.executable,
                    "-m",
                    "minos_core.cli",
                    "generate-draft",
                    "--input",
                    str(DEMO_PACKAGE),
                    "--output",
                    str(draft_json),
                    "--manifest-output",
                    str(draft_manifest),
                ],
                [
                    sys.executable,
                    "-m",
                    "minos_core.cli",
                    "export-draft",
                    "--input",
                    str(draft_json),
                    "--output",
                    str(draft_xlsx),
                    "--manifest-output",
                    str(draft_export_manifest),
                ],
                [
                    sys.executable,
                    "-m",
                    "minos_core.cli",
                    "apply-review",
                    "--draft-result",
                    str(draft_json),
                    "--review-patch",
                    str(review_patch),
                    "--output",
                    str(review_json),
                    "--manifest-output",
                    str(review_manifest),
                ],
                [
                    sys.executable,
                    "-m",
                    "minos_core.cli",
                    "export",
                    "--input",
                    str(review_json),
                    "--output",
                    str(final_xlsx),
                    "--manifest-output",
                    str(final_manifest),
                ],
            ]

            for command in commands:
                result = subprocess.run(
                    command,
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            for path in (
                draft_json,
                draft_xlsx,
                review_json,
                final_xlsx,
                draft_manifest,
                draft_export_manifest,
                review_manifest,
                final_manifest,
            ):
                self.assertTrue(path.exists(), str(path))
                self.assertGreater(path.stat().st_size, 0, str(path))

            draft_result = json.loads(draft_json.read_text(encoding="utf-8"))
            review_result = json.loads(review_json.read_text(encoding="utf-8"))
            final_manifest_payload = json.loads(final_manifest.read_text(encoding="utf-8"))

            self.assertEqual(draft_result["document_type"], "apqp_chain_draft_result")
            self.assertFalse(draft_result["draft_is_formal_export"])
            self.assertTrue(draft_result["manual_review"]["required"])
            self.assertEqual(review_result["document_type"], "apqp_chain_review_result")
            self.assertTrue(review_result["final_export_allowed"])
            self.assertIn("DRAFT_ONLY", _sheet_names(draft_xlsx))
            self.assertNotIn("DRAFT_ONLY", _sheet_names(final_xlsx))
            self.assertIn("not for customer submission", _workbook_text(draft_xlsx))
            self.assertNotIn("not for customer submission", _workbook_text(final_xlsx))
            self.assertEqual(final_manifest_payload["document_type"], "run_manifest")
            self.assertIn("final_export", final_manifest_payload["artifact_hashes"])

    def test_real_project_template_is_json_schema_structure_only(self):
        input_package = json.loads(
            (REAL_PROJECT_TEMPLATE / "input_package.json").read_text(encoding="utf-8")
        )
        evidence = json.loads(
            (REAL_PROJECT_TEMPLATE / "evidence.json").read_text(encoding="utf-8")
        )
        review_patch = json.loads(
            (REAL_PROJECT_TEMPLATE / "review_patch.json").read_text(encoding="utf-8")
        )
        source_index = json.loads(
            (REAL_PROJECT_TEMPLATE / "source_index.json").read_text(encoding="utf-8")
        )

        self.assertTrue(validate_bundle_schema(input_package, "input_package"))
        self.assertEqual(evidence["document_type"], "evidence_bundle")
        self.assertIsInstance(evidence["evidence"], list)
        self.assertTrue(evidence["evidence"])
        self.assertIsInstance(source_index, dict)
        self.assertEqual(
            review_patch["template_status"],
            "requires_human_review_before_apply_review",
        )
        self.assertIn("REPLACE_WITH", json.dumps(input_package, ensure_ascii=False))
        self.assertEqual(input_package["evidence_path"], "evidence.json")
        self.assertEqual(input_package["review_patch_path"], "review_patch.json")
        self.assertEqual(review_patch["confirmed_by"], "")
        self.assertEqual(review_patch["confirmed_at"], "")
        self.assertEqual(review_patch["reason"], "")
        self.assertEqual(review_patch["manual_confirmation_event"], "")
        self.assertEqual(review_patch["evidence_refs"], [])
        for item in review_patch["items"]:
            self.assertEqual(item["confirmed_by"], "")
            self.assertEqual(item["confirmed_at"], "")
            self.assertEqual(item["reason"], "")
            self.assertEqual(item["manual_confirmation_event"], "")
            self.assertEqual(item["evidence_refs"], [])
        evidence_ids = {item["evidence_id"] for item in evidence["evidence"]}
        patch_refs = {
            ref
            for item in review_patch["items"]
            for ref in item.get("evidence_refs", [])
        }
        self.assertTrue(patch_refs.issubset(evidence_ids))

    def test_realistic_input_package_covers_source_document_locations_and_final_gate(self):
        payload = load_fixture_payload(REALISTIC_PACKAGE)
        ingest_result = run_stage(REALISTIC_PACKAGE, stage="ingest")
        draft_result = generate_draft(REALISTIC_PACKAGE)
        review_patch = payload["metadata"]["review_patch"]
        review_result = apply_review(draft_result, review_patch)

        self.assertEqual(payload["metadata"]["input_package_id"], "REALISTIC-INPUT-PACKAGE-001")
        self.assertEqual(ingest_result.status, "ok")
        self.assertEqual(len(payload["evidence"]), 7)
        for item in payload["evidence"]:
            self.assertIn("source_document_id", item)
            self.assertIn("source_location", item)
            self.assertIn("source_ref", item)
            self.assertTrue(item["source_document_id"].startswith("DOC-"))
            self.assertNotIn("customer name", item["content"].lower())

        self.assertEqual(draft_result["status"], "draft_ready")
        self.assertTrue(draft_result["manual_review"]["required"])
        self.assertFalse(draft_result["quality_gate"]["allow_user_export"])
        self.assertIn(
            "EV-REAL-REQ-001",
            "\n".join(draft_result["quality_gate"]["needs_confirmation_items"]),
        )
        self.assertGreaterEqual(len(draft_result["draft"]["process_steps"]), 3)
        self.assertGreaterEqual(len(draft_result["draft"]["failure_modes"]), 3)
        self.assertGreaterEqual(len(draft_result["draft"]["controls"]), 3)

        self.assertTrue(review_result["final_export_allowed"])
        self.assertTrue(review_result["quality_gate"]["allow_user_export"])
        self.assertFalse(review_result["quality_gate"]["needs_confirmation_items"])

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "realistic_final.xlsx"
            export_result = run_stage(
                review_result["patched_chain"], stage="export", output_path=output_path
            )

            self.assertEqual(export_result.status, "ok")
            self.assertTrue(output_path.exists())
            self.assertGreater(output_path.stat().st_size, 0)
