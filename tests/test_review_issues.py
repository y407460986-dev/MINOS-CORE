from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from minos_core.adapters.multimodal import FakeMultimodalDrawingAnalyzer
from minos_core.drawing_analysis import analyze_drawing_pages, evaluate_drawing_recognition_gate
from minos_core.drawing_input import load_drawing_source, render_drawing_pages
from minos_core.edit_patch import EDIT_PATCH_VERSION, apply_edit_patch, evaluate_edit_export_gate, export_edited_three_tables
from minos_core.quality_gates import evaluate_export_gate


def _review_ready_chain() -> dict:
    return {
        "document_type": "apqp_chain",
        "schema_version": "minos-core.generated.v1",
        "product": {},
        "process_steps": [
            {
                "process_step_id": "P10",
                "sequence": 10,
                "operation": "检验",
                "process_function": "确认尺寸",
                "evidence_refs": ["EV-1"],
                "review_status": "已确认",
                "needs_confirmation": False,
            }
        ],
        "failure_modes": [
            {
                "pfmea_id": "PFMEA-P10-001",
                "process_step_id": "P10",
                "process_function": "确认尺寸",
                "failure_mode": "漏检",
                "failure_effect": "不合格流出",
                "severity": 6,
                "failure_cause": "检具失准",
                "occurrence": 2,
                "prevention_control": "检具校准",
                "detection_control": "首件检验",
                "detection": 3,
                "action_priority": "L",
                "evidence_refs": ["EV-1"],
                "review_status": "已确认",
                "needs_confirmation": False,
            }
        ],
        "controls": [
            {
                "control_plan_id": "CP-P10-001",
                "process_step_id": "P10",
                "pfmea_id": "PFMEA-P10-001",
                "product_process_characteristic": "尺寸",
                "specification": "按图纸",
                "measurement_method": "卡尺",
                "sample_size": "1 件",
                "sample_frequency": "每批",
                "control_method": "首件检验",
                "reaction_plan": "隔离并通知质量",
                "evidence_refs": ["EV-1"],
                "review_status": "已确认",
                "needs_confirmation": False,
            }
        ],
        "evidence": [{"evidence_id": "EV-1", "source": "fixture", "content": "确认记录"}],
        "links": [],
        "pending_fields": [],
        "ai_inferred_items": [],
        "metadata": {"strict_aiag_vda_pfmea_gate": True},
    }


class ReviewIssueTests(unittest.TestCase):
    def test_drawing_analysis_normalizes_evidence_regions_and_review_issues(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "drawing.png"
            Image.new("RGB", (100, 80), color="white").save(image_path)
            pages = render_drawing_pages(load_drawing_source(image_path))
            payload = {
                "drawing_identity": {"part_name": "", "drawing_number": "D-1", "revision": "A"},
                "materials": [
                    {
                        "name": "SPCC",
                        "confidence": 0.7,
                        "evidence_refs": ["drawing_page_001"],
                        "evidence_regions": [
                            {
                                "evidence_id": "drawing_page_001",
                                "boundingBox": {"left": 10, "top": 5, "right": 30, "bottom": 25},
                                "rawText": "SPCC",
                                "confidence": "0.91",
                            }
                        ],
                    }
                ],
                "manufacturing_clues": [
                    {"operation": "blanking", "confidence": 0.9, "evidence_refs": ["drawing_page_001"]}
                ],
            }

            bundle = analyze_drawing_pages(
                pages,
                FakeMultimodalDrawingAnalyzer(json.dumps(payload)),
            )

        region = bundle["materials"][0]["evidence_regions"][0]
        self.assertEqual(region["evidence_ref"], "drawing_page_001")
        self.assertEqual(region["box"], {"x": 10.0, "y": 5.0, "width": 20.0, "height": 20.0})
        gate = evaluate_drawing_recognition_gate(bundle)
        self.assertTrue(gate.review_issues)
        self.assertTrue(all("review_issue_version" in item for item in gate.review_issues))

    def test_export_gate_blocks_unresolved_review_issue_and_edit_patch_resolves_it(self):
        source = _review_ready_chain()
        source["metadata"]["review_issues"] = [
            {
                "review_issue_version": "minos-core.review_issue.v1",
                "issue_id": "RI-test",
                "category": "人工复核",
                "message": "需要确认",
                "severity": "blocker",
                "status": "待处理",
            }
        ]

        gate = evaluate_export_gate(source)
        self.assertFalse(gate.allow_user_export)
        self.assertIn("RI-test", [item["issue_id"] for item in gate.review_issues])

        edited = apply_edit_patch(
            source,
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "items": [{"action": "resolve_review_issue", "table": "metadata", "target_id": "RI-test"}],
            },
        )
        self.assertEqual(edited["metadata"]["review_issues"][0]["status"], "已处理")
        self.assertTrue(evaluate_export_gate(edited).allow_user_export)

    def test_edit_export_gate_blocks_knowledge_recommendations_and_change_impacts(self):
        source = _review_ready_chain()
        source["metadata"]["knowledge_recommendations"] = [
            {
                "recommendation_id": "KR-1",
                "target_id": "PFMEA-P10-001",
                "reason": "高置信推荐",
                "confidence": 0.95,
                "status": "待确认",
            }
        ]
        source["metadata"]["change_impacts"] = [
            {
                "item_id": "CI-1",
                "target": "process_flow:P10",
                "category": "变更影响",
                "message": "下游需确认",
                "severity": "blocker",
                "status": "待同步",
            }
        ]

        before = evaluate_edit_export_gate(source)
        self.assertFalse(before["final_export_allowed"])
        self.assertIn("KR-1", before["knowledge_recommendations"])
        self.assertIn("CI-1", before["change_impacts"])

        edited = apply_edit_patch(
            copy.deepcopy(source),
            {
                "edit_patch_version": EDIT_PATCH_VERSION,
                "edited_by": "qe",
                "reason": "确认闭环",
                "items": [
                    {"action": "accept_recommendation", "table": "metadata", "target_id": "KR-1"},
                    {"action": "resolve_change_impact", "table": "metadata", "target_id": "CI-1"},
                ],
            },
        )

        after = evaluate_edit_export_gate(edited)
        self.assertTrue(after["final_export_allowed"])
        with tempfile.TemporaryDirectory() as tmpdir:
            result = export_edited_three_tables(edited, Path(tmpdir), export_mode="final")
        self.assertTrue(result["final_export_allowed"])


if __name__ == "__main__":
    unittest.main()
