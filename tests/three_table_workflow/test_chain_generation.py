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
    _family_route_summary,
)
from minos_core.three_table_result import build_three_table_generation_envelope
from minos_core.cli import main
from minos_core.schemas import validate_bundle_schema

from .conftest import rows_by_step, PFMEA_CONTROL_LOGIC_FIELDS, assert_pfmea_ai_risk_row


class ChainGenerationTests(unittest.TestCase):
    """Tests for PFD/PFMEA/CP chain generation and normalization."""

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

    def test_chain_pfd_generation_adds_canonical_contract_and_row_provenance(self):
        llm_payload = {
            "steps": [
                {
                    "process_step_id": "P10",
                    "operation_type": "加工",
                    "operation": "冲压成形",
                    "output_result": "冲压完成",
                    "process_function": "形成安装面",
                    "equipment": "压力机",
                    "product_characteristics": "",
                    "product_characteristic_class": "无",
                    "process_characteristics": "",
                    "process_characteristic_class": "无",
                    "special_characteristics": [],
                    "needs_confirmation": False,
                }
            ]
        }
        drawing_analysis = {
            "drawing_identity": {"part_name": "Demo"},
            "evidence": [
                {
                    "evidence_id": "EV-DRAW-001",
                    "source": "drawing",
                    "confidence": 0.91,
                }
            ],
        }

        with patch("minos_core.pipeline_chain.OpenAITextGenerator") as generator:
            llm = generator.return_value
            llm.generate_structured.return_value = llm_payload

            pfd = generate_pfd_from_drawing(drawing_analysis)

        call_kwargs = llm.generate_structured.call_args.kwargs
        schema_items = (
            call_kwargs["response_format"]["json_schema"]["schema"]["properties"]["steps"]["items"]
        )
        for field in ("evidence_refs", "confidence", "ai_inferred", "needs_confirmation"):
            self.assertIn(field, schema_items["properties"])
            self.assertIn(field, schema_items["required"])
        self.assertIn("evidence_refs", call_kwargs["system_prompt"])
        self.assertIn("confidence", call_kwargs["system_prompt"])
        self.assertEqual(pfd["document_type"], "process_flow")
        self.assertEqual(pfd["schema_version"], "minos-core.generated.v1")
        row = pfd["steps"][0]
        self.assertEqual(row["evidence_refs"], ["EV-DRAW-001"])
        self.assertAlmostEqual(row["confidence"], 0.91)
        self.assertTrue(row["ai_inferred"])
        self.assertFalse(row["needs_confirmation"])

    def test_chain_pfd_generation_does_not_fallback_to_all_ocr_blocks(self):
        llm_payload = {
            "steps": [
                {
                    "process_step_id": "P10",
                    "operation_type": "加工",
                    "operation": "冲压成形",
                    "output_result": "冲压完成",
                    "process_function": "形成安装面",
                    "equipment": "压力机",
                    "product_characteristics": "",
                    "product_characteristic_class": "无",
                    "process_characteristics": "",
                    "process_characteristic_class": "无",
                    "special_characteristics": [],
                    "needs_confirmation": False,
                }
            ]
        }
        drawing_analysis = {
            "drawing_identity": {"part_name": "Demo"},
            "evidence": [
                {
                    "evidence_id": "drawing_page_001",
                    "source": "drawing_page",
                    "confidence": 0.91,
                },
                *[
                    {
                        "evidence_id": f"ocr_block_{i:03d}",
                        "source": "ocr_block",
                        "confidence": 0.91,
                    }
                    for i in range(1, 62)
                ],
            ],
        }

        with patch("minos_core.pipeline_chain.OpenAITextGenerator") as generator:
            generator.return_value.generate_structured.return_value = llm_payload

            pfd = generate_pfd_from_drawing(drawing_analysis)

        row = pfd["steps"][0]
        self.assertEqual(row["evidence_refs"], ["drawing_page_001"])
        self.assertNotIn("ocr_block_001", row["evidence_refs"])

    def test_chain_pfd_generation_expands_incoming_inspection_from_bom_items(self):
        llm_payload = {
            "steps": [
                {
                    "process_step_id": "P10",
                    "flow_type": "inspection",
                    "flow_symbol": "inspection",
                    "operation_type": "检验",
                    "operation": "来料检验",
                    "input_material": "锻件",
                    "output_result": "来料合格",
                    "previous_step_ids": [],
                    "next_step_ids": [],
                    "process_function": "检查锻件外观和尺寸",
                    "equipment": "来料检验台",
                    "product_characteristics": "",
                    "product_characteristic_class": "无",
                    "process_characteristics": "",
                    "process_characteristic_class": "无",
                    "special_characteristics": [],
                    "evidence_refs": ["EV-BOM"],
                    "confidence": 0.88,
                    "ai_inferred": True,
                    "needs_confirmation": False,
                }
            ]
        }
        drawing_analysis = {
            "drawing_identity": {"part_name": "尾门铰链总成"},
            "sub_components": [
                {"part_name": "锻件", "quantity": 1, "part_number": "JLV03000501", "evidence_refs": ["EV-BOM"]},
                {"part_name": "销轴", "quantity": 1, "part_number": "BZJ01011100", "evidence_refs": ["EV-BOM"]},
                {"part_name": "衬套", "quantity": 1, "part_number": "BZJ01011000", "evidence_refs": ["EV-BOM"]},
            ],
            "evidence": [{"evidence_id": "EV-BOM", "source": "drawing_bom"}],
        }

        with patch("minos_core.pipeline_chain.OpenAITextGenerator") as generator:
            llm = generator.return_value
            llm.generate_structured.return_value = llm_payload

            pfd = generate_pfd_from_drawing(drawing_analysis)

        user_prompt = llm.generate_structured.call_args.kwargs["user_prompt"]
        self.assertIn("BOM子件", user_prompt)
        self.assertIn("销轴", user_prompt)
        self.assertIn("衬套", user_prompt)

        incoming = pfd["steps"][0]
        combined = " ".join(
            str(incoming.get(field, ""))
            for field in ("input_material", "process_function", "product_characteristics", "process_characteristics")
        )
        for expected in ("锻件", "销轴", "衬套"):
            self.assertIn(expected, combined)

    def test_family_route_summary_scans_process_inference_steps_and_key_checks(self):
        route_templates = [
            {"operation": "来料检验"},
            {"operation": "入库"},
            {
                "template_id": "door-hinge-process",
                "steps": [
                    {
                        "operation": "来料检验",
                        "process_function": "锻件、销轴、衬套按BOM检验",
                    },
                    {
                        "operation": "压装衬套+销轴铆接",
                        "process_function": "压入力和转动扭矩确认",
                    },
                ],
            },
        ]

        summary = _family_route_summary(route_templates)

        self.assertIn("来料检验(锻件、销轴、衬套按BOM检验)", summary)
        self.assertIn("压装衬套+销轴铆接(压入力和转动扭矩确认)", summary)

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

    def test_chain_pfmea_inherits_confirmed_pfd_process_fields(self):
        llm_payload = {
            "rows": [
                {
                    "pfmea_id": "",
                    "process_step_id": "P10",
                    "process_item": "制造过程",
                    "process_step_name": "",
                    "work_element_4m": "机",
                    "function_process_step": "",
                    "function_work_element": "压力机稳定输出",
                    "failure_effect": "下一工序无法装配",
                    "severity": 8,
                    "failure_mode": "安装孔偏移",
                    "failure_cause": "定位销磨损",
                    "prevention_control": "点检定位销",
                    "occurrence": 4,
                    "detection_control": "首件检验孔位",
                    "detection": 5,
                    "action_priority": "M",
                    "special_characteristics": "SC",
                    "preventive_action": "点检定位销并确认孔位能力",
                    "detection_action": "增加孔位巡检频次",
                    "responsible_person": "",
                    "target_date": "",
                    "status": "未开始",
                    "needs_confirmation": True,
                }
            ]
        }
        confirmed_pfd = {
            "steps": [
                {
                    "process_step_id": "P10",
                    "operation": "冲压安装孔",
                    "process_function": "形成安装孔位置",
                    "equipment": "压力机",
                    "product_characteristics": "安装孔位置度",
                    "process_characteristics": "冲压力",
                }
            ]
        }

        with patch("minos_core.pipeline_chain.OpenAITextGenerator") as generator:
            llm = generator.return_value
            llm.generate_structured.return_value = llm_payload

            pfmea = generate_pfmea_from_confirmed_pfd({}, confirmed_pfd)

        row = pfmea["rows"][0]
        call_kwargs = llm.generate_structured.call_args.kwargs
        schema_items = (
            call_kwargs["response_format"]["json_schema"]["schema"]["properties"]["rows"]["items"]
        )
        for field in PFMEA_CONTROL_LOGIC_FIELDS:
            self.assertIn(field, schema_items["properties"])
            self.assertIn(field, schema_items["required"])
        self.assertIn("原因过程参数", call_kwargs["system_prompt"])
        self.assertIn("预防控制对象", call_kwargs["system_prompt"])
        self.assertIn("探测对象", call_kwargs["system_prompt"])
        self.assertIn("预防控制必须控制失效原因", call_kwargs["user_prompt"])
        self.assertEqual(row["process_step_id"], "P10")
        self.assertEqual(row["operation"], "冲压安装孔")
        self.assertEqual(row["process_step"], "冲压安装孔")
        self.assertEqual(row["process_step_name"], "冲压安装孔")
        self.assertEqual(row["structure_process_step"], "冲压安装孔")
        self.assertEqual(row["structure_process_item"], "制造过程")
        self.assertEqual(row["structure_work_element"], "压力机")
        self.assertEqual(row["function_process_item"], "制造过程")
        self.assertEqual(row["function_process_step"], "形成安装孔位置")
        self.assertEqual(row["function_work_element"], "压力机稳定输出")
        self.assertEqual(row["function_requirement"], "形成安装孔位置")
        self.assertEqual(row["preventive_action"], "点检定位销并确认孔位能力")
        self.assertEqual(row["detection_action"], "增加孔位巡检频次")
        self.assertEqual(row["optimization_action"], "点检定位销并确认孔位能力；增加孔位巡检频次")
        self.assertEqual(row["AP"], "M")
        self.assertNotIn("rpn", row)
        self.assertNotIn("after_rpn", row)
        self.assertEqual(row["pfmea_id"], "PFMEA-P10-01")
        self.assertEqual(row["cause_process_parameter"], "冲压力")
        self.assertIn("定位销磨损", row["prevention_control_target"])
        self.assertTrue(row["prevention_control_timing"])
        self.assertIn("安装孔", row["detection_control_target"])
        self.assertTrue(row["detection_control_timing"])
        self.assertIn("预防", row["control_logic_review"])
        self.assertIn("探测", row["control_logic_review"])

    def test_chain_pfmea_contract_inherits_evidence_confidence_and_characteristics(self):
        llm_payload = {
            "rows": [
                {
                    "pfmea_id": "",
                    "process_step_id": "P20",
                    "process_item": "制造过程",
                    "process_step_name": "",
                    "structure_process_item": "制造过程",
                    "structure_process_step": "",
                    "structure_work_element": "压力机",
                    "work_element_4m": "机",
                    "function_process_item": "制造过程",
                    "function_process_step": "",
                    "function_work_element": "压力机稳定输出",
                    "failure_effect": "安装孔位置偏差导致装配困难",
                    "severity": 8,
                    "failure_mode": "安装孔偏移",
                    "failure_cause": "定位销磨损",
                    "cause_process_parameter": "定位销状态",
                    "prevention_control": "点检定位销",
                    "prevention_control_target": "定位销磨损",
                    "prevention_control_timing": "每班",
                    "occurrence": 4,
                    "detection_control": "首件检验孔位",
                    "detection_control_target": "安装孔位置",
                    "detection_control_timing": "首件",
                    "detection": 5,
                    "action_priority": "M",
                    "special_characteristics": "无",
                    "preventive_action": "更换定位销",
                    "detection_action": "增加巡检",
                    "optimization_action": "更换定位销；增加巡检",
                    "responsible_person": "",
                    "target_date": "",
                    "status": "未开始",
                    "control_logic_review": "预防和探测分列",
                    "needs_confirmation": False,
                }
            ]
        }
        confirmed_pfd = {
            "steps": [
                {
                    "process_step_id": "P20",
                    "operation": "冲孔",
                    "process_function": "形成安装孔",
                    "equipment": "压力机",
                    "product_characteristic_class": "SC",
                    "special_characteristics": ["SC-HOLE-POS"],
                    "evidence_refs": ["EV-PFD-020"],
                    "confidence": 0.84,
                }
            ]
        }

        with patch("minos_core.pipeline_chain.OpenAITextGenerator") as generator:
            llm = generator.return_value
            llm.generate_structured.return_value = llm_payload

            pfmea = generate_pfmea_from_confirmed_pfd({}, confirmed_pfd)

        call_kwargs = llm.generate_structured.call_args.kwargs
        schema_items = (
            call_kwargs["response_format"]["json_schema"]["schema"]["properties"]["rows"]["items"]
        )
        for field in (
            "evidence_refs",
            "confidence",
            "ai_inferred",
            "needs_confirmation",
            "special_characteristic_class",
            "characteristic_refs",
        ):
            self.assertIn(field, schema_items["properties"])
            self.assertIn(field, schema_items["required"])
        self.assertIn("evidence_refs", call_kwargs["system_prompt"])
        self.assertIn("confidence", call_kwargs["system_prompt"])

        self.assertEqual(pfmea["document_type"], "pfmea")
        self.assertEqual(pfmea["schema_version"], "minos-core.generated.v1")
        row = pfmea["rows"][0]
        self.assertEqual(row["evidence_refs"], ["EV-PFD-020"])
        self.assertAlmostEqual(row["confidence"], 0.84)
        self.assertTrue(row["ai_inferred"])
        self.assertFalse(row["needs_confirmation"])
        self.assertEqual(row["special_characteristic_class"], "SC")
        self.assertEqual(row["characteristic_refs"], ["SC-HOLE-POS"])
        self.assertEqual(row["special_characteristics"], "SC")

    def test_chain_pfmea_recalculates_action_priority_and_marks_low_confidence(self):
        llm_payload = {
            "rows": [
                {
                    "pfmea_id": "",
                    "process_step_id": "P20",
                    "process_item": "制造过程",
                    "process_step_name": "",
                    "structure_process_item": "制造过程",
                    "structure_process_step": "",
                    "structure_work_element": "压力机",
                    "work_element_4m": "机",
                    "function_process_item": "制造过程",
                    "function_process_step": "",
                    "function_work_element": "压力机稳定输出",
                    "failure_effect": "安装孔位置偏差导致装配困难",
                    "severity": 9,
                    "failure_mode": "安装孔偏移",
                    "failure_cause": "定位销磨损",
                    "cause_process_parameter": "定位销状态",
                    "prevention_control": "点检定位销",
                    "prevention_control_target": "定位销磨损",
                    "prevention_control_timing": "每班",
                    "occurrence": 3,
                    "detection_control": "首件检验孔位",
                    "detection_control_target": "安装孔位置",
                    "detection_control_timing": "首件",
                    "detection": 5,
                    "action_priority": "M",
                    "special_characteristics": "无",
                    "preventive_action": "更换定位销",
                    "detection_action": "增加巡检",
                    "optimization_action": "更换定位销；增加巡检",
                    "responsible_person": "",
                    "target_date": "",
                    "status": "未开始",
                    "control_logic_review": "预防和探测分列",
                    "evidence_refs": [],
                    "confidence": 0.62,
                    "ai_inferred": True,
                    "needs_confirmation": False,
                }
            ]
        }
        confirmed_pfd = {
            "steps": [
                {
                    "process_step_id": "P20",
                    "operation": "冲孔",
                    "process_function": "形成安装孔",
                    "equipment": "压力机",
                    "evidence_refs": ["EV-PFD-020"],
                    "confidence": 0.84,
                    "needs_confirmation": False,
                }
            ]
        }

        with patch("minos_core.pipeline_chain.OpenAITextGenerator") as generator:
            generator.return_value.generate_structured.return_value = llm_payload

            pfmea = generate_pfmea_from_confirmed_pfd({}, confirmed_pfd)

        row = pfmea["rows"][0]
        self.assertEqual(row["AP"], "H")
        self.assertEqual(row["action_priority"], "H")
        self.assertEqual(row["confidence"], 0.62)
        self.assertTrue(row["needs_confirmation"])

    def test_chain_pfmea_allows_manually_confirmed_surface_treatment_before_press_fit(self):
        confirmed_pfd = {
            "steps": [
                {
                    "process_step_id": "P10",
                    "operation": "表面处理镀锌",
                    "input_material": "已压装总成",
                    "output_result": "表面处理后总成",
                    "next_step_ids": ["P20"],
                },
                {
                    "process_step_id": "P20",
                    "operation": "压装衬套销轴铆接",
                    "input_material": "表面处理后总成",
                    "output_result": "压装完成总成",
                    "previous_step_ids": ["P10"],
                },
            ]
        }
        payloads = [
            {
                "rows": [
                    {
                        "pfmea_id": "",
                        "process_step_id": "P10",
                        "process_item": "制造过程",
                        "process_step_name": "",
                        "structure_process_item": "制造过程",
                        "structure_process_step": "",
                        "structure_work_element": "电镀线",
                        "work_element_4m": "机",
                        "function_process_item": "制造过程",
                        "function_process_step": "",
                        "function_work_element": "电镀线",
                        "failure_effect": "耐腐蚀能力不足",
                        "severity": 8,
                        "failure_mode": "镀层厚度不足",
                        "failure_cause": "电镀参数偏低",
                        "prevention_control": "电镀参数点检",
                        "occurrence": 3,
                        "detection_control": "镀层厚度检测",
                        "detection": 5,
                        "action_priority": "M",
                        "special_characteristics": "无",
                        "preventive_action": "",
                        "detection_action": "",
                        "responsible_person": "",
                        "target_date": "",
                        "status": "未开始",
                        "needs_confirmation": False,
                    }
                ]
            },
            {
                "rows": [
                    {
                        "pfmea_id": "",
                        "process_step_id": "P20",
                        "process_item": "制造过程",
                        "process_step_name": "",
                        "structure_process_item": "制造过程",
                        "structure_process_step": "",
                        "structure_work_element": "压装机",
                        "work_element_4m": "机",
                        "function_process_item": "制造过程",
                        "function_process_step": "",
                        "function_work_element": "压装机",
                        "failure_effect": "转动卡滞",
                        "severity": 7,
                        "failure_mode": "衬套压装不到位",
                        "failure_cause": "压装行程不足",
                        "prevention_control": "压装行程点检",
                        "occurrence": 5,
                        "detection_control": "压装后外观检查",
                        "detection": 5,
                        "action_priority": "M",
                        "special_characteristics": "无",
                        "preventive_action": "",
                        "detection_action": "",
                        "responsible_person": "",
                        "target_date": "",
                        "status": "未开始",
                        "needs_confirmation": False,
                    }
                ]
            },
        ]

        with patch("minos_core.pipeline_chain.OpenAITextGenerator") as generator:
            generator.return_value.generate_structured.side_effect = payloads

            pfmea = generate_pfmea_from_confirmed_pfd({}, confirmed_pfd)

        self.assertEqual(
            [row["process_step_id"] for row in pfmea["rows"]],
            ["P10", "P20"],
        )
        warning = pfmea["metadata"]["pfd_chain_warnings"][0]
        self.assertEqual(warning["type"], "surface_treatment_before_assembly")
        self.assertEqual(warning["from_step_id"], "P10")
        self.assertEqual(warning["to_step_id"], "P20")
        self.assertIn("人工确认", warning["message"])
        self.assertIn("继续生成", warning["message"])

    def test_chain_pfmea_allows_manually_confirmed_assembly_state_jump_between_linked_steps(self):
        confirmed_pfd = {
            "steps": [
                {
                    "process_step_id": "P10",
                    "operation": "过程尺寸检验",
                    "output_result": "尺寸合格的铰链零件放行至装配",
                    "next_step_ids": ["P20"],
                },
                {
                    "process_step_id": "P20",
                    "operation": "转运表面处理",
                    "input_material": "装配完成的尾门铰链总成",
                    "previous_step_ids": ["P10"],
                },
            ]
        }
        payloads = [
            {
                "rows": [
                    {
                        "pfmea_id": "",
                        "process_step_id": "P10",
                        "process_item": "制造过程",
                        "process_step_name": "",
                        "structure_process_item": "制造过程",
                        "structure_process_step": "",
                        "structure_work_element": "检具",
                        "work_element_4m": "机",
                        "function_process_item": "制造过程",
                        "function_process_step": "",
                        "function_work_element": "检具",
                        "failure_effect": "不合格流入后续装配",
                        "severity": 8,
                        "failure_mode": "尺寸误判",
                        "failure_cause": "检具未校准",
                        "prevention_control": "检具校准",
                        "occurrence": 3,
                        "detection_control": "复核记录",
                        "detection": 5,
                        "action_priority": "M",
                        "special_characteristics": "无",
                        "preventive_action": "",
                        "detection_action": "",
                        "responsible_person": "",
                        "target_date": "",
                        "status": "未开始",
                        "needs_confirmation": False,
                    }
                ]
            },
            {
                "rows": [
                    {
                        "pfmea_id": "",
                        "process_step_id": "P20",
                        "process_item": "制造过程",
                        "process_step_name": "",
                        "structure_process_item": "制造过程",
                        "structure_process_step": "",
                        "structure_work_element": "转运车",
                        "work_element_4m": "机",
                        "function_process_item": "制造过程",
                        "function_process_step": "",
                        "function_work_element": "转运车",
                        "failure_effect": "表面处理前状态混淆",
                        "severity": 7,
                        "failure_mode": "转运状态标识错误",
                        "failure_cause": "批次标识不清",
                        "prevention_control": "批次标识确认",
                        "occurrence": 3,
                        "detection_control": "转运前复核",
                        "detection": 5,
                        "action_priority": "M",
                        "special_characteristics": "无",
                        "preventive_action": "",
                        "detection_action": "",
                        "responsible_person": "",
                        "target_date": "",
                        "status": "未开始",
                        "needs_confirmation": False,
                    }
                ]
            },
        ]

        with patch("minos_core.pipeline_chain.OpenAITextGenerator") as generator:
            generator.return_value.generate_structured.side_effect = payloads

            pfmea = generate_pfmea_from_confirmed_pfd({}, confirmed_pfd)

        self.assertEqual([row["process_step_id"] for row in pfmea["rows"]], ["P10", "P20"])
        warning = pfmea["metadata"]["pfd_chain_warnings"][0]
        self.assertEqual(warning["type"], "assembly_state_jump")
        self.assertEqual(warning["from_step_id"], "P10")
        self.assertEqual(warning["to_step_id"], "P20")
        self.assertIn("人工确认", warning["message"])
        self.assertIn("继续生成", warning["message"])

    def test_chain_pfmea_generates_one_llm_request_per_confirmed_pfd_step(self):
        confirmed_pfd = {
            "steps": [
                {
                    "process_step_id": "P10",
                    "operation": "来料检验",
                    "process_function": "确认来料符合图纸要求",
                    "equipment": "检验台",
                },
                {
                    "process_step_id": "P20",
                    "operation": "冲压成形",
                    "process_function": "形成铰链主体形状",
                    "equipment": "压力机",
                },
            ]
        }
        payloads = [
            {
                "rows": [
                    {
                        "pfmea_id": "",
                        "process_step_id": "P10",
                        "process_item": "制造过程",
                        "process_step_name": "",
                        "structure_process_item": "制造过程",
                        "structure_process_step": "",
                        "structure_work_element": "检验台",
                        "work_element_4m": "机",
                        "function_process_item": "制造过程",
                        "function_process_step": "",
                        "function_work_element": "检验台执行来料确认",
                        "failure_effect": "不合格物料流入后续工序",
                        "severity": 7,
                        "failure_mode": "来料状态误判",
                        "failure_cause": "检验标准使用错误",
                        "prevention_control": "检验标准版本确认",
                        "occurrence": 3,
                        "detection_control": "复核检验记录",
                        "detection": 4,
                        "action_priority": "M",
                        "special_characteristics": "无",
                        "preventive_action": "锁定检验标准版本",
                        "detection_action": "抽查记录",
                        "optimization_action": "锁定检验标准版本；抽查记录",
                        "responsible_person": "",
                        "target_date": "",
                        "status": "未开始",
                        "needs_confirmation": True,
                    }
                ]
            },
            {
                "rows": [
                    {
                        "pfmea_id": "",
                        "process_step_id": "P20",
                        "process_item": "制造过程",
                        "process_step_name": "",
                        "structure_process_item": "制造过程",
                        "structure_process_step": "",
                        "structure_work_element": "压力机",
                        "work_element_4m": "机",
                        "function_process_item": "制造过程",
                        "function_process_step": "",
                        "function_work_element": "压力机形成主体形状",
                        "failure_effect": "铰链安装间隙异常",
                        "severity": 8,
                        "failure_mode": "成形尺寸偏差",
                        "failure_cause": "冲压参数漂移",
                        "prevention_control": "首件参数确认",
                        "occurrence": 4,
                        "detection_control": "尺寸巡检",
                        "detection": 5,
                        "action_priority": "M",
                        "special_characteristics": "SC",
                        "preventive_action": "锁定压力机参数",
                        "detection_action": "增加尺寸巡检",
                        "optimization_action": "锁定压力机参数；增加尺寸巡检",
                        "responsible_person": "",
                        "target_date": "",
                        "status": "未开始",
                        "needs_confirmation": True,
                    }
                ]
            },
        ]

        with patch("minos_core.pipeline_chain.OpenAITextGenerator") as generator:
            llm = generator.return_value
            llm.generate_structured.side_effect = payloads

            pfmea = generate_pfmea_from_confirmed_pfd({}, confirmed_pfd)

        self.assertEqual(llm.generate_structured.call_count, 2)
        prompts = [
            call.kwargs["user_prompt"]
            for call in llm.generate_structured.call_args_list
        ]
        self.assertIn("P10", prompts[0])
        self.assertNotIn("P20", prompts[0])
        self.assertIn("P20", prompts[1])
        self.assertNotIn("P10", prompts[1])
        self.assertEqual(
            [row["process_step_id"] for row in pfmea["rows"]],
            ["P10", "P20"],
        )
        self.assertEqual(
            pfmea["metadata"]["pfmea_generation_strategy"],
            "per_pfd_step",
        )

    def test_chain_pfmea_rejects_rows_not_from_confirmed_pfd(self):
        llm_payload = {
            "rows": [
                {
                    "pfmea_id": "PFMEA-P99-01",
                    "process_step_id": "P99",
                    "process_item": "制造过程",
                    "process_step_name": "不存在工序",
                    "work_element_4m": "机",
                    "function_process_step": "不存在",
                    "function_work_element": "不存在",
                    "failure_effect": "影响装配",
                    "severity": 8,
                    "failure_mode": "尺寸偏差",
                    "failure_cause": "参数错误",
                    "prevention_control": "参数确认",
                    "occurrence": 4,
                    "detection_control": "检验",
                    "detection": 5,
                    "action_priority": "M",
                    "special_characteristics": "无",
                    "preventive_action": "",
                    "detection_action": "",
                    "responsible_person": "",
                    "target_date": "",
                    "status": "未开始",
                    "needs_confirmation": True,
                }
            ]
        }

        with patch("minos_core.pipeline_chain.OpenAITextGenerator") as generator:
            generator.return_value.generate_structured.return_value = llm_payload

            with self.assertRaisesRegex(ValueError, "P99"):
                generate_pfmea_from_confirmed_pfd(
                    {},
                    {"steps": [{"process_step_id": "P10", "operation": "冲压安装孔"}]},
                )

    def test_chain_pfmea_rejects_step_request_returning_another_confirmed_step(self):
        confirmed_pfd = {
            "steps": [
                {"process_step_id": "P10", "operation": "来料检验"},
                {"process_step_id": "P20", "operation": "冲压成形"},
            ]
        }
        payloads = [
            {
                "rows": [
                    {
                        "pfmea_id": "PFMEA-P20-01",
                        "process_step_id": "P20",
                        "process_item": "制造过程",
                        "process_step_name": "冲压成形",
                        "work_element_4m": "机",
                        "function_process_step": "形成铰链主体",
                        "function_work_element": "压力机输出",
                        "failure_effect": "影响装配",
                        "severity": 8,
                        "failure_mode": "尺寸偏差",
                        "failure_cause": "参数漂移",
                        "prevention_control": "参数确认",
                        "occurrence": 4,
                        "detection_control": "尺寸检验",
                        "detection": 5,
                        "action_priority": "M",
                        "special_characteristics": "无",
                        "preventive_action": "",
                        "detection_action": "",
                        "responsible_person": "",
                        "target_date": "",
                        "status": "未开始",
                        "needs_confirmation": True,
                    }
                ]
            }
        ]

        with patch("minos_core.pipeline_chain.OpenAITextGenerator") as generator:
            # Parallel execution: both steps call LLM; return the same wrong payload for both
            generator.return_value.generate_structured.return_value = payloads[0]

            with self.assertRaisesRegex(ValueError, "expected P10"):
                generate_pfmea_from_confirmed_pfd({}, confirmed_pfd)

    def test_chain_cp_generates_per_pfmea_row_to_avoid_gateway_timeout(self):
        confirmed_pfd = {
            "steps": [
                {"process_step_id": "P10", "operation": "来料检验"},
                {"process_step_id": "P20", "operation": "冲压成形"},
            ]
        }
        confirmed_pfmea = {
            "rows": [
                {
                    "pfmea_id": "PFMEA-P10-01",
                    "process_step_id": "P10",
                    "process_step_name": "来料检验",
                    "equipment": "检具",
                    "failure_mode": "来料尺寸不符",
                    "failure_cause": "供应商过程波动",
                    "prevention_control": "供应商审核",
                    "detection_control": "来料检验",
                    "action_priority": "H",
                    "special_characteristics": "SC",
                },
                {
                    "pfmea_id": "PFMEA-P20-01",
                    "process_step_id": "P20",
                    "process_step_name": "冲压成形",
                    "equipment": "压力机",
                    "failure_mode": "成形尺寸偏差",
                    "failure_cause": "冲压参数漂移",
                    "prevention_control": "参数点检",
                    "detection_control": "尺寸巡检",
                    "action_priority": "M",
                    "special_characteristics": "无",
                },
            ]
        }
        payloads = [
            {
                "rows": [
                    {
                        "control_plan_id": "CP-P10-01",
                        "process_step_id": "P10",
                        "pfmea_id": "PFMEA-P10-01",
                        "process_name": "来料检验",
                        "equipment": "检具",
                        "characteristic_number": "PFMEA-P10-01",
                        "product_characteristic": "来料尺寸",
                        "process_characteristic": "供应商批次",
                        "special_characteristic_class": "SC",
                        "specification_tolerance": "按图纸要求",
                        "measurement_method": "来料检验",
                        "sample_size": "5 件",
                        "sample_frequency": "每批",
                        "control_method": "供应商审核；来料检验",
                        "process_parameter": "供应商批次追溯",
                        "parameter_specification": "批次状态受控且证书齐全",
                        "process_control_method": "供应商放行清单与批次扫描",
                        "setup_verification": "换批前确认供应商批次和材质证明",
                        "poka_yoke_device": "批次扫码防错",
                        "poka_yoke_verification": "每批首件扫码验证",
                        "process_record": "来料批次追溯记录",
                        "reaction_plan": "隔离批次并通知质量工程师",
                        "needs_confirmation": True,
                    }
                ]
            },
            {
                "rows": [
                    {
                        "control_plan_id": "CP-P20-01",
                        "process_step_id": "P20",
                        "pfmea_id": "PFMEA-P20-01",
                        "process_name": "冲压成形",
                        "equipment": "压力机",
                        "characteristic_number": "PFMEA-P20-01",
                        "product_characteristic": "成形尺寸",
                        "process_characteristic": "冲压参数",
                        "special_characteristic_class": "无",
                        "specification_tolerance": "按图纸要求",
                        "measurement_method": "尺寸巡检",
                        "sample_size": "5 件",
                        "sample_frequency": "每班",
                        "control_method": "参数点检；尺寸巡检",
                        "process_parameter": "冲压力",
                        "parameter_specification": "按作业指导书设定范围",
                        "process_control_method": "参数锁定并每班点检",
                        "setup_verification": "首件确认冲压参数和模具状态",
                        "poka_yoke_device": "压力机参数权限锁",
                        "poka_yoke_verification": "换型后验证参数锁定有效",
                        "process_record": "冲压参数点检表",
                        "reaction_plan": "隔离产品并调整参数",
                        "needs_confirmation": True,
                    }
                ]
            },
        ]

        with patch("minos_core.pipeline_chain.OpenAITextGenerator") as generator:
            llm = generator.return_value
            llm.generate_structured.side_effect = payloads

            cp = generate_cp_from_confirmed_pfmea({}, confirmed_pfd, confirmed_pfmea)

        self.assertEqual(llm.generate_structured.call_count, 2)
        prompts = [call.kwargs["user_prompt"] for call in llm.generate_structured.call_args_list]
        self.assertIn("PFMEA-P10-01", prompts[0])
        self.assertNotIn("PFMEA-P20-01", prompts[0])
        self.assertIn("PFMEA-P20-01", prompts[1])
        self.assertNotIn("PFMEA-P10-01", prompts[1])
        self.assertEqual([row["pfmea_id"] for row in cp["rows"]], ["PFMEA-P10-01", "PFMEA-P20-01"])
        for row in cp["rows"]:
            for field in (
                "process_parameter",
                "parameter_specification",
                "process_control_method",
                "setup_verification",
                "poka_yoke_device",
                "poka_yoke_verification",
                "process_record",
            ):
                self.assertIn(field, row)
                self.assertTrue(row[field])
        self.assertEqual(cp["metadata"]["cp_generation_strategy"], "per_pfmea_row")

    def test_chain_cp_targets_high_severity_and_special_characteristic_rows(self):
        confirmed_pfd = {
            "steps": [
                {"process_step_id": "P10", "operation": "来料检验"},
                {"process_step_id": "P20", "operation": "冲压成形"},
                {"process_step_id": "P30", "operation": "终检"},
            ]
        }
        confirmed_pfmea = {
            "rows": [
                {
                    "pfmea_id": "PFMEA-P10-01",
                    "process_step_id": "P10",
                    "process_step_name": "来料检验",
                    "failure_mode": "来料尺寸不符",
                    "action_priority": "M",
                    "severity": 7,
                    "evidence_refs": ["EV-P10"],
                    "confidence": 0.86,
                    "needs_confirmation": False,
                },
                {
                    "pfmea_id": "PFMEA-P20-01",
                    "process_step_id": "P20",
                    "process_step_name": "冲压成形",
                    "failure_mode": "安全相关尺寸失效",
                    "action_priority": "L",
                    "severity": 9,
                    "evidence_refs": ["EV-P20"],
                    "confidence": 0.81,
                    "needs_confirmation": False,
                },
                {
                    "pfmea_id": "PFMEA-P30-01",
                    "process_step_id": "P30",
                    "process_step_name": "终检",
                    "failure_mode": "特殊特性漏检",
                    "action_priority": "L",
                    "severity": 5,
                    "characteristic_refs": ["SC-HOLE-POS"],
                    "evidence_refs": ["EV-P30"],
                    "confidence": 0.77,
                    "needs_confirmation": False,
                },
            ]
        }

        def payload_for(pfmea_id, step_id, special_class="无"):
            return {
                "rows": [
                    {
                        "control_plan_id": "",
                        "process_step_id": step_id,
                        "pfmea_id": pfmea_id,
                        "process_name": "",
                        "equipment": "",
                        "characteristic_number": "",
                        "product_characteristic": "",
                        "process_characteristic": "",
                        "special_characteristic_class": special_class,
                        "specification_tolerance": "",
                        "process_parameter": "过程参数",
                        "parameter_specification": "参数范围",
                        "process_control_method": "参数点检",
                        "setup_verification": "首件确认",
                        "poka_yoke_device": "防错",
                        "poka_yoke_verification": "每班验证",
                        "process_record": "点检表",
                        "measurement_method": "检验",
                        "sample_size": "5件",
                        "sample_frequency": "每班",
                        "control_method": "过程控制和检验",
                        "reaction_plan": "隔离并通知质量工程师",
                        "needs_confirmation": False,
                    }
                ]
            }

        with patch("minos_core.pipeline_chain.OpenAITextGenerator") as generator:
            llm = generator.return_value
            llm.generate_structured.side_effect = [
                payload_for("PFMEA-P10-01", "P10"),
                payload_for("PFMEA-P20-01", "P20"),
                payload_for("PFMEA-P30-01", "P30", "无"),
            ]

            cp = generate_cp_from_confirmed_pfmea({}, confirmed_pfd, confirmed_pfmea)

        self.assertEqual(llm.generate_structured.call_count, 3)
        self.assertEqual(cp["document_type"], "control_plan")
        self.assertEqual(cp["schema_version"], "minos-core.generated.v1")
        schema_items = (
            llm.generate_structured.call_args_list[0]
            .kwargs["response_format"]["json_schema"]["schema"]["properties"]["rows"]["items"]
        )
        for field in (
            "evidence_refs",
            "confidence",
            "ai_inferred",
            "needs_confirmation",
            "characteristic_refs",
        ):
            self.assertIn(field, schema_items["properties"])
            self.assertIn(field, schema_items["required"])
        self.assertIn("evidence_refs", llm.generate_structured.call_args_list[0].kwargs["system_prompt"])
        self.assertIn("confidence", llm.generate_structured.call_args_list[0].kwargs["system_prompt"])
        self.assertEqual(
            [row["pfmea_id"] for row in cp["rows"]],
            ["PFMEA-P10-01", "PFMEA-P20-01", "PFMEA-P30-01"],
        )
        special_row = cp["rows"][2]
        self.assertEqual(special_row["special_characteristic_class"], "SC")
        self.assertEqual(special_row["characteristic_refs"], ["SC-HOLE-POS"])
        self.assertEqual(special_row["evidence_refs"], ["EV-P30"])
        self.assertAlmostEqual(special_row["confidence"], 0.77)
        self.assertTrue(special_row["ai_inferred"])
        self.assertFalse(special_row["needs_confirmation"])

    def test_control_plan_generation_outputs_process_controls_not_only_result_checks(self):
        pfmea_bundle = {
            "document_type": "pfmea",
            "rows": [
                {
                    "pfmea_id": "PFMEA-P20-01",
                    "process_step_id": "P20",
                    "process_step_name": "冲压成形",
                    "equipment": "压力机",
                    "process_characteristic": "冲压力",
                    "failure_mode": "成形尺寸偏差",
                    "failure_cause": "冲压参数漂移",
                    "prevention_control": "换型后参数点检并锁定",
                    "detection_control": "尺寸巡检",
                    "action_priority": "H",
                    "severity": 8,
                    "occurrence": 6,
                    "detection": 5,
                }
            ],
        }

        cp = generate_control_plan_from_pfmea(pfmea_bundle)

        row = cp["rows"][0]
        self.assertEqual(row["process_parameter"], "冲压力")
        self.assertIn("冲压参数漂移", row["parameter_specification"])
        self.assertIn("换型后参数点检并锁定", row["process_control_method"])
        self.assertIn("首件", row["setup_verification"])
        self.assertTrue(row["poka_yoke_device"])
        self.assertTrue(row["poka_yoke_verification"])
        self.assertTrue(row["process_record"])

    def test_control_plan_generation_inherits_pfmea_cause_process_parameter(self):
        pfmea_bundle = {
            "document_type": "pfmea",
            "rows": [
                {
                    "pfmea_id": "PFMEA-P20-01",
                    "process_step_id": "P20",
                    "process_step_name": "冲压成形",
                    "equipment": "压力机",
                    "cause_process_parameter": "冲压力",
                    "failure_mode": "成形尺寸偏差",
                    "failure_cause": "压力不足导致成形不到位",
                    "prevention_control": "锁定压力机参数",
                    "detection_control": "尺寸巡检",
                    "action_priority": "H",
                    "severity": 8,
                    "occurrence": 6,
                    "detection": 5,
                }
            ],
        }

        cp = generate_control_plan_from_pfmea(pfmea_bundle)

        row = cp["rows"][0]
        self.assertEqual(row["process_parameter"], "冲压力")
        self.assertIn("压力不足导致成形不到位", row["parameter_specification"])

    def test_chain_cp_rejects_row_request_returning_another_pfmea(self):
        confirmed_pfd = {"steps": [{"process_step_id": "P10", "operation": "来料检验"}]}
        confirmed_pfmea = {
            "rows": [
                {
                    "pfmea_id": "PFMEA-P10-01",
                    "process_step_id": "P10",
                    "process_step_name": "来料检验",
                    "failure_mode": "来料尺寸不符",
                    "action_priority": "H",
                },
                {
                    "pfmea_id": "PFMEA-P10-02",
                    "process_step_id": "P10",
                    "process_step_name": "来料检验",
                    "failure_mode": "标签错误",
                    "action_priority": "M",
                },
            ]
        }
        llm_payload = {
            "rows": [
                {
                    "control_plan_id": "CP-P10-02",
                    "process_step_id": "P10",
                    "pfmea_id": "PFMEA-P10-02",
                    "process_name": "来料检验",
                    "equipment": "检具",
                    "characteristic_number": "PFMEA-P10-02",
                    "product_characteristic": "标签",
                    "process_characteristic": "来料批次",
                    "special_characteristic_class": "无",
                    "specification_tolerance": "按包装规范",
                    "measurement_method": "目视检查",
                    "sample_size": "5 件",
                    "sample_frequency": "每批",
                    "control_method": "标签核对",
                    "reaction_plan": "隔离并更换标签",
                    "needs_confirmation": True,
                }
            ]
        }

        with patch("minos_core.pipeline_chain.OpenAITextGenerator") as generator:
            generator.return_value.generate_structured.return_value = llm_payload

            with self.assertRaisesRegex(ValueError, "expected PFMEA-P10-01"):
                generate_cp_from_confirmed_pfmea({}, confirmed_pfd, confirmed_pfmea)

    def test_normalize_pfmea_rows_outputs_aiag_vda_form_c_fields(self):
        rows = [
            {
                "pfmea_id": "PFMEA-P10-01",
                "process_step_id": "P10",
                "operation": "冲压成形",
                "process_function": "形成安装面",
                "equipment": "压力机",
                "process_characteristics": "冲压力",
                "failure_mode": "安装面变形",
                "failure_effect": "装配间隙不满足要求",
                "failure_cause": "压力机参数不稳定",
                "severity": 8,
                "occurrence": 5,
                "detection": 6,
                "prevention_control": "锁定压力机参数",
                "detection_control": "首件和巡检测量安装面",
                "special_characteristics": ["SC-1"],
            }
        ]

        normalize_pfmea_rows(
            rows,
            process_steps=[
                {
                    "process_step_id": "P10",
                    "operation": "冲压成形",
                    "process_function": "形成安装面",
                    "equipment": "压力机",
                    "process_characteristics": "冲压力",
                }
            ],
        )

        row = rows[0]
        for field in (
            "process_item",
            "process_step",
            "process_work_element",
            "structure_process_item",
            "structure_process_step",
            "structure_work_element",
            "function_process_item",
            "function_process_step",
            "function_work_element",
            "failure_effect",
            "failure_mode",
            "failure_cause",
            "prevention_control",
            "detection_control",
            "cause_process_parameter",
            "prevention_control_target",
            "prevention_control_timing",
            "detection_control_target",
            "detection_control_timing",
            "control_logic_review",
            "severity",
            "occurrence",
            "detection",
            "action_priority",
            "optimization_action",
            "responsible_person",
            "target_date",
            "status",
            "needs_confirmation",
            "S",
            "O",
            "D",
            "AP",
        ):
            self.assertIn(field, row)
        self.assertEqual(row["process_item"], "制造过程")
        self.assertEqual(row["process_step"], "冲压成形")
        self.assertEqual(row["process_work_element"], "压力机")
        self.assertEqual(row["structure_process_item"], "制造过程")
        self.assertEqual(row["structure_process_step"], "冲压成形")
        self.assertEqual(row["structure_work_element"], "压力机")
        self.assertEqual(row["function_process_item"], "制造过程")
        self.assertEqual(row["function_process_step"], "形成安装面")
        self.assertEqual(row["function_work_element"], "冲压力")
        self.assertEqual(row["cause_process_parameter"], "冲压力")
        self.assertIn("压力机参数不稳定", row["prevention_control_target"])
        self.assertTrue(row["prevention_control_timing"])
        self.assertIn("安装面", row["detection_control_target"])
        self.assertIn("首件", row["detection_control_timing"])
        self.assertIn("预防", row["control_logic_review"])
        self.assertEqual(row["AP"], row["action_priority"])
        self.assertIn(row["action_priority"], {"H", "M", "L"})
        self.assertNotIn("rpn", row)
        self.assertNotIn("after_rpn", row)
        self.assertIsInstance(row["needs_confirmation"], bool)

    def test_normalize_control_plan_rows_outputs_cp_2024_fields(self):
        rows = [
            {
                "control_plan_id": "CP-P10-01",
                "process_step_id": "P10",
                "pfmea_id": "PFMEA-P10-01",
                "process_name": "冲压成形",
                "product_process_characteristic": "安装面高度",
                "specification": "10.0 +/- 0.2 mm",
                "measurement_method": "高度规",
                "sample_size": "5 件",
                "sample_frequency": "每批",
                "control_method": "首件检验",
                "reaction_plan": "隔离并调整参数",
            }
        ]

        normalize_control_plan_rows(rows)

        row = rows[0]
        for field in (
            "control_plan_id",
            "process_step_id",
            "pfmea_id",
            "process_name",
            "equipment",
            "characteristic_number",
            "product_characteristic",
            "process_characteristic",
            "special_characteristic_class",
            "specification_tolerance",
            "measurement_method",
            "sample_size",
            "sample_frequency",
            "control_method",
                "reaction_plan",
                "process_parameter",
                "parameter_specification",
                "process_control_method",
                "setup_verification",
                "poka_yoke_device",
                "poka_yoke_verification",
                "process_record",
                "needs_confirmation",
            ):
                self.assertIn(field, row)
        self.assertEqual(row["product_characteristic"], "安装面高度")
        self.assertEqual(row["specification_tolerance"], "10.0 +/- 0.2 mm")
        self.assertIsInstance(row["needs_confirmation"], bool)

    def test_control_plan_generation_prefers_standard_pfmea_fields(self):
        pfmea_bundle = {
            "document_type": "pfmea",
            "rows": [
                {
                    "pfmea_id": "PFMEA-P10-01",
                    "process_step_id": "P10",
                    "process_step": "旧工序名",
                    "failure_mode": "孔位偏移",
                    "severity": 8,
                    "occurrence": 4,
                    "detection": 5,
                    "action_priority": "M",
                    "product_process_characteristic": "旧合并特性",
                    "product_characteristic": "标准产品特性",
                    "process_characteristic": "标准过程特性",
                    "specification": "旧规格",
                    "specification_tolerance": "标准规格公差",
                    "classification": "旧分类",
                    "special_characteristic_class": "标准特殊分类",
                }
            ],
        }

        cp = generate_control_plan_from_pfmea(pfmea_bundle)

        row = cp["rows"][0]
        self.assertEqual(row["product_characteristic"], "标准产品特性")
        self.assertEqual(row["process_characteristic"], "标准过程特性")
        self.assertEqual(row["product_process_characteristic"], "标准产品特性")
        self.assertEqual(row["specification_tolerance"], "标准规格公差")
        self.assertEqual(row["specification"], "标准规格公差")
        self.assertEqual(row["special_characteristic_class"], "标准特殊分类")
        self.assertNotIn("classification", row)

    def test_pfmea_ai_risk_inference_uses_step_context_and_confirmation_rules(self):
        pfd = {
            "document_type": "process_flow",
            "schema_version": "minos-core.generated.v1",
            "product": {"part_name": "Demo Part"},
            "evidence": [{"evidence_id": "EV-1"}],
            "steps": [
                {
                    "process_step_id": "P10",
                    "operation": "Blanking",
                    "process_function": "Create blank profile",
                    "confidence": 0.88,
                    "evidence_refs": ["EV-1"],
                },
                {
                    "process_step_id": "P20",
                    "operation": "Piercing",
                    "process_function": "Create mounting holes",
                    "special_characteristics": ["SC-HOLE-POS"],
                    "confidence": 0.83,
                    "evidence_refs": ["EV-1"],
                },
                {
                    "process_step_id": "P30",
                    "operation": "Final inspection",
                    "process_function": "Verify finished part",
                    "confidence": 0.62,
                    "evidence_refs": ["EV-1"],
                },
            ],
            "links": [],
        }

        pfmea = infer_pfmea_from_process_flow(pfd)
        rows_by_step_dict = rows_by_step(pfmea["rows"])

        for step_id in ("P10", "P20", "P30"):
            self.assertGreaterEqual(len(rows_by_step_dict[step_id]), 2)
            failure_modes = [row["failure_mode"] for row in rows_by_step_dict[step_id]]
            self.assertEqual(len(failure_modes), len(set(failure_modes)))
        for row in pfmea["rows"]:
            assert_pfmea_ai_risk_row(self, row)
            self.assertEqual(row["S"], row["severity"])
            self.assertEqual(row["O"], row["occurrence"])
            self.assertEqual(row["D"], row["detection"])
            self.assertEqual(row["AP"], row["action_priority"])
        self.assertTrue(any("毛坯" in row["failure_mode"] for row in rows_by_step_dict["P10"]))
        self.assertTrue(any("孔" in row["failure_mode"] for row in rows_by_step_dict["P20"]))
        self.assertTrue(any(row["AP"] == "H" for row in rows_by_step_dict["P20"]))
        self.assertTrue(all(row["needs_confirmation"] for row in rows_by_step_dict["P20"]))
        self.assertTrue(all(row["needs_confirmation"] for row in rows_by_step_dict["P30"]))
        self.assertTrue(any(not row["needs_confirmation"] for row in rows_by_step_dict["P10"]))



if __name__ == "__main__":
    unittest.main()
