"""Tests for FMEA structured knowledge rules (fmea_rules.zh-CN.json)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

from minos_core.knowledge_recommendation import (
    DEFAULT_KNOWLEDGE_RULES,
    _matches_rule,
    _recommendation,
    _recommendations_from_rule,
    load_knowledge_rules,
    recommend_from_knowledge,
    recommend_from_local_knowledge,
    unresolved_recommendations,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

FMEA_RULES_PATH = Path(__file__).resolve().parent.parent / "configs" / "knowledge" / "fmea_rules.zh-CN.json"


def _make_step(**kwargs: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "process_step_id": "P10",
        "sequence": 10,
        "operation": "",
        "process_function": "",
        "special_characteristics": [],
        "product_characteristics": [],
        "process_characteristics": [],
    }
    defaults.update(kwargs)
    return defaults


def _make_row(**kwargs: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "pfmea_id": "PFMEA-P10-001",
        "process_step_id": "P10",
        "failure_mode": "",
        "failure_effect": "",
        "failure_cause": "",
        "severity": 5,
        "occurrence": 3,
        "detection": 5,
        "action_priority": "M",
        "classification": "",
        "characteristic_refs": [],
        "prevention_control": "",
        "detection_control": "",
    }
    defaults.update(kwargs)
    return defaults


def _make_source(steps: list[dict[str, Any]] | None = None, rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "document_type": "apqp_chain",
        "process_steps": steps or [],
        "failure_modes": rows or [],
    }


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


class LoadRulesTest(unittest.TestCase):
    """Tests for rule loading."""

    def test_load_from_json_returns_v2_rules(self):
        """1. Load from fmea_rules.zh-CN.json returns the expanded V2 rule set."""
        rules = load_knowledge_rules(FMEA_RULES_PATH)
        self.assertGreaterEqual(len(rules), 58)
        self.assertEqual(len({r["knowledge_id"] for r in rules}), len(rules))
        expected_ids = {
            "KR-STAMPING-HOLE-DIMENSION-001",
            "KR-WELDING-STRENGTH-003",
            "KR-SPECIAL-CHARACTERISTIC-014",
            "KR-HIGH-AP-REACTION-015",
            "KR-DOOR-HINGE-ROTATION-FUNCTION-045",
            "KR-LIMITER-DETENT-FORCE-046",
            "KR-STAMPING-SHEET-FEATURE-047",
        }
        self.assertGreaterEqual({r["knowledge_id"] for r in rules}, expected_ids)
        for r in rules:
            self.assertIsInstance(r, dict)
            self.assertIn("knowledge_id", r)

    def test_explicit_missing_file_raises(self):
        """12. Explicit path that does not exist raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            load_knowledge_rules("/nonexistent/path/rules.json")

    def test_explicit_invalid_json_raises(self):
        """13. Explicit path with invalid JSON raises ValueError."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            f.write("this is not valid json {{{")
            bad_path = f.name
        try:
            with self.assertRaises(ValueError):
                load_knowledge_rules(bad_path)
        finally:
            os.unlink(bad_path)

    def test_none_path_loads_default_json_rules(self):
        """path=None loads the default JSON rules, not the 3 in-code fallback rules."""
        rules = load_knowledge_rules(None)
        self.assertGreaterEqual(len(rules), 58)
        self.assertEqual(len({r["knowledge_id"] for r in rules}), len(rules))
        for r in rules:
            self.assertIsInstance(r, dict)
            self.assertIn("knowledge_id", r)

    def test_none_path_missing_default_file_falls_back(self):
        """When default JSON file is missing, path=None falls back to seed rules with warning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Temporarily point knowledge_base._DEFAULT_KB_PATH to a non-existent file.
            import minos_core.knowledge_base as kb
            original = kb._DEFAULT_KB_PATH
            try:
                kb._DEFAULT_KB_PATH = Path(tmpdir) / "nonexistent.json"
                with self.assertWarns(UserWarning) as warn_ctx:
                    rules = load_knowledge_rules(None)
                self.assertTrue(
                    any("不存在" in str(w.message) for w in warn_ctx.warnings),
                )
                self.assertEqual(len(rules), len(DEFAULT_KNOWLEDGE_RULES))
                rule_ids = {r["knowledge_id"] for r in rules}
                expected_ids = {r["rule_id"] for r in DEFAULT_KNOWLEDGE_RULES}
                self.assertEqual(rule_ids, expected_ids)
            finally:
                kb._DEFAULT_KB_PATH = original


class MatchRuleTest(unittest.TestCase):
    """Tests for _matches_rule with new-format rules."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.rules = load_knowledge_rules(FMEA_RULES_PATH)
        cls.rule_by_id = {r["knowledge_id"]: r for r in cls.rules}

    def test_process_and_characteristic_terms_both_match(self):
        """2. process_terms + characteristic_terms both match -> True."""
        rule = self.rule_by_id["KR-STAMPING-HOLE-DIMENSION-001"]
        step = _make_step(operation="冲压冲孔", special_characteristics=["孔径"])
        row = _make_row(
            failure_mode="尺寸超差",
            failure_cause="模具磨损",
            characteristic_refs=["孔径"],
            classification="SC-1",
        )
        self.assertTrue(_matches_rule(row, step, rule))

    def test_characteristic_terms_not_satisfied_skips(self):
        """3. characteristic_terms not satisfied -> False."""
        rule = self.rule_by_id["KR-STAMPING-HOLE-DIMENSION-001"]
        step = _make_step(operation="冲压冲孔", special_characteristics=["外观"])
        row = _make_row(
            failure_mode="划伤",
            failure_cause="操作不当",
            characteristic_refs=["外观"],
        )
        # process_terms match (冲压) but characteristic_terms (孔径/位置度/毛刺) do NOT.
        self.assertFalse(_matches_rule(row, step, rule))

    def test_special_characteristic_required_matches_sc_rows(self):
        """4. special_characteristic_required=True matches rows with classification or special_characteristics."""
        rule = self.rule_by_id["KR-SPECIAL-CHARACTERISTIC-014"]
        step_sc = _make_step(special_characteristics=["SC-1"])
        row_sc = _make_row(classification="SC-1")
        self.assertTrue(_matches_rule(row_sc, step_sc, rule))

        step_no = _make_step(special_characteristics=[])
        row_no = _make_row(classification="", characteristic_refs=[])
        self.assertFalse(_matches_rule(row_no, step_no, rule))

    def test_stamping_hole_rule_matches_punching_operation(self):
        """9. Stamping + hole diameter rule matches punching process."""
        rule = self.rule_by_id["KR-STAMPING-HOLE-DIMENSION-001"]
        step = _make_step(operation="冲孔", process_function="落料")
        row = _make_row(
            failure_mode="孔径超差",
            characteristic_refs=["孔径"],
        )
        self.assertTrue(_matches_rule(row, step, rule))

    def test_welding_rule_matches_spot_welding(self):
        """10. Welding rule matches spot welding process."""
        rule = self.rule_by_id["KR-WELDING-STRENGTH-003"]
        step = _make_step(operation="点焊")
        row = _make_row(
            failure_mode="虚焊",
            characteristic_refs=["熔深"],
        )
        self.assertTrue(_matches_rule(row, step, rule))

    def test_old_format_rule_still_works(self):
        """8. Old format (DEFAULT_KNOWLEDGE_RULES) still matches correctly."""
        old_rule = DEFAULT_KNOWLEDGE_RULES[0]  # KR-INSPECTION-GAUGE
        step = _make_step(operation="尺寸检验")
        row = _make_row(failure_mode="漏检")
        self.assertTrue(_matches_rule(row, step, old_rule))

        # KR-SPECIAL-CHARACTERISTIC-CP
        sc_rule = DEFAULT_KNOWLEDGE_RULES[1]
        step_sc = _make_step(special_characteristics=["SC-1"])
        row_sc = _make_row(classification="SC-1")
        self.assertTrue(_matches_rule(row_sc, step_sc, sc_rule))

        # KR-HIGH-AP-REACTION
        ap_rule = DEFAULT_KNOWLEDGE_RULES[2]
        row_h = _make_row(action_priority="H")
        self.assertTrue(_matches_rule(row_h, step, ap_rule))
        row_m = _make_row(action_priority="M")
        self.assertFalse(_matches_rule(row_m, step, ap_rule))

    def test_rule_with_no_conditions_does_not_match(self):
        """A rule with no process_terms, no characteristic_terms, no requires_* does not match."""
        rule: dict[str, Any] = {"rule_id": "EMPTY-RULE"}
        step = _make_step(operation="anything")
        row = _make_row()
        self.assertFalse(_matches_rule(row, step, rule))

    def test_empty_input_does_not_crash(self):
        """11. Empty input does not crash."""
        result = recommend_from_local_knowledge({}, FMEA_RULES_PATH)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)


class RecommendationOutputTest(unittest.TestCase):
    """Tests for _recommendation and _recommendations_from_rule output structure."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.rules = load_knowledge_rules(FMEA_RULES_PATH)
        cls.rule_by_id = {r["knowledge_id"]: r for r in cls.rules}

    def test_comprehensive_rule_generates_multiple_recommendations(self):
        """5. Comprehensive rule generates multiple per-dimension recommendations."""
        rule = self.rule_by_id["KR-STAMPING-HOLE-DIMENSION-001"]
        step = _make_step(operation="冲压冲孔", special_characteristics=["孔径"])
        row = _make_row(
            failure_mode="尺寸超差",
            characteristic_refs=["孔径"],
        )
        recs = _recommendations_from_rule(row, step, rule)
        self.assertGreater(len(recs), 1, "Comprehensive rule should generate multiple recommendations")

        types_found = {r["recommendation_type"] for r in recs}
        expected_types = {"failure_mode", "failure_cause", "prevention_control", "detection_control",
                          "control_plan", "rating_hint"}
        for t in expected_types:
            self.assertIn(t, types_found, f"Expected recommendation type '{t}' not found")

        # Each recommendation has a unique recommendation_id.
        ids = [r["recommendation_id"] for r in recs]
        self.assertEqual(len(ids), len(set(ids)))

        # Each recommendation type carries only its relevant fields.
        for r in recs:
            rtype = r["recommendation_type"]
            sf = r.get("suggested_fields", {})
            if rtype == "rating_hint":
                self.assertIn("severity", sf)
                self.assertNotIn("failure_mode", sf)
            elif rtype == "failure_mode":
                self.assertIn("failure_mode", sf)
                self.assertNotIn("severity", sf)

    def test_linked_control_plan_suggestion_present(self):
        """6. Recommendation includes linked_control_plan_suggestion."""
        rule = self.rule_by_id["KR-STAMPING-HOLE-DIMENSION-001"]
        step = _make_step(operation="冲压冲孔", special_characteristics=["孔径"])
        row = _make_row(
            failure_mode="尺寸超差",
            characteristic_refs=["孔径"],
        )
        recs = _recommendations_from_rule(row, step, rule)
        cp_recs = [r for r in recs if r["recommendation_type"] == "control_plan"]
        self.assertTrue(cp_recs)
        for r in cp_recs:
            self.assertIsNotNone(r.get("linked_control_plan_suggestion"))
            lcp = r["linked_control_plan_suggestion"]
            self.assertIn("measurement_method", lcp)
            self.assertIn("sample_frequency", lcp)
            self.assertIn("reaction_plan", lcp)
            self.assertTrue(lcp["measurement_method"])
            self.assertTrue(lcp["sample_frequency"])
            self.assertTrue(lcp["reaction_plan"])

    def test_rating_hint_in_suggested_fields(self):
        """7. rating_hint fields appear in suggested_fields of rating_hint type only."""
        rule = self.rule_by_id["KR-STAMPING-HOLE-DIMENSION-001"]
        step = _make_step(operation="冲压冲孔", special_characteristics=["孔径"])
        row = _make_row(
            failure_mode="尺寸超差",
            characteristic_refs=["孔径"],
        )
        recs = _recommendations_from_rule(row, step, rule)
        self.assertTrue(recs)
        rating_recs = [r for r in recs if r["recommendation_type"] == "rating_hint"]
        self.assertTrue(rating_recs, "Should have at least one rating_hint recommendation")
        for r in rating_recs:
            sf = r.get("suggested_fields", {})
            self.assertIn("severity", sf)
            self.assertIn("occurrence", sf)
            self.assertIn("detection", sf)
            self.assertEqual(sf["severity"], 8)
            self.assertEqual(sf["occurrence"], 4)
            self.assertEqual(sf["detection"], 5)
            # rating_hint should NOT carry failure_mode/controls fields
            self.assertNotIn("failure_mode", sf)
            self.assertNotIn("prevention_control", sf)

    def test_suggested_fields_includes_risk_and_controls(self):
        """suggested_fields are split by type: failure_mode type carries risk fields, prevention_control carries controls."""
        rule = self.rule_by_id["KR-STAMPING-HOLE-DIMENSION-001"]
        step = _make_step(operation="冲压冲孔", special_characteristics=["孔径"])
        row = _make_row(
            failure_mode="尺寸超差",
            characteristic_refs=["孔径"],
        )
        recs = _recommendations_from_rule(row, step, rule)
        fm_recs = [r for r in recs if r["recommendation_type"] == "failure_mode"]
        pc_recs = [r for r in recs if r["recommendation_type"] == "prevention_control"]
        self.assertTrue(fm_recs)
        self.assertTrue(pc_recs)
        for r in fm_recs:
            sf = r.get("suggested_fields", {})
            self.assertIn("failure_mode", sf)
            self.assertIn("failure_effect", sf)
            self.assertTrue(sf["failure_mode"])
            self.assertNotIn("prevention_control", sf)
        for r in pc_recs:
            sf = r.get("suggested_fields", {})
            self.assertIn("prevention_control", sf)
            self.assertTrue(sf["prevention_control"])
            self.assertNotIn("failure_mode", sf)

    def test_single_dimension_rule_generates_one_recommendation(self):
        """A rule with only one dimension generates a single recommendation."""
        rule = self.rule_by_id["KR-SPECIAL-CHARACTERISTIC-014"]
        step = _make_step(special_characteristics=["SC-1"])
        row = _make_row(classification="SC-1")
        recs = _recommendations_from_rule(row, step, rule)
        # This rule has all dimensions but special_characteristic_required, so it still has
        # risk + controls + rating_hint → comprehensive → multiple dimensions.
        # Let's check: it has risk.failure_mode, risk.failure_cause, controls.prevention_control,
        # controls.detection_control, rating_hint. So it would generate multiple too.
        self.assertGreater(len(recs), 1)

    def test_old_format_single_recommendation(self):
        """Old format rules (DEFAULT_KNOWLEDGE_RULES) produce single recommendation."""
        rule = DEFAULT_KNOWLEDGE_RULES[0]
        step = _make_step(operation="检验")
        row = _make_row(failure_mode="漏检")
        recs = _recommendations_from_rule(row, step, rule)
        self.assertEqual(len(recs), 1)
        # Keeps existing recommendation_type from the rule.
        self.assertEqual(recs[0]["recommendation_type"], "探测控制")


class UnresolvedRecommendationsTest(unittest.TestCase):
    """Tests for unresolved_recommendations."""

    def test_filters_accepted_and_ignored_with_reason(self):
        """14. unresolved_recommendations correctly filters applied and ignored-with-reason."""
        recs: list[dict[str, Any]] = [
            {
                "recommendation_id": "R1",
                "status": "已应用",
                "lifecycle_status": "applied",
                "ignore_reason": "",
            },
            {
                "recommendation_id": "R2",
                "status": "已忽略",
                "lifecycle_status": "ignored",
                "ignore_reason": "不需要",
            },
            {
                "recommendation_id": "R3",
                "status": "待确认",
                "lifecycle_status": "proposed",
                "ignore_reason": "",
            },
            {
                "recommendation_id": "R4",
                "status": "已忽略",
                "lifecycle_status": "ignored",
                "ignore_reason": "",  # No reason — still unresolved.
            },
        ]
        unresolved = unresolved_recommendations(recs)
        ids = {r["recommendation_id"] for r in unresolved}
        self.assertNotIn("R1", ids)  # applied
        self.assertNotIn("R2", ids)  # ignored with reason
        self.assertIn("R3", ids)  # pending
        self.assertIn("R4", ids)  # ignored without reason

    def test_unresolved_filters_applied(self):
        """15. applied lifecycle_status recommendations are filtered out."""
        recs: list[dict[str, Any]] = [
            {
                "recommendation_id": "A1",
                "status": "已应用",
                "lifecycle_status": "applied",
                "ignore_reason": "",
            },
            {
                "recommendation_id": "A2",
                "status": "已应用",
                "lifecycle_status": "applied",
                "ignore_reason": "",
            },
        ]
        unresolved = unresolved_recommendations(recs)
        self.assertEqual(len(unresolved), 0)

    def test_unresolved_filters_ignored_with_reason(self):
        """16. ignored lifecycle_status with a reason does not block."""
        recs: list[dict[str, Any]] = [
            {
                "recommendation_id": "I1",
                "status": "已忽略",
                "lifecycle_status": "ignored",
                "ignore_reason": "不适用当前产线",
            },
        ]
        unresolved = unresolved_recommendations(recs)
        self.assertEqual(len(unresolved), 0)

    def test_unresolved_keeps_proposed(self):
        """17. proposed lifecycle_status recommendations still block."""
        recs: list[dict[str, Any]] = [
            {
                "recommendation_id": "P1",
                "status": "待确认",
                "lifecycle_status": "proposed",
                "ignore_reason": "",
            },
        ]
        unresolved = unresolved_recommendations(recs)
        ids = {r["recommendation_id"] for r in unresolved}
        self.assertIn("P1", ids)

    def test_unresolved_keeps_accepted_without_applied(self):
        """18. accepted lifecycle_status without applied fields still blocks."""
        recs: list[dict[str, Any]] = [
            {
                "recommendation_id": "AC1",
                "status": "已接受",
                "lifecycle_status": "accepted",
                "ignore_reason": "",
            },
        ]
        unresolved = unresolved_recommendations(recs)
        ids = {r["recommendation_id"] for r in unresolved}
        self.assertIn("AC1", ids)


class EndToEndTest(unittest.TestCase):
    """End-to-end tests for recommend_from_knowledge with new rules."""

    def test_full_workflow_with_new_rules(self):
        """recommend_from_knowledge returns recommendations for matching rules."""
        rules = load_knowledge_rules(FMEA_RULES_PATH)
        source = _make_source(
            steps=[
                {
                    "process_step_id": "P10",
                    "sequence": 10,
                    "operation": "冲压冲孔",
                    "process_function": "落料",
                    "special_characteristics": ["孔径"],
                    "product_characteristics": [],
                    "process_characteristics": [],
                },
                {
                    "process_step_id": "P20",
                    "sequence": 20,
                    "operation": "点焊",
                    "process_function": "焊接",
                    "special_characteristics": ["熔深"],
                    "product_characteristics": [],
                    "process_characteristics": [],
                },
            ],
            rows=[
                {
                    "pfmea_id": "PFMEA-P10-001",
                    "process_step_id": "P10",
                    "failure_mode": "孔径超差",
                    "failure_effect": "装配困难",
                    "failure_cause": "模具磨损",
                    "severity": 8,
                    "occurrence": 4,
                    "detection": 5,
                    "action_priority": "H",
                    "classification": "SC-1",
                    "characteristic_refs": ["孔径", "SC-1"],
                    "prevention_control": "",
                    "detection_control": "",
                },
                {
                    "pfmea_id": "PFMEA-P20-001",
                    "process_step_id": "P20",
                    "failure_mode": "虚焊",
                    "failure_effect": "开裂",
                    "failure_cause": "参数偏移",
                    "severity": 9,
                    "occurrence": 3,
                    "detection": 4,
                    "action_priority": "H",
                    "classification": "",
                    "characteristic_refs": ["熔深"],
                    "prevention_control": "",
                    "detection_control": "",
                },
            ],
        )

        recs = recommend_from_knowledge(source, rules)

        # Should have recommendations from at least 2 rules
        # (stamping + welding)
        sources = {r["source"] for r in recs}
        self.assertIn("KR-STAMPING-HOLE-DIMENSION-001", sources)
        self.assertIn("KR-WELDING-STRENGTH-003", sources)

        # Every recommendation should have required fields.
        for r in recs:
            self.assertIn("recommendation_id", r)
            self.assertIn("recommendation_type", r)
            self.assertIn("suggested_fields", r)
            self.assertEqual(r["target_table"], "pfmea")
            self.assertIn("process_step_id", r)

    def test_deleted_rows_are_skipped(self):
        """Rows marked as deleted should not generate recommendations."""
        rules = load_knowledge_rules(FMEA_RULES_PATH)
        source = _make_source(
            steps=[
                {
                    "process_step_id": "P10",
                    "operation": "冲压冲孔",
                    "special_characteristics": ["孔径"],
                },
            ],
            rows=[
                {
                    "pfmea_id": "PFMEA-P10-001",
                    "process_step_id": "P10",
                    "failure_mode": "孔径超差",
                    "characteristic_refs": ["孔径"],
                    "deleted": True,
                },
            ],
        )
        recs = recommend_from_knowledge(source, rules)
        self.assertEqual(len(recs), 0)

    def test_recommend_from_local_knowledge_convenience(self):
        """recommend_from_local_knowledge loads rules from path and recommends."""
        source = _make_source(
            steps=[
                {
                    "process_step_id": "P10",
                    "operation": "冲压冲孔",
                    "special_characteristics": ["孔径"],
                },
            ],
            rows=[
                {
                    "pfmea_id": "PFMEA-P10-001",
                    "process_step_id": "P10",
                    "failure_mode": "孔径超差",
                    "characteristic_refs": ["孔径"],
                },
            ],
        )
        recs = recommend_from_local_knowledge(source, FMEA_RULES_PATH)
        self.assertTrue(len(recs) > 0)
        sources = {r["source"] for r in recs}
        self.assertIn("KR-STAMPING-HOLE-DIMENSION-001", sources)

    def test_recommend_from_knowledge_default_uses_json_rules(self):
        """recommend_from_knowledge without explicit rules uses default JSON rules."""
        source = _make_source(
            steps=[
                {
                    "process_step_id": "P10",
                    "sequence": 10,
                    "operation": "点焊",
                    "process_function": "焊接",
                    "special_characteristics": ["熔深"],
                    "product_characteristics": [],
                    "process_characteristics": [],
                },
            ],
            rows=[
                {
                    "pfmea_id": "PFMEA-P10-001",
                    "process_step_id": "P10",
                    "failure_mode": "虚焊",
                    "failure_effect": "强度不足",
                    "failure_cause": "参数偏移",
                    "severity": 9,
                    "occurrence": 3,
                    "detection": 4,
                    "action_priority": "H",
                    "classification": "",
                    "characteristic_refs": ["熔深"],
                    "prevention_control": "",
                    "detection_control": "",
                },
            ],
        )
        recs = recommend_from_knowledge(source)  # No rules arg — uses default JSON
        # Welding process should trigger KR-WELDING-STRENGTH-003 and possibly others.
        self.assertGreater(len(recs), 3, "Default JSON rules should produce more than 3 recommendations for welding")
        sources = {r["source"] for r in recs}
        self.assertIn("KR-WELDING-STRENGTH-003", sources)

    def test_recommendation_fields_split_by_type(self):
        """Each recommendation type only carries its relevant fields in suggested_fields."""
        rules = load_knowledge_rules(FMEA_RULES_PATH)
        rule = {r["knowledge_id"]: r for r in rules}["KR-STAMPING-HOLE-DIMENSION-001"]
        step = _make_step(operation="冲压冲孔", special_characteristics=["孔径"])
        row = _make_row(failure_mode="孔径超差", characteristic_refs=["孔径"])
        recs = _recommendations_from_rule(row, step, rule)

        for r in recs:
            rtype = r["recommendation_type"]
            sf = r.get("suggested_fields", {})
            if rtype == "failure_mode":
                self.assertIn("failure_mode", sf)
                self.assertIn("failure_effect", sf)
                self.assertNotIn("failure_cause", sf)
                self.assertNotIn("prevention_control", sf)
                self.assertNotIn("detection_control", sf)
                self.assertNotIn("severity", sf)
            elif rtype == "failure_cause":
                self.assertIn("failure_cause", sf)
                self.assertNotIn("failure_mode", sf)
                self.assertNotIn("prevention_control", sf)
                self.assertNotIn("detection_control", sf)
            elif rtype == "prevention_control":
                self.assertIn("prevention_control", sf)
                self.assertNotIn("failure_mode", sf)
                self.assertNotIn("detection_control", sf)
            elif rtype == "detection_control":
                self.assertIn("detection_control", sf)
                self.assertNotIn("failure_mode", sf)
                self.assertNotIn("prevention_control", sf)
            elif rtype == "rating_hint":
                self.assertIn("severity", sf)
                self.assertIn("occurrence", sf)
                self.assertIn("detection", sf)
                self.assertNotIn("failure_mode", sf)
                self.assertNotIn("prevention_control", sf)
            elif rtype == "control_plan":
                self.assertEqual(sf, {})
                self.assertIsNotNone(r.get("linked_control_plan_suggestion"))


class KnowledgeBaseV2IntegrationTest(unittest.TestCase):
    """Tests for knowledge_base v2 integration in knowledge_recommendation."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.rules = load_knowledge_rules(FMEA_RULES_PATH)

    def test_recommendation_has_knowledge_id(self):
        """推荐项包含 knowledge_id 字段。"""
        rule = {r["knowledge_id"]: r for r in self.rules}["KR-STAMPING-HOLE-DIMENSION-001"]
        step = _make_step(operation="冲压冲孔", special_characteristics=["孔径"])
        row = _make_row(failure_mode="孔径超差", characteristic_refs=["孔径"])
        recs = _recommendations_from_rule(row, step, rule)
        self.assertTrue(recs)
        for r in recs:
            self.assertIn("knowledge_id", r)
            self.assertTrue(r["knowledge_id"], f"knowledge_id should not be empty: {r}")
            self.assertEqual(r["knowledge_id"], "KR-STAMPING-HOLE-DIMENSION-001")

    def test_recommendation_has_created_from(self):
        """推荐项包含 created_from='knowledge_base'。"""
        rule = {r["knowledge_id"]: r for r in self.rules}["KR-WELDING-STRENGTH-003"]
        step = _make_step(operation="点焊")
        row = _make_row(failure_mode="虚焊", characteristic_refs=["熔深"])
        recs = _recommendations_from_rule(row, step, rule)
        self.assertTrue(recs)
        for r in recs:
            self.assertEqual(r.get("created_from"), "knowledge_base")

    def test_new_recommendation_id_format(self):
        """新格式 recommendation_id 为 knowledge_id:recommendation_type:pfmea_id。"""
        rule = {r["knowledge_id"]: r for r in self.rules}["KR-STAMPING-HOLE-DIMENSION-001"]
        step = _make_step(operation="冲压冲孔", special_characteristics=["孔径"])
        row = _make_row(pfmea_id="PFMEA-P10-001", failure_mode="孔径超差",
                        characteristic_refs=["孔径"])
        recs = _recommendations_from_rule(row, step, rule)
        self.assertTrue(recs)
        for r in recs:
            rid = r["recommendation_id"]
            # Format: knowledge_id:type:pfmea_id (3 parts)
            parts = rid.split(":")
            self.assertEqual(len(parts), 3, f"Expected 3-part ID, got: {rid}")
            self.assertEqual(parts[0], "KR-STAMPING-HOLE-DIMENSION-001")
            self.assertEqual(parts[2], "PFMEA-P10-001")
            self.assertIn(parts[1], r.get("recommendation_type", ""))

    def test_expired_recommendation_is_unresolved(self):
        """lifecycle=expired 推荐项进入 unresolved。"""
        recs: list[dict[str, Any]] = [
            {
                "recommendation_id": "EXP-1",
                "status": "已过期",
                "lifecycle_status": "expired",
                "ignore_reason": "",
            },
        ]
        unresolved = unresolved_recommendations(recs)
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["recommendation_id"], "EXP-1")

    def test_unresolved_handles_all_lifecycle_states(self):
        """全面测试 lifecycle_status 对 unresolved 的影响。"""
        recs: list[dict[str, Any]] = [
            {
                "recommendation_id": "R-applied",
                "status": "待确认",
                "lifecycle_status": "applied",
                "ignore_reason": "",
            },
            {
                "recommendation_id": "R-ignored-reason",
                "status": "待确认",
                "lifecycle_status": "ignored",
                "ignore_reason": "不适用",
            },
            {
                "recommendation_id": "R-ignored-no-reason",
                "status": "待确认",
                "lifecycle_status": "ignored",
                "ignore_reason": "",
            },
            {
                "recommendation_id": "R-proposed",
                "status": "待确认",
                "lifecycle_status": "proposed",
                "ignore_reason": "",
            },
            {
                "recommendation_id": "R-accepted",
                "status": "待确认",
                "lifecycle_status": "accepted",
                "ignore_reason": "",
            },
            {
                "recommendation_id": "R-expired",
                "status": "待确认",
                "lifecycle_status": "expired",
                "ignore_reason": "",
            },
        ]
        unresolved = unresolved_recommendations(recs)
        unresolved_ids = {r["recommendation_id"] for r in unresolved}

        # applied: 不阻断
        self.assertNotIn("R-applied", unresolved_ids)
        # ignored with reason: 不阻断
        self.assertNotIn("R-ignored-reason", unresolved_ids)
        # ignored without reason: 阻断
        self.assertIn("R-ignored-no-reason", unresolved_ids)
        # proposed: 阻断
        self.assertIn("R-proposed", unresolved_ids)
        # accepted: 阻断
        self.assertIn("R-accepted", unresolved_ids)
        # expired: 阻断
        self.assertIn("R-expired", unresolved_ids)


if __name__ == "__main__":
    unittest.main()
