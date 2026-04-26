from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from minos_core.ppap_comparison import compare_to_approved_ppap
from minos_core.run_manifest import sha256_file, sha256_json
from minos_core.schemas import validate_bundle_schema


ROOT = Path(__file__).resolve().parents[1]
REALISTIC_PACKAGE = ROOT / "tests" / "fixtures" / "realistic_input_package"
APPROVED_BASELINE = (
    ROOT
    / "tests"
    / "fixtures"
    / "approved_baseline"
    / "apqp_chain_approved_baseline.json"
)
NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _run_cli(*args: str, expected_returncode: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, "-m", "minos_core.cli", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    message = "\n".join(
        [
            "command: " + " ".join([sys.executable, "-m", "minos_core.cli", *args]),
            "stdout:",
            result.stdout,
            "stderr:",
            result.stderr,
        ]
    )
    assert result.returncode == expected_returncode, message
    return result


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


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class Phase6PilotWorkflowTests(unittest.TestCase):
    def test_realistic_input_package_cli_pilot_workflow_regression(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            draft_json = tmp_path / "draft_result.json"
            draft_xlsx = tmp_path / "draft.xlsx"
            unreviewed_final_xlsx = tmp_path / "unreviewed_final.xlsx"
            review_json = tmp_path / "review_result.json"
            final_xlsx = tmp_path / "final.xlsx"
            comparison_json = tmp_path / "comparison_report.json"
            draft_manifest = tmp_path / "draft_manifest.json"
            draft_export_manifest = tmp_path / "draft_export_manifest.json"
            review_manifest = tmp_path / "review_manifest.json"
            final_manifest = tmp_path / "final_manifest.json"
            review_patch = REALISTIC_PACKAGE / "review_patch.json"

            _run_cli(
                "generate-draft",
                "--input",
                str(REALISTIC_PACKAGE),
                "--output",
                str(draft_json),
                "--manifest-output",
                str(draft_manifest),
            )
            _run_cli(
                "export-draft",
                "--input",
                str(draft_json),
                "--output",
                str(draft_xlsx),
                "--manifest-output",
                str(draft_export_manifest),
            )
            _run_cli(
                "export",
                "--input",
                str(draft_json),
                "--output",
                str(unreviewed_final_xlsx),
                expected_returncode=2,
            )
            self.assertFalse(unreviewed_final_xlsx.exists())

            draft_text = _workbook_text(draft_xlsx)
            self.assertIn("DRAFT_ONLY", _sheet_names(draft_xlsx))
            self.assertIn("not for customer submission", draft_text)

            _run_cli(
                "apply-review",
                "--draft-result",
                str(draft_json),
                "--review-patch",
                str(review_patch),
                "--output",
                str(review_json),
                "--manifest-output",
                str(review_manifest),
            )
            _run_cli(
                "export",
                "--input",
                str(review_json),
                "--output",
                str(final_xlsx),
                "--manifest-output",
                str(final_manifest),
            )

            final_text = _workbook_text(final_xlsx)
            self.assertNotIn("DRAFT_ONLY", _sheet_names(final_xlsx))
            self.assertNotIn("DRAFT_ONLY", final_text)
            self.assertNotIn("not for customer submission", final_text)

            for manifest_path in (
                draft_manifest,
                draft_export_manifest,
                review_manifest,
                final_manifest,
            ):
                self.assertTrue(manifest_path.exists(), str(manifest_path))
                manifest_payload = _read_json(manifest_path)
                self.assertTrue(validate_bundle_schema(manifest_payload, "run_manifest"))
                self.assertEqual(manifest_payload["document_type"], "run_manifest")
                self.assertIn("artifact_hashes", manifest_payload)

            final_manifest_payload = _read_json(final_manifest)
            self.assertEqual(
                final_manifest_payload["artifact_hashes"]["final_export"],
                sha256_file(final_xlsx),
            )
            self.assertEqual(
                final_manifest_payload["artifact_hashes"]["final_export"],
                hashlib.sha256(final_xlsx.read_bytes()).hexdigest(),
            )

            review_payload = _read_json(review_json)
            comparison_report = compare_to_approved_ppap(
                review_payload["patched_chain"], APPROVED_BASELINE
            ).model_dump()
            comparison_json.write_text(
                json.dumps(comparison_report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            self.assertTrue(comparison_json.exists())
            comparison_payload = _read_json(comparison_json)
            self.assertIn("matched", comparison_payload["counts"])
            self.assertIn("missing_process_step", comparison_payload["counts"])
            self.assertIn("extra_generated_item", comparison_payload["counts"])
            self.assertIn("differences", comparison_payload)
            self.assertGreater(len(comparison_payload["differences"]), 0)

            comparison_hash = sha256_json(comparison_payload)
            self.assertEqual(comparison_hash, sha256_json(_read_json(comparison_json)))


if __name__ == "__main__":
    unittest.main()
