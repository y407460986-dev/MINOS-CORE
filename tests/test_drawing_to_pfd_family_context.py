import unittest

from minos_core.drawing_to_pfd import infer_process_flow_from_drawing
from minos_core.part_family_classifier import classify_part_family
from minos_core.part_family_knowledge import load_part_family_knowledge


class DrawingToPfdFamilyContextTests(unittest.TestCase):
    def test_family_context_builds_door_hinge_pfd_skeleton(self):
        bundle = _door_hinge_bundle()
        family_context = classify_part_family(bundle)

        pfd = infer_process_flow_from_drawing(bundle, family_context=family_context)

        operations = [step["operation"] for step in pfd["steps"]]
        self.assertEqual(family_context["family_key"], "door_hinge")
        self.assertEqual(operations[:2], ["来料检验", "材料准备"])
        for expected in ("落料", "冲孔", "成形", "装配", "铆接", "润滑", "功能检验"):
            self.assertIn(expected, operations)
        self.assertEqual(operations[-2:], ["最终检验", "包装"])
        self.assertEqual(pfd["metadata"]["family_context"]["family_key"], "door_hinge")

        for step in pfd["steps"]:
            self.assertTrue(step["evidence_refs"])
            self.assertTrue(step["knowledge_source_refs"])
            self.assertIn("confidence", step)
            self.assertIsInstance(step["needs_confirmation"], bool)
            self.assertTrue(step["ai_inferred"])

    def test_family_context_enhances_matching_drawing_clue(self):
        bundle = _door_hinge_bundle()
        bundle["manufacturing_clues"] = [
            {
                "process_step_id": "P30",
                "operation": "Riveting",
                "process_function": "Stake hinge pin to retain the hinge assembly",
                "confidence": 0.89,
                "evidence_refs": ["EV-RIVET"],
            }
        ]
        bundle["evidence"].append({"evidence_id": "EV-RIVET", "source": "drawing_page"})
        family_context = classify_part_family(bundle)

        pfd = infer_process_flow_from_drawing(bundle, family_context=family_context)
        riveting_step = next(step for step in pfd["steps"] if step["operation"] == "铆接")

        self.assertIn("EV-RIVET", riveting_step["evidence_refs"])
        self.assertTrue(riveting_step["knowledge_source_refs"])
        self.assertEqual(
            riveting_step["process_function"],
            "Stake hinge pin to retain the hinge assembly",
        )
        self.assertTrue(riveting_step["ai_inferred"])

    def test_family_context_can_use_default_template_from_family_key_only(self):
        bundle = _door_hinge_bundle()

        pfd = infer_process_flow_from_drawing(
            bundle,
            family_context={
                "family_key": "limiter",
                "family_name": "限位器",
                "confidence": 0.82,
            },
        )

        operations = [step["operation"] for step in pfd["steps"]]
        self.assertIn("功能检验", operations)
        self.assertIn("压装", operations)
        self.assertEqual(pfd["metadata"]["family_context"]["family_key"], "limiter")
        self.assertTrue(
            all(step["knowledge_source_refs"] for step in pfd["steps"])
        )

    def test_process_inference_variant_feeds_family_pfd_route(self):
        bundle = _door_hinge_bundle()
        bundle["technical_requirements"].append(
            {
                "text": "冲压型铰链采用级进模冲压，含卷圆、焊接螺母、压装衬套和销轴铆接。",
                "evidence_refs": ["EV-HINGE"],
            }
        )
        family_context = load_part_family_knowledge("door_hinge")

        pfd = infer_process_flow_from_drawing(bundle, family_context=family_context)

        operations = [step["operation"] for step in pfd["steps"]]
        self.assertIn("级进模冲压(12工位)", operations)
        self.assertIn("焊接/压铆螺母", operations)
        self.assertIn("压装衬套+销轴铆接", operations)
        self.assertNotIn("热锻成形", operations)
        self.assertEqual(
            pfd["metadata"]["family_context"]["family_key"],
            "door_hinge",
        )
        process_inference_steps = [
            step for step in pfd["steps"] if step["source"] == "part_family_knowledge"
        ]
        self.assertTrue(
            any(
                "process_inference:door_hinge:stamped_hinge_progressive"
                in step["knowledge_source_refs"]
                for step in process_inference_steps
            )
        )


def _door_hinge_bundle():
    refs = ["EV-HINGE"]
    return {
        "drawing_identity": {
            "part_name": "FRONT DOOR HINGE ASSEMBLY",
            "drawing_number": "HINGE-001",
            "revision": "A",
            "evidence_refs": refs,
        },
        "materials": [{"name": "SPCC steel sheet", "evidence_refs": refs}],
        "technical_requirements": [
            {
                "text": "Door hinge includes hinge pin, bushing, rotation torque and opening angle requirements",
                "evidence_refs": refs,
            }
        ],
        "manufacturing_clues": [],
        "special_characteristics": [],
        "evidence": [{"evidence_id": "EV-HINGE", "source": "drawing_page"}],
    }


if __name__ == "__main__":
    unittest.main()
