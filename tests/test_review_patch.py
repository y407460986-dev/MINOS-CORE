import copy
import unittest

from minos_core.adapters.fixture_json import load_fixture_payload
from minos_core.quality_gates import evaluate_stage_gate
from minos_core.review_patch import (
    REVIEW_PATCH_VERSION,
    ReviewPatchError,
    apply_review_patch,
    build_review_patch_template,
)


ROOT_FIXTURE = "D:/MINOS-CORE/tests/fixtures/apqp_chain"


def _fixture():
    return load_fixture_payload(ROOT_FIXTURE)


class ReviewPatchTests(unittest.TestCase):
    def test_review_patch_confirms_evidence_and_rows_for_formal_export(self):
        payload = _fixture()
        payload["evidence"][0]["needs_confirmation"] = True
        payload["process_flow"]["steps"][0]["needs_confirmation"] = True
        payload["pfmea"]["rows"][0]["needs_confirmation"] = True
        payload["control_plan"]["rows"][0]["needs_confirmation"] = True

        before = evaluate_stage_gate(payload, stage="export")
        self.assertFalse(before.allow_user_export)
        self.assertIn("process_step:P10", before.needs_confirmation_items)
        self.assertIn("failure_mode:PFMEA-P10-001", before.needs_confirmation_items)
        self.assertIn("control_item:CP-P10-001", before.needs_confirmation_items)
        self.assertTrue(any("EV-PFD-ROUTE-001" in item for item in before.needs_confirmation_items))

        updated = apply_review_patch(
            payload,
            {
                "review_patch_version": REVIEW_PATCH_VERSION,
                "confirmed_by": "qa.engineer",
                "confirmed_at": "2026-04-25T10:00:00Z",
                "reason": "人工复核已确认这些 draft 项可以正式放行",
                "evidence_refs": ["EV-PFD-ROUTE-001"],
                "items": [
                    {"action": "confirm", "target": "evidence:EV-PFD-ROUTE-001"},
                    {"action": "confirm", "target": "process_step:P10"},
                    {"action": "confirm", "target": "failure_mode:PFMEA-P10-001"},
                    {"action": "confirm", "target": "control_item:CP-P10-001"},
                ],
            },
        )

        self.assertTrue(payload["evidence"][0]["needs_confirmation"])
        self.assertFalse(updated["evidence"][0]["needs_confirmation"])
        self.assertFalse(updated["process_flow"]["steps"][0]["needs_confirmation"])
        self.assertFalse(updated["pfmea"]["rows"][0]["needs_confirmation"])
        self.assertFalse(updated["control_plan"]["rows"][0]["needs_confirmation"])
        self.assertEqual(
            len(updated["metadata"]["review_confirmations"]),
            4,
        )
        self.assertEqual(
            updated["metadata"]["review_confirmations"][0]["confirmed_by"],
            "qa.engineer",
        )

        after = evaluate_stage_gate(updated, stage="export")
        self.assertTrue(after.can_continue)
        self.assertTrue(after.allow_user_export)
        self.assertEqual(after.needs_confirmation_items, [])

    def test_review_patch_corrects_pending_field_and_records_basis(self):
        payload = _fixture()
        payload["control_plan"]["rows"][0]["specification"] = ""
        payload["pending_fields"] = [
            {"source_ref": "CP-P10-001", "field": "specification"},
            "control_item:CP-P10-001.specification",
        ]

        before = evaluate_stage_gate(payload, stage="export")
        self.assertFalse(before.allow_user_export)
        self.assertIn("CP-P10-001.specification", before.pending_fields)

        updated = apply_review_patch(
            payload,
            {
                "review_patch_version": REVIEW_PATCH_VERSION,
                "items": [
                    {
                        "action": "correct",
                        "target": "pending_field:CP-P10-001.specification",
                        "value": "2.00 +/- 0.10 mm",
                        "confirmed_by": "quality.lead",
                        "confirmed_at": "2026-04-25T11:00:00Z",
                        "reason": "按已存在工程要求证据补齐规格",
                        "evidence_refs": ["EV-ENG-REQ-001"],
                    }
                ],
            },
        )

        self.assertEqual(
            updated["control_plan"]["rows"][0]["specification"],
            "2.00 +/- 0.10 mm",
        )
        self.assertEqual(updated["pending_fields"], [])
        record = updated["metadata"]["review_confirmations"][0]
        self.assertEqual(record["target"], "pending_field:CP-P10-001.specification")
        self.assertEqual(record["field_path"], "CP-P10-001.specification")
        self.assertEqual(record["evidence_refs"], ["EV-ENG-REQ-001"])

        after = evaluate_stage_gate(updated, stage="export")
        self.assertTrue(after.allow_user_export)
        self.assertNotIn("CP-P10-001.specification", after.pending_fields)

    def test_review_patch_rejects_missing_evidence_reference(self):
        payload = _fixture()

        with self.assertRaises(ReviewPatchError):
            apply_review_patch(
                payload,
                {
                    "review_patch_version": REVIEW_PATCH_VERSION,
                    "confirmed_by": "qa.engineer",
                    "confirmed_at": "2026-04-25T12:00:00Z",
                    "reason": "invalid evidence should fail fast",
                    "items": [
                        {
                            "action": "confirm",
                            "target": "process_step:P10",
                            "evidence_refs": ["EV-DOES-NOT-EXIST"],
                        }
                    ],
                },
            )

    def test_review_patch_allows_explicit_manual_confirmation_event(self):
        payload = _fixture()
        payload["pfmea"]["rows"][0]["needs_confirmation"] = True

        updated = apply_review_patch(
            payload,
            {
                "review_patch_version": REVIEW_PATCH_VERSION,
                "items": [
                    {
                        "action": "confirm",
                        "target": "failure_mode:PFMEA-P10-001",
                        "confirmed_by": "manufacturing.engineer",
                        "confirmed_at": "2026-04-25T13:00:00Z",
                        "reason": "现场评审会议确认该 PFMEA 行",
                        "manual_confirmation_event": "MRB-2026-04-25-001",
                    }
                ],
            },
        )

        self.assertFalse(updated["pfmea"]["rows"][0]["needs_confirmation"])
        record = updated["metadata"]["review_confirmations"][0]
        self.assertEqual(record["manual_confirmation_event"], "MRB-2026-04-25-001")

    def test_review_template_lists_review_items_without_auto_confirmation(self):
        payload = _fixture()
        payload["control_plan"]["rows"][0]["specification"] = ""
        payload["pending_fields"] = ["control_item:CP-P10-001.specification"]
        payload["evidence"][0]["needs_confirmation"] = True
        payload["evidence"].append(
            {
                "evidence_id": "EV-AI-001",
                "source": "llm",
                "content": "AI inferred risk for manual review only.",
                "confidence": 0.5,
                "ai_inferred": True,
                "needs_confirmation": True,
            }
        )
        draft_result = {
            "document_type": "apqp_chain_draft_result",
            "status": "draft_ready",
            "draft": payload,
        }

        template = build_review_patch_template(draft_result)

        self.assertEqual(template["review_patch_version"], REVIEW_PATCH_VERSION)
        self.assertEqual(
            template["template_status"],
            "requires_human_review_before_apply_review",
        )
        self.assertEqual(template["confirmed_by"], "")
        self.assertEqual(template["confirmed_at"], "")
        self.assertEqual(template["reason"], "")
        targets = {item["target"] for item in template["items"]}
        categories = {item["review_category"] for item in template["items"]}
        self.assertIn("pending_field:CP-P10-001.specification", targets)
        self.assertIn("evidence:EV-PFD-ROUTE-001", targets)
        self.assertIn("evidence:EV-AI-001", targets)
        self.assertIn("pending_field", categories)
        self.assertIn("needs_confirmation", categories)
        self.assertIn("ai_inferred_manual_review", categories)
        for item in template["items"]:
            self.assertEqual(item["confirmed_by"], "")
            self.assertEqual(item["confirmed_at"], "")
            self.assertEqual(item["reason"], "")
            self.assertEqual(item["evidence_refs"], [])

    def test_review_template_cannot_be_applied_without_human_completion(self):
        payload = _fixture()
        payload["evidence"][0]["needs_confirmation"] = True
        draft_result = {
            "document_type": "apqp_chain_draft_result",
            "status": "draft_ready",
            "draft": payload,
        }
        template = build_review_patch_template(draft_result)

        with self.assertRaisesRegex(ReviewPatchError, "templates must be completed"):
            apply_review_patch(payload, template)

    def test_review_template_cli_writes_template_file(self):
        import json
        import subprocess
        import sys
        import tempfile
        from pathlib import Path

        payload = _fixture()
        payload["evidence"][0]["needs_confirmation"] = True
        draft_result = {
            "document_type": "apqp_chain_draft_result",
            "status": "draft_ready",
            "draft": payload,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            draft_path = tmp_path / "draft_result.json"
            output_path = tmp_path / "review_patch_template.json"
            draft_path.write_text(
                json.dumps(draft_result, ensure_ascii=False), encoding="utf-8"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "minos_core.cli",
                    "review-template",
                    "--draft-result",
                    str(draft_path),
                    "--output",
                    str(output_path),
                ],
                cwd="D:/MINOS-CORE",
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            template = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(template["review_patch_version"], REVIEW_PATCH_VERSION)
            self.assertIn(
                "requires_human_review_before_apply_review",
                output_path.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
