import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from minos_core.pipeline import generate_three_tables_from_drawing


class PipelinePartFamilyContextTests(unittest.TestCase):
    def test_generate_three_tables_passes_loaded_family_context_into_pfd_and_recommendations(self):
        classification = {
            "family_key": "door_hinge",
            "family_name": "门铰链",
            "confidence": 0.91,
            "needs_confirmation": False,
        }
        knowledge = _door_hinge_knowledge()
        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_pipeline_with_patches(
                tmpdir,
                classification=classification,
                knowledge=knowledge,
                captured=captured,
            )

        pfd_family_context = captured["pfd_family_context"]
        self.assertIsInstance(pfd_family_context, dict)
        self.assertEqual(pfd_family_context["family_key"], "door_hinge")
        self.assertEqual(
            pfd_family_context["pfmea_patterns"][0]["pattern_id"],
            "door-hinge-pfmea-rivet",
        )

        metadata = result["metadata"]
        self.assertEqual(metadata["part_family_classification"]["family_key"], "door_hinge")
        self.assertEqual(metadata["family_context"]["family_name"], "门铰链")

        chain_metadata = result["chain"]["metadata"]
        self.assertEqual(chain_metadata["part_family_classification"]["family_key"], "door_hinge")
        self.assertEqual(chain_metadata["family_context"]["family_key"], "door_hinge")

        recs = chain_metadata["knowledge_recommendations"]
        family_rec = next(item for item in recs if item["source"] == "door-hinge-pfmea-rivet")
        self.assertEqual(family_rec["score"], 100)
        self.assertEqual(family_rec["match_level"], "family_operation_characteristic")

    def test_unknown_family_keeps_old_path_and_does_not_load_family_knowledge(self):
        classification = {
            "family_key": "unknown",
            "family_name": "未知零件族",
            "confidence": 0.2,
            "needs_confirmation": True,
        }
        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_pipeline_with_patches(
                tmpdir,
                classification=classification,
                knowledge=None,
                captured=captured,
            )

        self.assertIsNone(captured["pfd_family_context"])
        self.assertFalse(captured["load_part_family_knowledge_called"])
        self.assertEqual(result["metadata"]["part_family_classification"]["family_key"], "unknown")
        self.assertEqual(result["metadata"]["family_context"], {})
        self.assertEqual(result["chain"]["metadata"]["family_context"], {})


class _Gate:
    def __init__(
        self,
        *,
        can_continue: bool = True,
        allow_user_export: bool = False,
        needs_human_review: bool = True,
    ) -> None:
        self.can_continue = can_continue
        self.allow_user_export = allow_user_export
        self.needs_human_review = needs_human_review
        self.manual_review_items: list[dict[str, object]] = []

    def model_dump(self) -> dict[str, object]:
        return {
            "can_continue": self.can_continue,
            "allow_user_export": self.allow_user_export,
            "needs_human_review": self.needs_human_review,
            "manual_review_items": [],
            "needs_confirmation_items": [],
        }


def _run_pipeline_with_patches(
    tmpdir: str,
    *,
    classification: dict[str, object],
    knowledge: dict[str, object] | None,
    captured: dict[str, object],
) -> dict[str, object]:
    root = Path(tmpdir)
    drawing_path = root / "drawing.png"
    drawing_path.write_bytes(b"not-a-real-image")
    captured["load_part_family_knowledge_called"] = False

    def infer_pfd(drawing_analysis, family_context=None):
        captured["pfd_family_context"] = family_context
        return _process_flow()

    def load_part_family_knowledge(family_key):
        captured["load_part_family_knowledge_called"] = True
        if knowledge is None:
            raise AssertionError("unknown family should not load family knowledge")
        self_key = knowledge.get("family_key")
        if self_key:
            assert family_key == self_key
        return knowledge

    patches = [
        patch("minos_core.drawing_input.load_drawing_source", return_value={"path": str(drawing_path)}),
        patch("minos_core.drawing_input.render_drawing_pages", return_value=["page-1"]),
        patch("minos_core.drawing_analysis.analyze_drawing_pages", return_value=_drawing_analysis()),
        patch("minos_core.drawing_analysis.evaluate_drawing_recognition_gate", return_value=_Gate()),
        patch("minos_core.part_family_classifier.classify_part_family", return_value=classification),
        patch("minos_core.part_family_knowledge.load_part_family_knowledge", side_effect=load_part_family_knowledge),
        patch("minos_core.drawing_to_pfd.infer_process_flow_from_drawing", side_effect=infer_pfd),
        patch("minos_core.characteristic_registry.build_characteristic_registry", return_value={}),
        patch("minos_core.quality_gates.evaluate_pfd_bundle_gate", return_value=_Gate()),
        patch("minos_core.quality_gates.evaluate_pfmea_bundle_gate", return_value=_Gate()),
        patch("minos_core.quality_gates.evaluate_control_plan_bundle_gate", return_value=_Gate()),
        patch("minos_core.pfd_to_pfmea_ai.infer_pfmea_from_process_flow", return_value=_pfmea()),
        patch("minos_core.generate_control_plan.generate_control_plan_from_pfmea", return_value=_control_plan()),
        patch("minos_core.pipeline.evaluate_export_gate", return_value=_Gate()),
        patch("minos_core.pipeline.export_three_table_workbook", side_effect=_write_export),
        patch("minos_core.pipeline.export_split_three_table_workbooks", side_effect=_write_split_exports),
        patch("minos_core.action_tracking.build_action_items", return_value=[]),
        patch("minos_core.action_tracking.action_items_summary", return_value={"total": 0}),
        patch("minos_core.three_table_linkage.build_three_table_linkage_map", return_value={"gaps": []}),
        patch("minos_core.three_table_linkage.evaluate_three_table_linkage", return_value={}),
        patch("minos_core.risk_structure.build_risk_structure", return_value={}),
        patch("minos_core.edit_patch.evaluate_edit_export_gate", return_value={}),
        patch("minos_core.edit_patch._build_review_dashboard", return_value={}),
        patch("minos_core.knowledge_recommendation.load_knowledge_rules", return_value=[]),
    ]
    with ExitStack() as stack:
        for item in patches:
            stack.enter_context(item)
        return generate_three_tables_from_drawing(
            drawing_path,
            root / "out",
            context={"operator": "unit-test"},
            analyzer=object(),
        )


def _write_export(chain, path, **kwargs):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"test workbook")
    return destination


def _write_split_exports(chain, output_dir, **kwargs):
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    result = {}
    for name in ("process_flow", "pfmea", "control_plan"):
        path = directory / f"{name}.xlsx"
        path.write_bytes(b"test workbook")
        result[name] = path
    return result


def _drawing_analysis():
    return {
        "drawing_identity": {"part_name": "Door hinge", "drawing_number": "DH-001"},
        "manufacturing_clues": [],
        "special_characteristics": [],
        "evidence": [{"evidence_id": "EV-1", "source": "unit"}],
    }


def _process_flow():
    return {
        "document_type": "process_flow",
        "product": {"part_name": "Door hinge"},
        "drawings": [],
        "characteristics": [],
        "steps": [
            {
                "process_step_id": "P10",
                "operation": "铆接",
                "process_function": "控制铆接高度",
                "special_characteristics": ["铆接高度"],
                "evidence_refs": ["EV-1"],
            }
        ],
        "links": [],
        "pending_fields": [],
        "ai_inferred_items": [],
    }


def _pfmea():
    return {
        "document_type": "pfmea",
        "rows": [
            {
                "pfmea_id": "PFMEA-P10-001",
                "process_step_id": "P10",
                "failure_mode": "铆接高度不足",
                "failure_effect": "铰链转动异常",
                "failure_cause": "",
                "classification": "SC",
                "characteristic_refs": ["铆接高度"],
                "prevention_control": "",
                "detection_control": "",
            }
        ],
        "pending_fields": [],
        "ai_inferred_items": [],
    }


def _control_plan():
    return {
        "document_type": "control_plan",
        "rows": [
            {
                "control_plan_id": "CP-PFMEA-P10-001",
                "pfmea_id": "PFMEA-P10-001",
                "process_step_id": "P10",
            }
        ],
        "pending_fields": [],
        "ai_inferred_items": [],
    }


def _door_hinge_knowledge():
    return {
        "schema_version": "minos-core.part_family_knowledge.v1",
        "family_key": "door_hinge",
        "family_name": "门铰链",
        "process_route_templates": [],
        "pfmea_patterns": [
            {
                "pattern_id": "door-hinge-pfmea-rivet",
                "process_step_id": "P10",
                "failure_mode": "铆接高度不足",
                "failure_cause": "铆接机行程或定位未确认",
                "source_refs": [{"source_id": "door-hinge-seed", "row": 31}],
            }
        ],
        "control_plan_patterns": [
            {
                "pattern_id": "door-hinge-cp-rivet",
                "process_step_id": "P10",
                "characteristic": "铆接高度",
                "measurement_method": "高度规",
                "sample_frequency": "首件和巡检",
            }
        ],
        "source_refs": [{"source_id": "door-hinge-seed"}],
    }


if __name__ == "__main__":
    unittest.main()
