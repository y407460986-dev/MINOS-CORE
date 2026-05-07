import unittest

from minos_core.part_family_classifier import classify_part_family


class PartFamilyClassifierTests(unittest.TestCase):
    def test_classifies_stamping_family(self):
        result = classify_part_family(
            _analysis_bundle(
                "STAMPED REINFORCEMENT BRACKET",
                [
                    {"name": "SPCC sheet metal", "evidence_refs": ["EV-STAMP"]},
                    {
                        "clue": "Progressive die stamping route with blanking, piercing and forming on press line",
                        "evidence_refs": ["EV-STAMP"],
                    },
                ],
                "EV-STAMP",
            )
        )

        self.assertEqual(result["family_key"], "stamping")
        self.assertEqual(result["family_name"], "冲压件")
        self.assertGreaterEqual(result["confidence"], 0.78)
        self.assertFalse(result["needs_confirmation"])
        self.assertTrue(result["matched_evidence"])
        self.assertTrue(result["process_route_templates"])

    def test_classifies_limiter_family(self):
        result = classify_part_family(
            _analysis_bundle(
                "DOOR OPENING LIMITER ASSEMBLY",
                [
                    {"text": "Travel limiter with limit stop and holding force requirement", "evidence_refs": ["EV-LIM"]},
                    {
                        "clue": "Door check arm uses roller, spring, rivet and press fit components",
                        "evidence_refs": ["EV-LIM"],
                    },
                ],
                "EV-LIM",
            )
        )

        self.assertEqual(result["family_key"], "limiter")
        self.assertEqual(result["family_name"], "限位器")
        self.assertGreaterEqual(result["confidence"], 0.78)
        self.assertFalse(result["needs_confirmation"])
        self.assertTrue(result["matched_evidence"])

    def test_classifies_door_hinge_family(self):
        result = classify_part_family(
            _analysis_bundle(
                "FRONT DOOR HINGE ASSEMBLY",
                [
                    {"text": "Door hinge includes hinge pin, bushing and rotation torque requirement", "evidence_refs": ["EV-HINGE"]},
                    {
                        "clue": "Hinge bracket is riveted and checked for opening angle",
                        "evidence_refs": ["EV-HINGE"],
                    },
                ],
                "EV-HINGE",
            )
        )

        self.assertEqual(result["family_key"], "door_hinge")
        self.assertEqual(result["family_name"], "门铰链")
        self.assertGreaterEqual(result["confidence"], 0.78)
        self.assertFalse(result["needs_confirmation"])
        self.assertTrue(result["matched_evidence"])

    def test_classifies_door_hinge_from_ocr_title_block_variants(self):
        result = classify_part_family(
            _analysis_bundle(
                "DH ASSY",
                [
                    {
                        "text": "JLV03000500BACKX D00R HIMGE 尾门较链",
                        "evidence_refs": ["EV-HINGE-TITLE"],
                    },
                    {
                        "text": "3.较链总成不可有衬套露出校链，制造件不可有毛刺",
                        "evidence_refs": ["EV-HINGE-REQ"],
                    },
                ],
                "EV-HINGE-TITLE",
            )
        )

        self.assertEqual(result["family_key"], "door_hinge")
        self.assertEqual(result["family_name"], "门铰链")
        self.assertGreaterEqual(result["confidence"], 0.78)
        self.assertFalse(result["needs_confirmation"])
        matched_terms = {
            item["matched_term"] for item in result["matched_evidence"]
        }
        self.assertIn("尾门较链", matched_terms)
        self.assertIn("dh assy", matched_terms)

    def test_title_block_tailgate_hinge_beats_bushing_component_text(self):
        result = classify_part_family(
            {
                "drawing_identity": {
                    "part_name": "尾门铰链",
                    "drawing_number": "JLV03000500",
                    "revision": "A",
                    "evidence_refs": ["EV-TITLE"],
                },
                "technical_requirements": [
                    {
                        "text": "衬套不可露出，铰链销铆接后转动力矩符合要求",
                        "evidence_refs": ["EV-REQ"],
                    }
                ],
                "manufacturing_clues": [
                    {
                        "operation": "衬套预装并压入精整",
                        "evidence_refs": ["EV-REQ"],
                    }
                ],
                "evidence": [
                    {"evidence_id": "EV-TITLE", "source": "ocr_block", "content": "JLV03000500 尾门铰链"},
                    {"evidence_id": "EV-REQ", "source": "ocr_block", "content": "衬套不可露出"},
                ],
            }
        )

        self.assertEqual(result["family_key"], "door_hinge")
        self.assertFalse(result["needs_confirmation"])
        self.assertGreaterEqual(result["confidence"], 0.78)
        self.assertEqual(result["matched_evidence"][0]["matched_term"], "尾门铰链")
        self.assertIn("drawing_identity.part_name", result["matched_evidence"][0]["field_path"])

    def test_bushing_component_alone_does_not_classify_as_door_hinge(self):
        result = classify_part_family(
            {
                "drawing_identity": {
                    "part_name": "衬套",
                    "drawing_number": "BZJ01004500",
                    "revision": "A",
                    "evidence_refs": ["EV-BUSHING"],
                },
                "technical_requirements": [
                    {
                        "text": "bushing press fit, no burr, appearance inspection",
                        "evidence_refs": ["EV-BUSHING"],
                    }
                ],
                "manufacturing_clues": [],
                "evidence": [
                    {"evidence_id": "EV-BUSHING", "source": "ocr_block", "content": "衬套 bushing"},
                ],
            }
        )

        self.assertEqual(result["family_key"], "unknown")
        self.assertTrue(result["needs_confirmation"])

    def test_confirmation_band_keeps_family_but_requires_confirmation(self):
        result = classify_part_family(
            {
                "drawing_identity": {"part_name": "Demo Custom Part", "evidence_refs": ["EV-CUSTOM"]},
                "technical_requirements": [{"text": "alpha beta", "evidence_refs": ["EV-CUSTOM"]}],
            },
            family_index={
                "custom": {
                    "family_key": "custom",
                    "family_name": "自定义族",
                    "indicators": [
                        {"terms": ["alpha"], "weight": 0.30},
                        {"terms": ["beta"], "weight": 0.28},
                    ],
                }
            },
        )

        self.assertEqual(result["family_key"], "custom")
        self.assertGreaterEqual(result["confidence"], 0.55)
        self.assertLess(result["confidence"], 0.78)
        self.assertTrue(result["needs_confirmation"])

    def test_low_confidence_becomes_unknown(self):
        result = classify_part_family(
            {"drawing_identity": {"part_name": "Unclear part"}},
            family_index={
                "custom": {
                    "family_key": "custom",
                    "family_name": "自定义族",
                    "indicators": [{"terms": ["alpha"], "weight": 0.30}],
                }
            },
        )

        self.assertEqual(result["family_key"], "unknown")
        self.assertTrue(result["needs_confirmation"])
        self.assertEqual(result["process_route_templates"], [])


def _analysis_bundle(part_name, items, evidence_id):
    return {
        "drawing_identity": {
            "part_name": part_name,
            "drawing_number": f"{evidence_id}-DWG",
            "revision": "A",
            "evidence_refs": [evidence_id],
        },
        "materials": items[:1],
        "technical_requirements": items[1:2],
        "manufacturing_clues": items[1:],
        "evidence": [{"evidence_id": evidence_id, "source": "drawing_page"}],
    }


if __name__ == "__main__":
    unittest.main()
