import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from minos_core.pipeline import apply_review, export_draft_fixture, generate_draft
from minos_core.review_patch import REVIEW_PATCH_VERSION
from minos_core.run_manifest import (
    RUN_MANIFEST_SCHEMA_VERSION,
    build_run_manifest,
    sha256_bytes,
    sha256_file,
    sha256_json,
)

ROOT_FIXTURE = "D:/MINOS-CORE/tests/fixtures/apqp_chain"


class RunManifestTests(unittest.TestCase):
    def test_build_run_manifest_has_required_audit_fields_and_hashes_artifacts(self):
        payload = {"b": 2, "a": 1}
        manifest = build_run_manifest(
            run_id="run-test-001",
            created_at="2026-04-25T10:00:00Z",
            inputs={"fixture": "fixture.json"},
            outputs={"draft": "draft-result.json"},
            stage_results=[{"stage": "validate", "status": "ok"}],
            quality_gates=[{"stage": "validate", "can_continue": True}],
            review_confirmations=[{"target": "process_step:P10"}],
            artifacts={"payload": payload, "raw": b"abc"},
            warnings=["draft only"],
        )

        self.assertEqual(manifest["document_type"], "run_manifest")
        self.assertEqual(manifest["schema_version"], RUN_MANIFEST_SCHEMA_VERSION)
        self.assertEqual(manifest["run_id"], "run-test-001")
        self.assertEqual(manifest["created_at"], "2026-04-25T10:00:00Z")
        self.assertEqual(manifest["inputs"], {"fixture": "fixture.json"})
        self.assertEqual(manifest["outputs"], {"draft": "draft-result.json"})
        self.assertEqual(manifest["stage_results"][0]["stage"], "validate")
        self.assertEqual(manifest["stages"], manifest["stage_results"])
        self.assertEqual(manifest["quality_gates"][0]["stage"], "validate")
        self.assertEqual(manifest["review_confirmations"][0]["target"], "process_step:P10")
        self.assertEqual(manifest["warnings"], ["draft only"])
        self.assertEqual(manifest["artifact_hashes"]["payload"], sha256_json(payload))
        self.assertEqual(manifest["artifact_hashes"]["raw"], sha256_bytes(b"abc"))

    def test_sha256_helpers_hash_canonical_json_and_file_bytes(self):
        expected_json_hash = hashlib.sha256(b'{"a":1,"b":2}').hexdigest()
        self.assertEqual(sha256_json({"b": 2, "a": 1}), expected_json_hash)
        self.assertEqual(sha256_bytes(b"abc"), hashlib.sha256(b"abc").hexdigest())

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "artifact.bin"
            path.write_bytes(b"file-bytes")

            self.assertEqual(
                sha256_file(path), hashlib.sha256(b"file-bytes").hexdigest()
            )

    def test_generate_draft_writes_optional_run_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"
            result = generate_draft(EVIDENCE_INPUT, manifest_output=manifest_path)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "draft_ready")
        self.assertEqual(manifest["document_type"], "run_manifest")
        self.assertEqual(manifest["outputs"], result)
        self.assertTrue(manifest["stage_results"])
        self.assertEqual(manifest["stages"], manifest["stage_results"])
        self.assertEqual(manifest["quality_gates"][0]["stage"], "validate")
        self.assertEqual(manifest["review_confirmations"], [])
        self.assertIn("draft_result", manifest["artifact_hashes"])
        self.assertTrue(manifest["warnings"])

    def test_apply_review_writes_optional_run_manifest_with_confirmations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"
            result = apply_review(
                ROOT_FIXTURE,
                _review_patch("process_step:P10"),
                manifest_output=manifest_path,
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["document_type"], "run_manifest")
        self.assertEqual(manifest["outputs"], result)
        self.assertEqual(manifest["quality_gates"][0], result["quality_gate"])
        self.assertEqual(manifest["stages"], [])
        self.assertEqual(manifest["review_confirmations"], result["review_confirmations"])
        self.assertIn("review_result", manifest["artifact_hashes"])
        self.assertIn("patched_chain", manifest["artifact_hashes"])

    def test_export_draft_writes_optional_run_manifest_with_file_hash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workbook_path = Path(tmpdir) / "draft.xlsx"
            manifest_path = Path(tmpdir) / "manifest.json"
            exported = export_draft_fixture(
                ROOT_FIXTURE,
                workbook_path,
                manifest_output=manifest_path,
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(exported, workbook_path)
            self.assertTrue(workbook_path.exists())
            self.assertEqual(manifest["document_type"], "run_manifest")
            self.assertEqual(manifest["outputs"], {"export_path": str(workbook_path)})
            self.assertEqual(manifest["stages"], [])
            self.assertIn("draft_export", manifest["artifact_hashes"])
            self.assertEqual(manifest["artifact_hashes"]["draft_export"], sha256_file(workbook_path))


def _review_patch(*targets: str) -> dict:
    return {
        "review_patch_version": REVIEW_PATCH_VERSION,
        "confirmed_by": "qa.engineer",
        "confirmed_at": "2026-04-25T10:00:00Z",
        "reason": "人工复核确认 draft 项可用于当前放行判断",
        "evidence_refs": ["EV-PFD-ROUTE-001"],
        "items": [{"action": "confirm", "target": target} for target in targets],
    }


EVIDENCE_INPUT = {
    "document_type": "evidence_bundle",
    "schema_version": "0.1",
    "evidence": [
        {
            "evidence_id": "EV-GEN-ROUTE-001",
            "source": "routing fixture",
            "content": (
                "Released process routing defines P10 incoming material verification, "
                "P20 rivet assembly, P30 final inspection and pack, including sequence "
                "P10 -> P20 -> P30."
            ),
            "confidence": 1.0,
        },
        {
            "evidence_id": "EV-GEN-REQ-001",
            "source": "drawing fixture",
            "content": (
                "Drawing DRW-777 Rev B and engineering requirements define material "
                "thickness 2.00 +/- 0.10 mm, rivet height 1.50 +0.50/-0.00 mm, "
                "and push-out force >= 10 kN."
            ),
            "confidence": 1.0,
            "needs_confirmation": True,
        },
        {
            "evidence_id": "EV-GEN-AI-001",
            "source": "llm",
            "content": "AI inferred possible rivet setup risk for engineer review only.",
            "confidence": 0.55,
            "ai_inferred": True,
            "needs_confirmation": True,
        },
    ],
}


if __name__ == "__main__":
    unittest.main()
