"""Tests for Phase 2.4 confidence propagation in brainstorm and PFMEA AI."""

from __future__ import annotations

import unittest

from minos_core.brainstorm import brainstorm_failure_modes_from_pfd
from minos_core.pfd_to_pfmea_ai import infer_pfmea_from_process_flow


def _make_step(**overrides):
    step = {
        "process_step_id": "P10",
        "sequence": 10,
        "operation": "rivet assembly",
        "process_function": "assemble riveted joint",
        "special_characteristics": [],
        "evidence_refs": [],
    }
    step.update(overrides)
    return step


def _make_process_flow(steps, evidence=None):
    return {
        "document_type": "process_flow",
        "steps": steps,
        "evidence": evidence or [],
        "links": [{"from": "P10", "to": "P20", "link_type": "sequence"}],
    }


class ConfidencePropagationBrainstormTests(unittest.TestCase):
    """Tests for confidence propagation in brainstorm._candidate()."""

    def test_high_confidence_step_produces_no_confirmation(self):
        """High confidence (0.9) step should produce candidates with needs_confirmation=False."""
        step = _make_step(confidence=0.9)
        result = brainstorm_failure_modes_from_pfd(_make_process_flow([step]))

        self.assertEqual(result["document_type"], "failure_mode_candidates")
        candidates = result["candidates"]
        self.assertGreater(len(candidates), 0)
        for candidate in candidates:
            self.assertFalse(
                candidate["needs_confirmation"],
                f"Candidate {candidate['candidate_id']} should not need confirmation "
                f"with high confidence step. Got confidence={candidate.get('confidence')}",
            )
            self.assertAlmostEqual(candidate["confidence"], 0.9, places=1)

    def test_low_confidence_step_produces_confirmation(self):
        """Low confidence (0.3) step should produce candidates with needs_confirmation=True."""
        step = _make_step(confidence=0.3)
        result = brainstorm_failure_modes_from_pfd(_make_process_flow([step]))

        self.assertEqual(result["document_type"], "failure_mode_candidates")
        candidates = result["candidates"]
        self.assertGreater(len(candidates), 0)
        for candidate in candidates:
            self.assertTrue(
                candidate["needs_confirmation"],
                f"Candidate {candidate['candidate_id']} should need confirmation "
                f"with low confidence step. Got confidence={candidate.get('confidence')}",
            )
            self.assertAlmostEqual(candidate["confidence"], 0.3, places=1)

    def test_step_with_high_confidence_evidence_reflects_it(self):
        """Evidence with high confidence should raise candidate confidence."""
        step = _make_step(
            confidence=0.4,
            evidence_refs=["EV-HIGH"],
        )
        evidence = [
            {
                "evidence_id": "EV-HIGH",
                "source": "test",
                "content": "rivet assembly joint verification",
                "confidence": 0.95,
            },
        ]
        result = brainstorm_failure_modes_from_pfd(
            _make_process_flow([step], evidence=evidence)
        )

        candidates = result["candidates"]
        self.assertGreater(len(candidates), 0)
        for candidate in candidates:
            # Evidence confidence 0.95 should push avg above 0.9
            self.assertGreater(
                candidate["confidence"],
                0.5,
                f"Candidate {candidate['candidate_id']} confidence should reflect "
                f"evidence confidence. Got confidence={candidate['confidence']}",
            )
            self.assertFalse(
                candidate["needs_confirmation"],
                f"Candidate backed by high-confidence evidence should not need confirmation",
            )

    def test_no_confidence_data_defaults_to_confirmation(self):
        """When no step or evidence confidence is provided, needs_confirmation=True."""
        step = _make_step()
        # No confidence on step, no evidence
        result = brainstorm_failure_modes_from_pfd(_make_process_flow([step]))

        candidates = result["candidates"]
        self.assertGreater(len(candidates), 0)
        for candidate in candidates:
            # Default when no evidence confidence and no step confidence is 0.5
            self.assertAlmostEqual(candidate["confidence"], 0.5, places=1)
            self.assertTrue(
                candidate["needs_confirmation"],
                "Candidate with no confidence data should need confirmation "
                "(default 0.5 < 0.85 threshold)",
            )

    def test_mixed_confidence_evidence_averages_correctly(self):
        """Multiple evidence items: confidence should be average of the matched ones."""
        step = _make_step(
            evidence_refs=["EV-HIGH", "EV-LOW"],
        )
        evidence = [
            {
                "evidence_id": "EV-HIGH",
                "source": "test",
                "content": "rivet assembly",
                "confidence": 0.9,
            },
            {
                "evidence_id": "EV-LOW",
                "source": "test",
                "content": "rivet assembly check",
                "confidence": 0.3,
            },
        ]
        result = brainstorm_failure_modes_from_pfd(
            _make_process_flow([step], evidence=evidence)
        )

        candidates = result["candidates"]
        self.assertGreater(len(candidates), 0)
        for candidate in candidates:
            # Average of 0.9 and 0.3 = 0.6, which is < 0.85 -> needs confirmation
            self.assertAlmostEqual(candidate["confidence"], 0.6, places=1)
            self.assertTrue(
                candidate["needs_confirmation"],
                f"Avg confidence 0.6 < 0.85 should need confirmation",
            )

    def test_confidence_present_in_candidate_dict(self):
        """Every candidate must have a 'confidence' key."""
        step = _make_step(confidence=0.8)
        result = brainstorm_failure_modes_from_pfd(_make_process_flow([step]))

        for candidate in result["candidates"]:
            self.assertIn("confidence", candidate)
            self.assertIsInstance(candidate["confidence"], float)


class ConfidencePropagationPfmeaAiTests(unittest.TestCase):
    """Tests for confidence propagation in pfd_to_pfmea_ai.py."""

    def test_high_confidence_step_generates_lower_occurrence(self):
        """High confidence (>=0.9) should map to occurrence=3."""
        step = {
            "process_step_id": "P10",
            "sequence": 10,
            "operation": "rivet assembly",
            "process_function": "assemble riveted joint",
            "confidence": 0.92,
            "evidence_refs": [],
            "special_characteristics": [],
        }
        pfmea = infer_pfmea_from_process_flow(
            {"steps": [step], "product": {}, "evidence": [], "pending_fields": []}
        )
        rows = pfmea["rows"]
        self.assertGreater(len(rows), 0)
        for row in rows:
            self.assertLessEqual(
                row["occurrence"],
                4,
                f"High confidence should produce occurrence <= 4, got {row['occurrence']} "
                f"for {row['pfmea_id']}",
            )

    def test_low_confidence_step_generates_higher_occurrence(self):
        """Low confidence (<0.5) should map to occurrence=6."""
        step = {
            "process_step_id": "P10",
            "sequence": 10,
            "operation": "rivet assembly",
            "process_function": "assemble riveted joint",
            "confidence": 0.3,
            "evidence_refs": [],
            "special_characteristics": [],
        }
        pfmea = infer_pfmea_from_process_flow(
            {"steps": [step], "product": {}, "evidence": [], "pending_fields": []}
        )
        rows = pfmea["rows"]
        self.assertGreater(len(rows), 0)
        for row in rows:
            self.assertGreaterEqual(
                row["occurrence"],
                5,
                f"Low confidence should produce occurrence >= 5, got {row['occurrence']} "
                f"for {row['pfmea_id']}",
            )

    def test_mid_confidence_step_generates_moderate_occurrence(self):
        """Mid confidence (0.5-0.7) should map to occurrence=5."""
        step = {
            "process_step_id": "P10",
            "sequence": 10,
            "operation": "rivet assembly",
            "process_function": "assemble riveted joint",
            "confidence": 0.65,
            "evidence_refs": [],
            "special_characteristics": [],
        }
        pfmea = infer_pfmea_from_process_flow(
            {"steps": [step], "product": {}, "evidence": [], "pending_fields": []}
        )
        rows = pfmea["rows"]
        self.assertGreater(len(rows), 0)
        for row in rows:
            # Mid confidence (0.5 <= x < 0.7) -> occurrence=5
            self.assertEqual(
                row["occurrence"],
                5,
                f"Mid confidence 0.65 should produce occurrence=5, got {row['occurrence']}",
            )

    def test_ai_reasoning_is_readable_chinese_text(self):
        """ai_reasoning must be non-empty Chinese-readable text (v1.9.1+)."""
        step = {
            "process_step_id": "P10",
            "sequence": 10,
            "operation": "rivet assembly",
            "process_function": "assemble riveted joint",
            "confidence": 0.8,
            "evidence_refs": ["EV-001"],
            "special_characteristics": ["SC-HEIGHT"],
        }
        pfmea = infer_pfmea_from_process_flow(
            {"steps": [step], "product": {}, "evidence": [], "pending_fields": []}
        )
        rows = pfmea["rows"]
        self.assertGreater(len(rows), 0)
        for row in rows:
            reasoning_str = row.get("ai_reasoning", "")
            self.assertTrue(reasoning_str, f"ai_reasoning should not be empty")
            # Should contain step context (step ID and operation in Chinese-readable prose)
            self.assertIn("P10", reasoning_str)
            self.assertIn("assemble riveted joint", reasoning_str)

    def test_no_confidence_step_produces_needs_confirmation(self):
        """Step with no confidence should produce needs_confirmation rows."""
        step = {
            "process_step_id": "P10",
            "sequence": 10,
            "operation": "rivet assembly",
            "process_function": "assemble riveted joint",
            "evidence_refs": [],
            "special_characteristics": [],
        }
        pfmea = infer_pfmea_from_process_flow(
            {"steps": [step], "product": {}, "evidence": [], "pending_fields": []}
        )
        rows = pfmea["rows"]
        self.assertGreater(len(rows), 0)
        for row in rows:
            self.assertTrue(
                row["needs_confirmation"],
                f"No-confidence step should need confirmation for {row['pfmea_id']}",
            )


if __name__ == "__main__":
    unittest.main()
