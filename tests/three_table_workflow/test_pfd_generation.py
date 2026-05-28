import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from PIL import Image

from minos_core.adapters.multimodal import FakeMultimodalDrawingAnalyzer
from minos_core.drawing_analysis import (
    DrawingAnalysisError,
    analyze_drawing_pages,
    evaluate_drawing_recognition_gate,
)
from minos_core.drawing_input import (
    DrawingInputError,
    load_drawing_source,
    render_drawing_pages,
)
from minos_core.drawing_to_pfd import infer_process_flow_from_drawing, normalize_process_flow_steps
from minos_core.exporters.three_table_workbooks import (
    export_split_three_table_workbooks,
    export_three_table_workbook,
)
from minos_core.generate_control_plan import (
    generate_control_plan_from_pfmea,
    normalize_control_plan_rows,
)
from minos_core.pfd_to_pfmea_ai import (
    infer_pfmea_from_process_flow,
    normalize_pfmea_rows,
)
from minos_core.pipeline import generate_three_tables_from_drawing
from minos_core.pipeline_chain import (
    generate_cp_from_confirmed_pfmea,
    generate_pfd_from_drawing,
    generate_pfmea_from_confirmed_pfd,
)
from minos_core.three_table_result import build_three_table_generation_envelope
from minos_core.cli import main
from minos_core.schemas import validate_bundle_schema

from .conftest import rows_by_step, PFMEA_CONTROL_LOGIC_FIELDS, assert_pfmea_ai_risk_row


class PFDGenerationTests(unittest.TestCase):
    """Tests for PFDGeneration workflow stage."""

    def test_llm_pfd_generation_normalizes_standard_process_flow_fields(self):
        llm_payload = {
            "steps": [
                {
                    "process_step_id": "P10",
                    "operation_type": "加工",
                    "operation": "冲孔",
                    "output_result": "冲孔完成",
                    "process_function": "形成安装孔",
                    "equipment": "压力机",
                    "product_characteristics": "",
                    "product_characteristic_class": "无",
                    "process_characteristics": "",
                    "process_characteristic_class": "无",
                    "special_characteristics": [],
                    "needs_confirmation": False,
                },
                {
                    "process_step_id": "P20",
                    "flow_symbol": "检验",
                    "operation": "过程检验",
                    "process_function": "确认孔位",
                    "equipment": "检具",
                    "special_characteristics": [],
                    "needs_confirmation": True,
                },
            ]
        }

        with patch("minos_core.pipeline_chain.OpenAITextGenerator") as generator:
            generator.return_value.generate_structured.return_value = llm_payload

            pfd = generate_pfd_from_drawing({"drawing_identity": {"part_name": "Demo"}})

        first, second = pfd["steps"]
        self.assertEqual(first["flow_type"], "operation")
        self.assertEqual(first["flow_symbol"], "operation")
        self.assertEqual(first["flow_type_display"], "加工")
        self.assertEqual(first["input_material"], "Demo")
        self.assertEqual(first["output_result"], "冲孔完成")
        self.assertEqual(first["previous_step_ids"], [])
        self.assertEqual(first["next_step_ids"], ["P20"])
        self.assertEqual(second["flow_type"], "inspection")
        self.assertEqual(second["previous_step_ids"], ["P10"])
        self.assertEqual(second["next_step_ids"], [])
        for step in pfd["steps"]:
            for field in (
                "operation_type",
                "operation",
                "input_material",
                "output_result",
                "next_step_ids",
                "previous_step_ids",
                "equipment",
                "product_characteristics",
                "process_characteristics",
                "needs_confirmation",
            ):
                self.assertIn(field, step)


    def test_rule_pfd_inference_outputs_standard_flow_type_fields(self):
        pfd = infer_process_flow_from_drawing(
            {
                "drawing_identity": {"part_name": "DEMO"},
                "manufacturing_clues": [
                    {
                        "process_step_id": "P10",
                        "operation": "piercing",
                        "evidence_refs": ["drawing_page_001"],
                    }
                ],
                "evidence": [{"evidence_id": "drawing_page_001"}],
            }
        )

        self.assertTrue(pfd["steps"])
        for step in pfd["steps"]:
            self.assertIn(step["flow_type"], {"operation", "inspection", "transport", "storage", "rework", "outsourced"})
            self.assertEqual(step["flow_symbol"], step["flow_type"])
            self.assertIn("operation_type", step)
            self.assertIn("input_material", step)
            self.assertIn("output_result", step)
            self.assertIsInstance(step["previous_step_ids"], list)
            self.assertIsInstance(step["next_step_ids"], list)


    def test_normalize_process_flow_steps_preserves_existing_non_linear_links(self):
        steps = [
            {
                "process_step_id": "P10",
                "operation": "外协加工",
                "next_step_ids": ["P20", "P30"],
            },
            {
                "process_step_id": "P20",
                "operation": "返工确认",
                "previous_step_ids": ["P10", "P30"],
                "next_step_ids": ["P10"],
            },
            {
                "process_step_id": "P30",
                "operation": "最终检验",
            },
        ]

        normalize_process_flow_steps(steps)

        self.assertEqual(steps[0]["previous_step_ids"], [])
        self.assertEqual(steps[0]["next_step_ids"], ["P20", "P30"])
        self.assertEqual(steps[1]["previous_step_ids"], ["P10", "P30"])
        self.assertEqual(steps[1]["next_step_ids"], ["P10"])
        self.assertEqual(steps[2]["previous_step_ids"], ["P20"])
        self.assertEqual(steps[2]["next_step_ids"], [])


    def test_normalize_process_flow_steps_does_not_create_material_pseudo_step(self):
        steps = [
            {
                "process_step_id": "P05",
                "operation": "压装铰链总成",
            },
            {
                "process_step_id": "P10",
                "operation": "过程检验",
            },
        ]

        normalize_process_flow_steps(steps, default_input_material="D00R HINGE 尾门铰链")

        self.assertEqual([step["process_step_id"] for step in steps], ["P05", "P10"])
        self.assertEqual(steps[0]["operation"], "压装铰链总成")
        self.assertEqual(steps[0]["input_material"], "D00R HINGE 尾门铰链")
        self.assertEqual(steps[0]["previous_step_ids"], [])
        self.assertEqual(steps[0]["next_step_ids"], ["P10"])




if __name__ == "__main__":
    unittest.main()
