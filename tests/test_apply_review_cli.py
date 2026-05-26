from __future__ import annotations

import copy
import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from minos_core.cli import main
from minos_core.pipeline import apply_review
from minos_core.review_patch import REVIEW_PATCH_VERSION


ROOT_FIXTURE = str(Path(__file__).parent / "fixtures" / "apqp_chain")


def _review_patch(*targets: str, evidence_refs: list[str] | None = None) -> dict:
    return {
        "review_patch_version": REVIEW_PATCH_VERSION,
        "confirmed_by": "qa.engineer",
        "confirmed_at": "2026-04-25T10:00:00Z",
        "reason": "人工复核确认 draft 项可用于当前放行判断",
        "evidence_refs": evidence_refs or ["EV-PFD-ROUTE-001"],
        "items": [{"action": "confirm", "target": target} for target in targets],
    }


class ApplyReviewApiTests(unittest.TestCase):
    def test_apply_review_returns_review_envelope_and_allows_export_when_gate_clears(self):
        result = apply_review(
            ROOT_FIXTURE,
            _review_patch(
                "evidence:EV-PFD-ROUTE-001",
                "process_step:P10",
                "failure_mode:PFMEA-P10-001",
                "control_item:CP-P10-001",
            ),
        )

        self.assertEqual(result["document_type"], "apqp_chain_review_result")
        self.assertTrue(result["final_export_allowed"])
        self.assertTrue(result["quality_gate"]["allow_user_export"])
        self.assertEqual(len(result["review_confirmations"]), 4)
        self.assertFalse(
            result["patched_chain"]["metadata"]["review_confirmations"][0]["target"] == ""
        )

    def test_apply_review_accepts_draft_result_envelope(self):
        draft_result = {
            "document_type": "apqp_chain_draft_result",
            "draft": _fixture_with_pending_review(),
        }

        result = apply_review(
            draft_result,
            _review_patch("process_step:P10"),
        )

        self.assertEqual(result["document_type"], "apqp_chain_review_result")
        self.assertFalse(result["patched_chain"]["process_flow"]["steps"][0]["needs_confirmation"])

    def test_apply_review_returns_zero_semantics_when_patch_applies_but_gate_blocks(self):
        result = apply_review(
            _fixture_with_pending_review(),
            _review_patch("process_step:P10"),
        )

        self.assertFalse(result["final_export_allowed"])
        self.assertFalse(result["quality_gate"]["allow_user_export"])
        self.assertIn("failure_mode:PFMEA-P10-001", result["quality_gate"]["needs_confirmation_items"])


class ApplyReviewCliTests(unittest.TestCase):
    def test_apply_review_cli_writes_envelope_and_returns_zero_when_still_not_allowed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            chain_path = tmp_path / "chain.json"
            patch_path = tmp_path / "review_patch.json"
            output_path = tmp_path / "review_result.json"
            chain_path.write_text(
                json.dumps(_fixture_with_pending_review(), ensure_ascii=False),
                encoding="utf-8",
            )
            patch_path.write_text(
                json.dumps(_review_patch("process_step:P10"), ensure_ascii=False),
                encoding="utf-8",
            )

            with patch("sys.stdout", new_callable=StringIO):
                exit_code = main(
                    [
                        "apply-review",
                        "--input",
                        str(chain_path),
                        "--review-patch",
                        str(patch_path),
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            envelope = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(envelope["document_type"], "apqp_chain_review_result")
            self.assertFalse(envelope["final_export_allowed"])

    def test_apply_review_cli_returns_non_zero_for_bad_patch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            patch_path = tmp_path / "bad_review_patch.json"
            patch_path.write_text(
                json.dumps(
                    _review_patch(
                        "process_step:P10", evidence_refs=["EV-DOES-NOT-EXIST"]
                    ),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch("sys.stdout", new_callable=StringIO) as stdout:
                exit_code = main(
                    [
                        "apply-review",
                        "--input",
                        ROOT_FIXTURE,
                        "--review-patch",
                        str(patch_path),
                    ]
                )

            self.assertEqual(exit_code, 2)
            self.assertIn("references missing evidence", stdout.getvalue())


def _fixture_with_pending_review() -> dict:
    from minos_core.adapters.fixture_json import load_fixture_payload

    payload = copy.deepcopy(load_fixture_payload(ROOT_FIXTURE))
    payload["evidence"][0]["needs_confirmation"] = True
    payload["process_flow"]["steps"][0]["needs_confirmation"] = True
    payload["pfmea"]["rows"][0]["needs_confirmation"] = True
    payload["control_plan"]["rows"][0]["needs_confirmation"] = True
    return payload


if __name__ == "__main__":
    unittest.main()
