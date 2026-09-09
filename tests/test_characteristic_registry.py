"""Tests for characteristic_registry module."""

from __future__ import annotations

import copy
import unittest

from minos_core.characteristic_registry import (
    attach_characteristics_to_three_tables,
    build_characteristic_registry,
)


class BuildCharacteristicRegistryTests(unittest.TestCase):
    """Unit tests for build_characteristic_registry."""

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _drawing_analysis(**overrides: object) -> dict:
        """Return a minimal but realistic drawing_analysis payload."""
        payload: dict = {
            "document_type": "drawing_analysis_bundle",
            "schema_version": "minos-core.drawing_analysis.v1",
            "dimensions": [
                {
                    "name": "孔径",
                    "specification": "10.0 +/- 0.1 mm",
                    "evidence_refs": ["drawing_page_001"],
                    "confidence": 0.86,
                    "ai_inferred": True,
                    "needs_confirmation": True,
                },
                {
                    "name": "槽宽",
                    "specification": "5.0 +/- 0.05 mm",
                    "evidence_refs": ["drawing_page_001"],
                    "confidence": 0.92,
                    "ai_inferred": True,
                    "needs_confirmation": False,
                },
            ],
            "special_characteristics": [
                {
                    "name": "孔径",
                    "symbol": "SC-001",
                    "specification": "10.0 +/- 0.1 mm",
                    "evidence_refs": ["drawing_page_001"],
                    "confidence": 0.90,
                    "ai_inferred": True,
                    "needs_confirmation": False,
                    "confirmation_status": "rule_confirmed",
                },
                {
                    "name": "硬度",
                    "specification": "HRC 58-62",
                    "evidence_refs": ["drawing_page_001"],
                    "confidence": 0.78,
                    "ai_inferred": True,
                    "needs_confirmation": False,
                    "confirmation_status": "human_confirmed",
                },
            ],
            "technical_requirements": [
                {
                    "description": "表面无毛刺",
                    "evidence_refs": ["drawing_page_001"],
                    "confidence": 0.81,
                    "ai_inferred": True,
                    "needs_confirmation": False,
                },
            ],
            "inspection_requirements": [
                {
                    "item": "全尺寸检查",
                    "evidence_refs": ["drawing_page_001"],
                    "confidence": 0.75,
                    "ai_inferred": True,
                    "needs_confirmation": False,
                },
            ],
            "evidence": [
                {"evidence_id": "drawing_page_001", "source": "page_1.png"},
            ],
        }
        payload.update(overrides)  # type: ignore[arg-type]
        return payload

    # ------------------------------------------------------------------
    # test 1: normal registry build
    # ------------------------------------------------------------------

    def test_build_registry_from_drawing_analysis(self):
        da = self._drawing_analysis()
        registry = build_characteristic_registry(da)

        self.assertEqual(registry["document_type"], "characteristic_registry")
        self.assertEqual(
            registry["schema_version"],
            "minos-core.characteristic_registry.v1",
        )
        self.assertIsInstance(registry["items"], list)
        # 2 dims + 2 sc + 1 tech + 1 inspection = 6 items
        self.assertEqual(len(registry["items"]), 6)

        # Verify classifications
        classifications = {item["classification"] for item in registry["items"]}
        self.assertIn("dimension", classifications)
        self.assertIn("special_characteristic", classifications)
        self.assertIn("technical_requirement", classifications)
        self.assertIn("inspection_requirement", classifications)

        # Verify source_blocks
        source_blocks = {item["source_block"] for item in registry["items"]}
        self.assertIn("dimensions", source_blocks)
        self.assertIn("special_characteristics", source_blocks)
        self.assertIn("technical_requirements", source_blocks)
        self.assertIn("inspection_requirements", source_blocks)

    # ------------------------------------------------------------------
    # test 2: special characteristics use SC-prefixed IDs
    # ------------------------------------------------------------------

    def test_special_characteristics_use_sc_prefix(self):
        da = self._drawing_analysis()
        registry = build_characteristic_registry(da)

        sc_items = [
            item
            for item in registry["items"]
            if item["classification"] == "special_characteristic"
        ]
        self.assertTrue(sc_items)

        for item in sc_items:
            cid = item["characteristic_id"]
            self.assertTrue(
                cid.startswith("SC-"),
                f"Expected SC- prefix, got {cid}",
            )

    def test_registry_skips_unconfirmed_special_characteristics(self):
        drawing_analysis = {
            "special_characteristics": [
                {
                    "id": "SC-001",
                    "name": "孔径 10.0 mm",
                    "classification": "SC",
                    "evidence_refs": ["drawing_page_001"],
                    "needs_confirmation": True,
                }
            ],
            "dimensions": [],
            "technical_requirements": [],
            "inspection_requirements": [],
        }

        registry = build_characteristic_registry(drawing_analysis)

        self.assertEqual(registry["items"], [])

    def test_registry_accepts_rule_confirmed_special_characteristic(self):
        drawing_analysis = {
            "special_characteristics": [
                {
                    "id": "SC-001",
                    "name": "孔径 10.0 mm",
                    "classification": "SC",
                    "evidence_refs": ["drawing_page_001"],
                    "needs_confirmation": False,
                    "confirmation_status": "rule_confirmed",
                }
            ],
            "dimensions": [],
            "technical_requirements": [],
            "inspection_requirements": [],
        }

        registry = build_characteristic_registry(drawing_analysis)

        self.assertEqual(registry["items"][0]["characteristic_id"], "SC-001")
        self.assertEqual(registry["items"][0]["classification"], "special_characteristic")

    def test_registry_accepts_judge_confirmed_special_characteristic(self):
        drawing_analysis = {
            "special_characteristics": [
                {
                    "symbol": "CC-001",
                    "name": "安装孔位置度",
                    "classification": "CC",
                    "evidence_refs": ["drawing_page_001"],
                    "needs_confirmation": False,
                    "confirmation_status": "judge_confirmed",
                }
            ],
            "dimensions": [],
            "technical_requirements": [],
            "inspection_requirements": [],
        }

        registry = build_characteristic_registry(drawing_analysis)

        self.assertEqual(registry["items"][0]["characteristic_id"], "CC-001")
        self.assertEqual(registry["items"][0]["classification"], "special_characteristic")

    def test_registry_skips_unconfirmed_special_characteristic_even_when_not_marked_pending(self):
        drawing_analysis = {
            "special_characteristics": [
                {
                    "symbol": "SC-002",
                    "name": "孔径 10.0 mm",
                    "classification": "SC",
                    "evidence_refs": ["drawing_page_001"],
                    "needs_confirmation": False,
                    "confirmation_status": "needs_human_review",
                }
            ],
            "dimensions": [],
            "technical_requirements": [],
            "inspection_requirements": [],
        }

        registry = build_characteristic_registry(drawing_analysis)

        self.assertEqual(registry["items"], [])

    def test_registry_still_skips_judge_confirmed_when_needs_confirmation_true(self):
        drawing_analysis = {
            "special_characteristics": [
                {
                    "symbol": "CC-002",
                    "name": "安装孔位置度",
                    "classification": "CC",
                    "evidence_refs": ["drawing_page_001"],
                    "needs_confirmation": True,
                    "confirmation_status": "judge_confirmed",
                }
            ],
            "dimensions": [],
            "technical_requirements": [],
            "inspection_requirements": [],
        }

        registry = build_characteristic_registry(drawing_analysis)

        self.assertEqual(registry["items"], [])

    def test_registry_skips_ptc_special_characteristic(self):
        drawing_analysis = {
            "special_characteristics": [
                {
                    "id": "PTC-001",
                    "name": "图例定义项",
                    "symbol": "PTC-001",
                    "classification": "PTC",
                    "evidence_refs": ["drawing_page_001"],
                    "needs_confirmation": False,
                    "confirmation_status": "rule_confirmed",
                }
            ],
            "dimensions": [],
            "technical_requirements": [],
            "inspection_requirements": [],
        }

        registry = build_characteristic_registry(drawing_analysis)

        self.assertEqual(registry["items"], [])

    # ------------------------------------------------------------------
    # test 3: non-special characteristics use CHR-prefixed IDs
    # ------------------------------------------------------------------

    def test_non_special_characteristics_use_chr_prefix(self):
        da = self._drawing_analysis()
        registry = build_characteristic_registry(da)

        non_sc = [
            item
            for item in registry["items"]
            if item["classification"] != "special_characteristic"
        ]
        self.assertTrue(non_sc)

        for item in non_sc:
            cid = item["characteristic_id"]
            self.assertTrue(
                cid.startswith("CHR-"),
                f"Expected CHR- prefix, got {cid}",
            )

    # ------------------------------------------------------------------
    # test 4: dedup — same name + spec + evidence_ref
    # ------------------------------------------------------------------

    def test_dedup_same_name_spec_evidence_ref(self):
        da = self._drawing_analysis()
        # Add a duplicate dimension that shares evidence_ref
        da["dimensions"].append(
            {
                "name": "孔径",
                "specification": "10.0 +/- 0.1 mm",
                "evidence_refs": ["drawing_page_001"],
                "confidence": 0.50,
                "ai_inferred": True,
                "needs_confirmation": False,
            }
        )
        registry = build_characteristic_registry(da)

        hole_items = [
            item
            for item in registry["items"]
            if item["name"] == "孔径" and item["classification"] == "dimension"
        ]
        self.assertEqual(
            len(hole_items), 1,
            "Duplicate dimension '孔径' should have been deduplicated",
        )
        # Confidence should take the higher of the two (0.86 vs 0.50)
        self.assertEqual(hole_items[0]["confidence"], 0.86)

    # ------------------------------------------------------------------
    # test 5: no dedup when name or spec differs
    # ------------------------------------------------------------------

    def test_no_dedup_different_name_or_spec(self):
        da = self._drawing_analysis()
        # Different name, same spec, same evidence_ref → NOT a duplicate
        da["dimensions"].append(
            {
                "name": "孔深",
                "specification": "10.0 +/- 0.1 mm",
                "evidence_refs": ["drawing_page_001"],
                "confidence": 0.80,
                "ai_inferred": True,
                "needs_confirmation": False,
            }
        )
        registry = build_characteristic_registry(da)
        dim_items = [
            item
            for item in registry["items"]
            if item["classification"] == "dimension"
        ]
        # 2 original + 1 new = 3 (孔径 and 槽宽 have different names)
        self.assertEqual(len(dim_items), 3)

    # ------------------------------------------------------------------
    # test 6: empty drawing_analysis → empty registry
    # ------------------------------------------------------------------

    def test_empty_drawing_analysis_returns_empty_registry(self):
        registry = build_characteristic_registry({})
        self.assertEqual(registry["document_type"], "characteristic_registry")
        self.assertEqual(registry["items"], [])

    # ------------------------------------------------------------------
    # test 12: registry items preserve evidence_refs, confidence,
    #          ai_inferred, needs_confirmation
    # ------------------------------------------------------------------

    def test_registry_items_preserve_metadata_fields(self):
        da = self._drawing_analysis()
        registry = build_characteristic_registry(da)

        for item in registry["items"]:
            self.assertIn("evidence_refs", item)
            self.assertIsInstance(item["evidence_refs"], list)
            self.assertIn("confidence", item)
            self.assertIsInstance(item["confidence"], float)
            self.assertIn("ai_inferred", item)
            self.assertIsInstance(item["ai_inferred"], bool)
            self.assertIn("needs_confirmation", item)
            self.assertIsInstance(item["needs_confirmation"], bool)

        # Spot-check one known item
        aperture_items = [
            item
            for item in registry["items"]
            if item["name"] == "孔径" and item["classification"] == "dimension"
        ]
        self.assertTrue(aperture_items)
        aperture = aperture_items[0]
        self.assertEqual(aperture_items[0]["evidence_refs"], ["drawing_page_001"])
        self.assertAlmostEqual(aperture["confidence"], 0.86)
        self.assertTrue(aperture["ai_inferred"])
        self.assertTrue(aperture["needs_confirmation"])


class AttachCharacteristicsToThreeTablesTests(unittest.TestCase):
    """Unit tests for attach_characteristics_to_three_tables."""

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _source() -> dict:
        """Return a minimal three-table source dict."""
        return {
            "process_flow": {
                "steps": [
                    {
                        "process_step_id": "P10",
                        "sequence": 10,
                        "operation": "数控钻孔",
                        "process_function": "加工孔径至图纸要求",
                        "characteristic_refs": [],
                        "special_characteristics": [],
                    },
                    {
                        "process_step_id": "P20",
                        "sequence": 20,
                        "operation": "热处理",
                        "process_function": "淬火达到硬度要求",
                        "characteristic_refs": [],
                        "special_characteristics": [],
                    },
                ]
            },
            "pfmea": {
                "rows": [
                    {
                        "pfmea_id": "PFMEA-P10-001",
                        "process_step_id": "P10",
                        "failure_mode": "孔径超差",
                        "function_requirement": "孔径 10.0 +/- 0.1 mm",
                        "characteristic_refs": [],
                    },
                    {
                        "pfmea_id": "PFMEA-P20-001",
                        "process_step_id": "P20",
                        "failure_mode": "硬度不足",
                        "function_requirement": "硬度 HRC 58-62",
                        "characteristic_refs": [],
                    },
                ]
            },
            "control_plan": {
                "rows": [
                    {
                        "control_plan_id": "CP-P10-001",
                        "process_step_id": "P10",
                        "pfmea_id": "PFMEA-P10-001",
                        "product_process_characteristic": "孔径",
                        "specification": "10.0 +/- 0.1 mm",
                        "characteristic_refs": [],
                        "source_special_characteristics": [],
                    },
                    {
                        "control_plan_id": "CP-P20-001",
                        "process_step_id": "P20",
                        "pfmea_id": "PFMEA-P20-001",
                        "product_process_characteristic": "硬度",
                        "specification": "HRC 58-62",
                        "characteristic_refs": [],
                        "source_special_characteristics": [],
                    },
                ]
            },
        }

    @staticmethod
    def _registry() -> dict:
        """Return a registry whose names match the source content."""
        return {
            "document_type": "characteristic_registry",
            "schema_version": "minos-core.characteristic_registry.v1",
            "items": [
                {
                    "characteristic_id": "CHR-001",
                    "name": "孔径",
                    "classification": "dimension",
                    "specification": "10.0 +/- 0.1 mm",
                    "source_block": "dimensions",
                    "source_ref": "drawing_page_001",
                    "evidence_refs": ["drawing_page_001"],
                    "confidence": 0.86,
                    "ai_inferred": True,
                    "needs_confirmation": True,
                },
                {
                    "characteristic_id": "SC-001",
                    "name": "孔径",
                    "classification": "special_characteristic",
                    "specification": "10.0 +/- 0.1 mm",
                    "source_block": "special_characteristics",
                    "source_ref": "drawing_page_001",
                    "evidence_refs": ["drawing_page_001"],
                    "confidence": 0.90,
                    "ai_inferred": True,
                    "needs_confirmation": True,
                },
                {
                    "characteristic_id": "CHR-002",
                    "name": "硬度",
                    "classification": "dimension",
                    "specification": "HRC 58-62",
                    "source_block": "dimensions",
                    "source_ref": "drawing_page_001",
                    "evidence_refs": ["drawing_page_001"],
                    "confidence": 0.78,
                    "ai_inferred": True,
                    "needs_confirmation": False,
                },
                {
                    "characteristic_id": "SC-002",
                    "name": "硬度",
                    "classification": "special_characteristic",
                    "specification": "HRC 58-62",
                    "source_block": "special_characteristics",
                    "source_ref": "drawing_page_001",
                    "evidence_refs": ["drawing_page_001"],
                    "confidence": 0.88,
                    "ai_inferred": True,
                    "needs_confirmation": False,
                },
            ],
        }

    # ------------------------------------------------------------------
    # test 7: PFD step characteristic_refs
    # ------------------------------------------------------------------

    def test_pfd_step_characteristic_refs_populated(self):
        source = self._source()
        registry = self._registry()
        result = attach_characteristics_to_three_tables(source, registry)

        p10 = result["process_flow"]["steps"][0]
        # "孔径" appears in operation "数控钻孔" (no) and process_function "加工孔径至图纸要求" (yes)
        # So CHR-001 (dimension "孔径") and SC-001 (special "孔径") should be attached
        self.assertIn("CHR-001", p10["characteristic_refs"])
        self.assertIn("SC-001", p10["characteristic_refs"])

        p20 = result["process_flow"]["steps"][1]
        # "硬度" appears in operation "热处理" (no) and process_function "淬火达到硬度要求" (yes)
        self.assertIn("CHR-002", p20["characteristic_refs"])
        self.assertIn("SC-002", p20["characteristic_refs"])

    # ------------------------------------------------------------------
    # test 8: special characteristics also go into special_characteristics list
    # ------------------------------------------------------------------

    def test_special_characteristics_enter_special_characteristics_list(self):
        source = self._source()
        registry = self._registry()
        result = attach_characteristics_to_three_tables(source, registry)

        p10 = result["process_flow"]["steps"][0]
        self.assertIn("SC-001", p10["special_characteristics"])
        # CHR-001 is a dimension, NOT a special characteristic
        self.assertNotIn("CHR-001", p10["special_characteristics"])

    # ------------------------------------------------------------------
    # test 9: PFMEA row characteristic_refs
    # ------------------------------------------------------------------

    def test_pfmea_row_characteristic_refs_populated(self):
        source = self._source()
        registry = self._registry()
        result = attach_characteristics_to_three_tables(source, registry)

        pfmea_p10 = result["pfmea"]["rows"][0]
        # failure_mode "孔径超差" contains "孔径"
        self.assertIn("CHR-001", pfmea_p10["characteristic_refs"])
        self.assertIn("SC-001", pfmea_p10["characteristic_refs"])

        pfmea_p20 = result["pfmea"]["rows"][1]
        # failure_mode "硬度不足" contains "硬度"
        self.assertIn("CHR-002", pfmea_p20["characteristic_refs"])
        self.assertIn("SC-002", pfmea_p20["characteristic_refs"])

    # ------------------------------------------------------------------
    # test 10: CP row characteristic_refs and source_special_characteristics
    # ------------------------------------------------------------------

    def test_cp_row_characteristic_refs_and_source_special_characteristics(self):
        source = self._source()
        registry = self._registry()
        result = attach_characteristics_to_three_tables(source, registry)

        cp_p10 = result["control_plan"]["rows"][0]
        # product_process_characteristic "孔径" matches "孔径"
        self.assertIn("CHR-001", cp_p10["characteristic_refs"])
        self.assertIn("SC-001", cp_p10["characteristic_refs"])
        # SC-001 is special → should appear in source_special_characteristics
        self.assertIn("SC-001", cp_p10["source_special_characteristics"])
        # CHR-001 is NOT special
        self.assertNotIn("CHR-001", cp_p10["source_special_characteristics"])

        cp_p20 = result["control_plan"]["rows"][1]
        self.assertIn("CHR-002", cp_p20["characteristic_refs"])
        self.assertIn("SC-002", cp_p20["characteristic_refs"])
        self.assertIn("SC-002", cp_p20["source_special_characteristics"])
        self.assertNotIn("CHR-002", cp_p20["source_special_characteristics"])

    # ------------------------------------------------------------------
    # test 11: attach does not mutate original source
    # ------------------------------------------------------------------

    def test_attach_does_not_mutate_original_source(self):
        source = self._source()
        original = copy.deepcopy(source)
        registry = self._registry()

        _result = attach_characteristics_to_three_tables(source, registry)

        # Original source must be unmodified
        self.assertEqual(source, original)

    # ------------------------------------------------------------------
    # edge case: source without a particular table does not crash
    # ------------------------------------------------------------------

    def test_attach_handles_missing_tables(self):
        source: dict = {}
        registry = self._registry()
        result = attach_characteristics_to_three_tables(source, registry)
        self.assertEqual(result, {})

    def test_attach_noop_when_registry_empty(self):
        source = self._source()
        registry: dict = {"items": []}
        result = attach_characteristics_to_three_tables(source, registry)
        # Should be a deep copy, structures intact
        self.assertEqual(
            result["process_flow"]["steps"][0]["process_step_id"], "P10"
        )

    def test_attach_via_apqp_chain_keys(self):
        """attach works when source uses chain keys (process_steps /
        failure_modes / controls) instead of table-wrapped keys."""
        source = {
            "process_steps": [
                {
                    "process_step_id": "P10",
                    "operation": "钻孔",
                    "process_function": "加工孔径",
                    "characteristic_refs": [],
                    "special_characteristics": [],
                }
            ],
            "failure_modes": [
                {
                    "pfmea_id": "PFMEA-P10",
                    "failure_mode": "孔径超差",
                    "characteristic_refs": [],
                }
            ],
            "controls": [
                {
                    "control_plan_id": "CP-P10",
                    "product_process_characteristic": "孔径",
                    "characteristic_refs": [],
                    "source_special_characteristics": [],
                }
            ],
        }
        registry = self._registry()
        result = attach_characteristics_to_three_tables(source, registry)
        self.assertIn("CHR-001", result["process_steps"][0]["characteristic_refs"])
        self.assertIn("CHR-001", result["failure_modes"][0]["characteristic_refs"])
        self.assertIn("CHR-001", result["controls"][0]["characteristic_refs"])


if __name__ == "__main__":
    unittest.main()
