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
from minos_core.pipeline_chain import generate_pfd_from_drawing, generate_pfmea_from_confirmed_pfd
from minos_core.cli import main
from minos_core.schemas import validate_bundle_schema


class AIDrawingThreeTableWorkflowTests(unittest.TestCase):
    def test_png_drawing_becomes_page_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = self._write_png(Path(tmpdir) / "drawing.png")

            source = load_drawing_source(image_path)
            pages = render_drawing_pages(source)

            self.assertEqual(source.file_type, "png")
            self.assertEqual(len(pages), 1)
            self.assertEqual(pages[0].evidence_id, "drawing_page_001")
            self.assertEqual(pages[0].width, 100)
            self.assertEqual(pages[0].height, 80)
            self.assertTrue(pages[0].sha256)

    def test_missing_or_broken_drawing_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(FileNotFoundError):
                load_drawing_source(Path(tmpdir) / "missing.png")

            bad = Path(tmpdir) / "bad.png"
            bad.write_text("not an image", encoding="utf-8")
            source = load_drawing_source(bad)
            with self.assertRaisesRegex(DrawingInputError, "cannot be opened"):
                render_drawing_pages(source)

    def test_pdf_without_renderer_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf = Path(tmpdir) / "drawing.pdf"
            pdf.write_bytes(b"%PDF-1.4\n%%EOF")
            source = load_drawing_source(pdf)
            try:
                import fitz  # type: ignore[import-not-found]  # noqa: F401
            except ImportError:
                with self.assertRaisesRegex(DrawingInputError, "PDF rendering requires PyMuPDF"):
                    render_drawing_pages(source, Path(tmpdir) / "pages")
            else:
                with self.assertRaisesRegex(DrawingInputError, "PDF rendering failed"):
                    render_drawing_pages(source, Path(tmpdir) / "pages")

    def test_fake_multimodal_adapter_returns_valid_drawing_analysis_bundle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_drawing_pages(load_drawing_source(self._write_png(Path(tmpdir) / "drawing.png")))
            bundle = analyze_drawing_pages(
                pages,
                FakeMultimodalDrawingAnalyzer(json.dumps(self._analysis_payload())),
                {"part_family": "hinge"},
            )

            self.assertTrue(validate_bundle_schema(bundle, "drawing_analysis_bundle"))
            self.assertEqual(bundle["drawing_identity"]["part_name"], "Hinge Bracket")
            gate = evaluate_drawing_recognition_gate(bundle)
            self.assertTrue(gate.can_continue)
            self.assertFalse(gate.allow_user_export)
            self.assertTrue(gate.needs_human_review)

    def test_invalid_ai_json_and_non_page_unknown_evidence_refs_fail(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_drawing_pages(load_drawing_source(self._write_png(Path(tmpdir) / "drawing.png")))

            with self.assertRaisesRegex(DrawingAnalysisError, "invalid JSON"):
                analyze_drawing_pages(pages, FakeMultimodalDrawingAnalyzer("{bad"))

            payload = self._analysis_payload()
            payload["materials"][0]["evidence_refs"] = ["missing"]
            with self.assertRaisesRegex(DrawingAnalysisError, "unknown evidence"):
                analyze_drawing_pages(
                    pages,
                    FakeMultimodalDrawingAnalyzer(json.dumps(payload)),
                )

    def test_unknown_single_page_drawing_ref_is_repaired_for_manual_review(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_drawing_pages(load_drawing_source(self._write_png(Path(tmpdir) / "drawing.png")))
            payload = self._analysis_payload()
            payload["materials"][0]["evidence_refs"] = ["drawing_page_003"]

            bundle = analyze_drawing_pages(
                pages,
                FakeMultimodalDrawingAnalyzer(json.dumps(payload)),
            )
            material = bundle["materials"][0]
            gate = evaluate_drawing_recognition_gate(bundle)

            self.assertEqual(material["evidence_refs"], ["drawing_page_001"])
            self.assertEqual(material["original_evidence_refs"], ["drawing_page_003"])
            self.assertTrue(material["needs_confirmation"])
            self.assertIn("evidence_ref_repairs", material)
            self.assertIn("evidence_ref_repairs", bundle["metadata"])
            self.assertTrue(gate.can_continue)
            self.assertTrue(gate.needs_human_review)
            self.assertFalse(gate.missing_evidence_refs)
            self.assertTrue(
                any(
                    getattr(item, "category", "") == "drawing_evidence_ref_repaired"
                    for item in gate.manual_review_items
                )
            )

    def test_invalid_confidence_is_traceable_in_drawing_gate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_drawing_pages(load_drawing_source(self._write_png(Path(tmpdir) / "drawing.png")))
            payload = self._analysis_payload()
            payload["materials"][0]["confidence"] = "not-a-number"

            bundle = analyze_drawing_pages(
                pages,
                FakeMultimodalDrawingAnalyzer(json.dumps(payload)),
            )
            gate = evaluate_drawing_recognition_gate(bundle)

            self.assertTrue(bundle["materials"][0]["needs_confirmation"])
            self.assertIn("confidence_parse_errors", bundle["materials"][0])
            self.assertTrue(gate.evidence_coverage["confidence_parse_error_items"])
            self.assertTrue(
                any(
                    getattr(item, "category", "") == "drawing_confidence_parse_error"
                    for item in gate.manual_review_items
                )
            )

    def test_drawing_to_pfd_to_pfmea_to_cp_and_excel_exports(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_drawing_pages(load_drawing_source(self._write_png(Path(tmpdir) / "drawing.png")))
            drawing_bundle = analyze_drawing_pages(
                pages,
                FakeMultimodalDrawingAnalyzer(json.dumps(self._analysis_payload())),
            )

            pfd = infer_process_flow_from_drawing(drawing_bundle)
            operations = [step["operation"] for step in pfd["steps"]]
            self.assertEqual(operations[:2], ["来料检验", "材料准备"])
            self.assertIn("落料", operations)
            self.assertIn("冲孔", operations)
            self.assertIn("表面处理", operations)
            self.assertEqual(operations[-3:], ["过程检验", "最终检验", "包装"])
            self.assertTrue(all(step["evidence_refs"] for step in pfd["steps"]))

            pfmea = infer_pfmea_from_process_flow(pfd)
            rows_by_step = _rows_by_step(pfmea["rows"])
            self.assertEqual(set(rows_by_step), {step["process_step_id"] for step in pfd["steps"]})
            for step_rows in rows_by_step.values():
                self.assertGreaterEqual(len(step_rows), 2)
                failure_modes = [row["failure_mode"] for row in step_rows]
                self.assertEqual(len(failure_modes), len(set(failure_modes)))
            self.assertTrue(any(not row["needs_confirmation"] for row in pfmea["rows"]))
            piercing_step_id = next(step["process_step_id"] for step in pfd["steps"] if step["operation"] == "冲孔")
            self.assertTrue(all(row["needs_confirmation"] for row in rows_by_step[piercing_step_id]))
            for row in pfmea["rows"]:
                _assert_pfmea_ai_risk_row(self, row)

            cp = generate_control_plan_from_pfmea(pfmea)
            self.assertEqual(len(cp["rows"]), len(pfmea["rows"]))
            self.assertTrue(all(row["pfmea_id"] for row in cp["rows"]))
            self.assertTrue(all(row["specification"] for row in cp["rows"]))
            self.assertTrue(all(row["measurement_method"] for row in cp["rows"]))
            self.assertTrue(all(row["sample_size"] for row in cp["rows"]))
            self.assertTrue(all(row["sample_frequency"] for row in cp["rows"]))
            self.assertTrue(all(row["control_method"] for row in cp["rows"]))
            self.assertTrue(all(row["reaction_plan"] for row in cp["rows"]))
            self.assertTrue(all(row["ai_inferred"] for row in cp["rows"]))
            self.assertTrue(all(row["ai_reasoning"] for row in cp["rows"]))

            chain = {
                "document_type": "apqp_chain",
                "schema_version": "minos-core.generated.v1",
                "product": pfd["product"],
                "drawings": pfd["drawings"],
                "characteristics": pfd["characteristics"],
                "process_steps": pfd["steps"],
                "failure_modes": pfmea["rows"],
                "controls": cp["rows"],
                "evidence": drawing_bundle["evidence"],
                "links": pfd["links"],
                "pending_fields": [],
                "ai_inferred_items": pfd["ai_inferred_items"] + pfmea["ai_inferred_items"],
            }
            unified = export_three_table_workbook(
                chain,
                Path(tmpdir) / "三表总工作簿.xlsx",
                export_mode="draft",
                require_gate=False,
            )
            split = export_split_three_table_workbooks(chain, Path(tmpdir) / "split")

            self._assert_xlsx(unified)
            unified_text = self._xlsx_text(unified)
            self.assertIn("DRAFT_ONLY", self._sheet_names(unified))
            self.assertIn("draft_only", unified_text)
            self.assertIn("not for customer submission", unified_text)
            self.assertEqual(set(split), {"process_flow", "pfmea", "control_plan"})
            for path in split.values():
                self._assert_xlsx(path)
                text = self._xlsx_text(path)
                self.assertIn("draft_only", text)
                self.assertIn("requires_engineering_review", text)
                self.assertIn("not for customer submission", text)

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
                    "rpn": 160,
                    "action_priority": "M",
                    "special_characteristics": "SC",
                    "preventive_action": "",
                    "detection_action": "",
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
            generator.return_value.generate_structured.return_value = llm_payload

            pfmea = generate_pfmea_from_confirmed_pfd({}, confirmed_pfd)

        row = pfmea["rows"][0]
        self.assertEqual(row["process_step_id"], "P10")
        self.assertEqual(row["operation"], "冲压安装孔")
        self.assertEqual(row["process_step"], "冲压安装孔")
        self.assertEqual(row["process_step_name"], "冲压安装孔")
        self.assertEqual(row["structure_process_step"], "冲压安装孔")
        self.assertEqual(row["function_process_step"], "形成安装孔位置")
        self.assertEqual(row["function_requirement"], "形成安装孔位置")
        self.assertEqual(row["pfmea_id"], "PFMEA-P10-01")

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
                    "rpn": 160,
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

    def test_normalize_pfmea_rows_outputs_aiag_vda_form_c_fields(self):
        rows = [
            {
                "pfmea_id": "PFMEA-P10-01",
                "process_step_id": "P10",
                "operation": "冲压成形",
                "process_function": "形成安装面",
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

        normalize_pfmea_rows(rows, process_steps=[{"process_step_id": "P10", "operation": "冲压成形"}])

        row = rows[0]
        for field in (
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
            "severity",
            "occurrence",
            "detection",
            "action_priority",
            "optimization_action",
            "responsible_person",
            "target_date",
            "status",
            "needs_confirmation",
        ):
            self.assertIn(field, row)
        self.assertEqual(row["structure_process_step"], "冲压成形")
        self.assertEqual(row["function_process_step"], "形成安装面")
        self.assertIn(row["action_priority"], {"H", "M", "L"})
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
        self.assertEqual(row["classification"], "标准特殊分类")

    def test_three_table_exports_include_standard_pfmea_and_cp_columns(self):
        chain = {
            "process_steps": [
                {
                    "process_step_id": "P10",
                    "operation": "PFD 工序",
                    "process_function": "PFD 功能",
                }
            ],
            "failure_modes": [
                {
                    "pfmea_id": "PFMEA-P10-01",
                    "process_step_id": "P10",
                    "structure_process_item": "标准结构过程项",
                    "structure_process_step": "标准结构过程步骤",
                    "structure_work_element": "标准结构工作要素",
                    "function_process_item": "标准功能过程项",
                    "function_process_step": "标准功能过程步骤",
                    "function_work_element": "标准功能工作要素",
                    "process_item": "旧过程项",
                    "process_step": "旧过程步骤",
                    "process_work_element": "旧工作要素",
                    "function_requirement": "旧功能要求",
                    "failure_mode": "失效模式",
                    "failure_effect": "失效后果",
                    "failure_cause": "失效原因",
                    "severity": 7,
                    "occurrence": 4,
                    "detection": 5,
                    "action_priority": "M",
                    "optimization_action": "标准优化措施",
                    "recommended_action": "旧推荐措施",
                    "responsible_person": "标准责任人",
                    "responsibility": "旧责任人",
                    "status": "标准状态",
                    "action_status": "旧状态",
                }
            ],
            "controls": [
                {
                    "control_plan_id": "CP-P10-01",
                    "process_step_id": "P10",
                    "pfmea_id": "PFMEA-P10-01",
                    "process_name": "标准工序名称",
                    "equipment": "标准设备",
                    "characteristic_number": "CH-01",
                    "product_characteristic": "标准产品特性",
                    "process_characteristic": "标准过程特性",
                    "special_characteristic_class": "标准特殊分类",
                    "specification_tolerance": "标准规格公差",
                    "product_process_characteristic": "旧合并特性",
                    "specification": "旧规格",
                    "classification": "旧分类",
                    "measurement_method": "测量方法",
                    "sample_frequency": "每批",
                    "control_method": "控制方法",
                    "reaction_plan": "反应计划",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            unified = export_three_table_workbook(
                chain,
                Path(tmpdir) / "三表总工作簿.xlsx",
                export_mode="draft",
                require_gate=False,
            )
            split = export_split_three_table_workbooks(chain, Path(tmpdir) / "split")

            unified_text = self._xlsx_text(unified)
            split_pfmea_text = self._xlsx_text(split["pfmea"])
            split_cp_text = self._xlsx_text(split["control_plan"])

        for text in (unified_text, split_pfmea_text):
            self.assertIn("结构过程项", text)
            self.assertIn("功能过程项", text)
            self.assertIn("功能工作要素", text)
            self.assertIn("标准结构过程项", text)
            self.assertIn("标准功能过程项", text)
            self.assertIn("标准功能工作要素", text)
            self.assertIn("标准优化措施", text)
            self.assertIn("标准责任人", text)
            self.assertIn("标准状态", text)
            self.assertNotIn("旧过程项", text)
            self.assertNotIn("旧推荐措施", text)
        for text in (unified_text, split_cp_text):
            self.assertIn("特性编号", text)
            self.assertIn("产品特性", text)
            self.assertIn("过程特性", text)
            self.assertIn("特殊特性分类", text)
            self.assertIn("规格和公差", text)
            self.assertIn("标准设备", text)
            self.assertIn("CH-01", text)
            self.assertIn("标准产品特性", text)
            self.assertIn("标准过程特性", text)
            self.assertIn("标准特殊分类", text)
            self.assertIn("标准规格公差", text)
            self.assertNotIn("旧合并特性", text)
            self.assertNotIn("旧规格", text)

    def test_generated_three_table_user_content_is_chinese(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_drawing_pages(load_drawing_source(self._write_png(Path(tmpdir) / "drawing.png")))
            drawing_bundle = analyze_drawing_pages(
                pages,
                FakeMultimodalDrawingAnalyzer(json.dumps(self._analysis_payload())),
            )

            pfd = infer_process_flow_from_drawing(drawing_bundle)
            pfmea = infer_pfmea_from_process_flow(pfd)
            cp = generate_control_plan_from_pfmea(pfmea)

        pfd_text = json.dumps(pfd["steps"], ensure_ascii=False)
        pfmea_text = json.dumps(pfmea["rows"], ensure_ascii=False)
        cp_text = json.dumps(cp["rows"], ensure_ascii=False)

        self.assertIn("来料检验", pfd_text)
        self.assertIn("材料准备", pfd_text)
        self.assertIn("过程检验", pfd_text)
        self.assertNotIn("incoming inspection", pfd_text.lower())
        self.assertNotIn("material preparation", pfd_text.lower())
        self.assertIn("未达成", pfmea_text)
        self.assertIn("证据引用", pfmea_text)
        self.assertNotIn("not achieved", pfmea_text.lower())
        self.assertNotIn("inferred from", pfmea_text.lower())
        self.assertIn("草案控制意图", cp_text)
        self.assertIn("控制计划行来源于", cp_text)
        self.assertNotIn("Draft control intent", cp_text)
        self.assertNotIn("Control plan row derived", cp_text)

    def test_drawing_to_pfd_accepts_nested_ai_fields_and_process_step_clues(self):
        bundle = {
            "drawing_identity": {
                "part_name": {"value": "DEMO BRACKET", "confidence": 0.99, "evidence_refs": ["drawing_page_001"]},
                "drawing_number": {"value": "MINOS-DEMO-001", "confidence": 0.99, "evidence_refs": ["drawing_page_001"]},
                "revision": {"value": "A", "confidence": 0.99, "evidence_refs": ["drawing_page_001"]},
            },
            "special_characteristics": [
                {
                    "id": "SC-01",
                    "description": "hole position",
                    "classification": "special characteristic",
                    "evidence_refs": ["drawing_page_001"],
                }
            ],
            "manufacturing_clues": [
                {
                    "process_step": "blanking",
                    "sequence": 1,
                    "confidence": 0.99,
                    "evidence_refs": ["drawing_page_001"],
                },
                {
                    "process_step": "piercing",
                    "sequence": 2,
                    "confidence": 0.99,
                    "special_characteristics": ["SC-01"],
                    "evidence_refs": ["drawing_page_001"],
                },
            ],
            "evidence": [
                {
                    "evidence_id": "drawing_page_001",
                    "source": "drawing_page",
                }
            ],
        }

        pfd = infer_process_flow_from_drawing(bundle)

        operations = [step["operation"] for step in pfd["steps"]]
        self.assertEqual(operations[:2], ["来料检验", "材料准备"])
        self.assertIn("落料", operations)
        self.assertIn("冲孔", operations)
        self.assertEqual(operations[-3:], ["过程检验", "最终检验", "包装"])
        library_steps = [step for step in pfd["steps"] if step["source"] == "process_library"]
        self.assertTrue(library_steps)
        self.assertTrue(all(step["ai_inferred"] for step in library_steps))
        self.assertTrue(all(step["needs_confirmation"] for step in library_steps))
        self.assertTrue(all(step["evidence_refs"] == ["drawing_page_001"] for step in library_steps))
        self.assertEqual(pfd["product"]["part_name"], "DEMO BRACKET")
        self.assertEqual(pfd["drawings"][0]["drawing_id"], "MINOS-DEMO-001")
        self.assertEqual(pfd["drawings"][0]["source_ref"], "drawing_page_001")
        self.assertEqual(pfd["characteristics"][0]["characteristic_id"], "SC-01")
        self.assertEqual(pfd["links"][0]["from"], "P10")
        self.assertEqual(pfd["links"][0]["to"], "P20")

    def test_drawing_analysis_gate_accepts_nested_evidence_and_sequence_clues(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages = render_drawing_pages(
                load_drawing_source(self._write_png(Path(tmpdir) / "drawing.png"))
            )
            payload = {
                "drawing_identity": {
                    "part_name": {"value": "DEMO BRACKET", "evidence_refs": ["drawing_page_001"]},
                    "drawing_number": {"value": "MINOS-DEMO-001", "evidence_refs": ["drawing_page_001"]},
                    "revision": {"value": "A", "evidence_refs": ["drawing_page_001"]},
                },
                "materials": [
                    {
                        "material_spec": {
                            "value": "SPCC-SD",
                            "confidence": 0.96,
                            "evidence_refs": ["drawing_page_001"],
                        },
                        "thickness": {
                            "value": 1.6,
                            "confidence": 0.96,
                            "evidence_refs": ["drawing_page_001"],
                        },
                    }
                ],
                "surface_treatments": [],
                "dimensions": [],
                "tolerances": [],
                "special_characteristics": [],
                "technical_requirements": [],
                "inspection_requirements": [],
                "manufacturing_clues": [
                    {
                        "process_sequence": ["blanking", "piercing", "deburr"],
                        "source_text": "blanking -> piercing -> deburr",
                        "confidence": 0.95,
                        "evidence_refs": ["drawing_page_001"],
                    }
                ],
                "uncertainties": [],
            }

            bundle = analyze_drawing_pages(
                pages,
                FakeMultimodalDrawingAnalyzer(json.dumps(payload)),
            )

        gate = evaluate_drawing_recognition_gate(bundle)
        pfd = infer_process_flow_from_drawing(bundle)
        operations = [step["operation"] for step in pfd["steps"]]
        self.assertTrue(gate.can_continue)
        self.assertFalse(gate.missing_evidence_refs)
        self.assertEqual(operations[:2], ["来料检验", "材料准备"])
        self.assertIn("落料", operations)
        self.assertIn("冲孔", operations)
        self.assertIn("去毛刺", operations)
        self.assertEqual(operations[-3:], ["过程检验", "最终检验", "包装"])

    def test_drawing_to_pfd_can_infer_steps_from_free_text_manufacturing_clue(self):
        bundle = {
            "drawing_identity": {
                "part_name": {"value": "DEMO PANEL", "evidence_refs": ["drawing_page_001"]},
                "drawing_number": {"value": "PANEL-001", "evidence_refs": ["drawing_page_001"]},
                "revision": {"value": "A", "evidence_refs": ["drawing_page_001"]},
            },
            "special_characteristics": [],
            "manufacturing_clues": [
                {
                    "clue": "Likely injection molded part due to uniform thin wall and ribbing",
                    "confidence": 0.9,
                    "evidence_refs": ["drawing_page_001"],
                }
            ],
            "evidence": [{"evidence_id": "drawing_page_001", "source": "drawing_page"}],
        }

        pfd = infer_process_flow_from_drawing(bundle)

        operations = [step["operation"] for step in pfd["steps"]]
        self.assertEqual(operations[:2], ["来料检验", "材料准备"])
        self.assertIn("注塑", operations)
        self.assertIn("修边", operations)
        self.assertEqual(operations[-3:], ["过程检验", "最终检验", "包装"])
        self.assertTrue(all(step["needs_confirmation"] for step in pfd["steps"]))

    def test_drawing_to_pfd_adds_common_sheet_metal_process_library_steps(self):
        bundle = {
            "drawing_identity": {
                "part_name": {"value": "DEMO STAMPING", "evidence_refs": ["drawing_page_001"]},
                "drawing_number": {"value": "STAMP-001", "evidence_refs": ["drawing_page_001"]},
                "revision": {"value": "A", "evidence_refs": ["drawing_page_001"]},
            },
            "materials": [{"name": "sheet metal SPCC", "evidence_refs": ["drawing_page_001"]}],
            "surface_treatments": [{"name": "zinc plating", "evidence_refs": ["drawing_page_001"]}],
            "technical_requirements": [{"text": "No burrs, clean before plating", "evidence_refs": ["drawing_page_001"]}],
            "special_characteristics": [],
            "manufacturing_clues": [
                {
                    "clue": "Likely stamping sheet metal part",
                    "confidence": 0.9,
                    "evidence_refs": ["drawing_page_001"],
                }
            ],
            "evidence": [{"evidence_id": "drawing_page_001", "source": "drawing_page"}],
        }

        pfd = infer_process_flow_from_drawing(bundle)
        operations = [step["operation"] for step in pfd["steps"]]

        self.assertEqual(operations[:2], ["来料检验", "材料准备"])
        for expected in ("落料", "成形", "去毛刺", "清洗", "表面处理"):
            self.assertIn(expected, operations)
        self.assertEqual(operations[-3:], ["过程检验", "最终检验", "包装"])
        for step in pfd["steps"]:
            if step["source"] == "process_library":
                self.assertTrue(step["ai_inferred"])
                self.assertTrue(step["needs_confirmation"])
                self.assertEqual(step["evidence_refs"], ["drawing_page_001"])

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
        rows_by_step = _rows_by_step(pfmea["rows"])

        for step_id in ("P10", "P20", "P30"):
            self.assertGreaterEqual(len(rows_by_step[step_id]), 2)
            failure_modes = [row["failure_mode"] for row in rows_by_step[step_id]]
            self.assertEqual(len(failure_modes), len(set(failure_modes)))
        for row in pfmea["rows"]:
            _assert_pfmea_ai_risk_row(self, row)
            self.assertEqual(row["S"], row["severity"])
            self.assertEqual(row["O"], row["occurrence"])
            self.assertEqual(row["D"], row["detection"])
            self.assertEqual(row["AP"], row["action_priority"])
        self.assertTrue(any("毛坯" in row["failure_mode"] for row in rows_by_step["P10"]))
        self.assertTrue(any("孔" in row["failure_mode"] for row in rows_by_step["P20"]))
        self.assertTrue(any(row["AP"] == "H" for row in rows_by_step["P20"]))
        self.assertTrue(all(row["needs_confirmation"] for row in rows_by_step["P20"]))
        self.assertTrue(all(row["needs_confirmation"] for row in rows_by_step["P30"]))
        self.assertTrue(any(not row["needs_confirmation"] for row in rows_by_step["P10"]))

    def test_generate_three_tables_from_drawing_exports_full_draft_package(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            image_path = self._write_png(root / "drawing.png")

            result = generate_three_tables_from_drawing(
                image_path,
                root / "out",
                context={"part_family": "hinge"},
                analyzer=FakeMultimodalDrawingAnalyzer(json.dumps(self._analysis_payload())),
            )

            self.assertEqual(result["document_type"], "three_table_generation_result")
            self.assertEqual(result["status"], "needs_review")
            self.assertEqual(result["status_display"], "待人工复核")
            self.assertTrue(validate_bundle_schema(result, "three_table_generation_result"))
            self.assertEqual(
                set(result["exports"]),
                {"unified_workbook", "process_flow", "pfmea", "control_plan"},
            )
            for path in result["exports"].values():
                self._assert_xlsx(Path(path))
            self.assertTrue(Path(result["manifest"]["path"]).exists())
            self.assertIn("unified_workbook", result["manifest"]["artifact_hashes"])
            self.assertTrue(result["manual_review"]["required"])
            self.assertIn("raw_items", result["manual_review"])
            self.assertGreaterEqual(
                result["manual_review"]["raw_count"],
                len(result["manual_review"]["items"]),
            )
            self.assertLessEqual(len(result["manual_review"]["items"]), 6)
            self.assertTrue(
                all("message" in item and "category" in item for item in result["manual_review"]["items"])
            )
            self.assertTrue(
                all("severity_display" in item for item in result["manual_review"]["items"])
            )
            self.assertTrue(
                any(
                    item.get("category") == "PFMEA 复核"
                    for item in result["manual_review"]["items"]
                )
            )
            review_keys = [
                _canonical_review_key(item if isinstance(item, str) else item.get("item_id"))
                for item in result["manual_review"]["items"]
            ]
            self.assertEqual(len(review_keys), len(set(review_keys)))

    def test_generate_three_tables_final_export_blocks_unreviewed_ai_draft(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = self._write_png(Path(tmpdir) / "drawing.png")

            result = generate_three_tables_from_drawing(
                image_path,
                Path(tmpdir) / "out",
                export_mode="final",
                analyzer=FakeMultimodalDrawingAnalyzer(json.dumps(self._analysis_payload())),
            )

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["blocked_stage"], "final_three_table")
            self.assertEqual(result["exports"], {})

    def test_generate_three_tables_propagates_invalid_ai_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = self._write_png(Path(tmpdir) / "drawing.png")

            with self.assertRaisesRegex(DrawingAnalysisError, "invalid JSON"):
                generate_three_tables_from_drawing(
                    image_path,
                    Path(tmpdir) / "out",
                    analysis_mode="vision_only",
                    analyzer=FakeMultimodalDrawingAnalyzer("{bad"),
                )

    def test_generate_three_tables_cli_saves_failure_result_without_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = self._write_png(Path(tmpdir) / "drawing.png")
            result_path = Path(tmpdir) / "result.json"
            import os

            with patch.dict(os.environ, {"MINOS_DISABLE_CODEX_CONFIG": "1"}, clear=True):
                code = main(
                    [
                        "generate-three-tables",
                        "--input",
                        str(image_path),
                        "--output-dir",
                        str(Path(tmpdir) / "out"),
                        "--result-output",
                        str(result_path),
                        "--mode", "vision_only",
                    ]
                )

            self.assertEqual(code, 2)
            self.assertFalse(result_path.exists())

    def test_generate_three_tables_cli_saves_result_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = self._write_png(Path(tmpdir) / "drawing.png")
            result_path = Path(tmpdir) / "result.json"
            fake_result = {
                "document_type": "three_table_generation_result",
                "schema_version": "minos-core.three_table_generation_result.v1",
                "status": "needs_review",
                "drawing_analysis": {},
                "process_flow": {},
                "pfmea": {},
                "control_plan": {},
                "quality_gate": {},
                "exports": {"unified_workbook": str(Path(tmpdir) / "三表总工作簿.xlsx")},
                "manifest": {},
            }
            with patch(
                "minos_core.pipeline.generate_three_tables_from_drawing",
                return_value=fake_result,
            ):
                code = main(
                    [
                        "generate-three-tables",
                        "--input",
                        str(image_path),
                        "--output-dir",
                        str(Path(tmpdir) / "out"),
                        "--result-output",
                        str(result_path),
                        "--context-json",
                        '{"part_family":"hinge"}',
                    ]
                )

            self.assertEqual(code, 0)
            saved = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "needs_review")

    def _write_png(self, path: Path) -> Path:
        Image.new("RGB", (100, 80), color="white").save(path)
        return path

    def _analysis_payload(self):
        refs = ["drawing_page_001"]
        return {
            "drawing_identity": {
                "part_name": "Hinge Bracket",
                "drawing_number": "HB-001",
                "revision": "A",
                "evidence_refs": refs,
            },
            "materials": [
                {"name": "SPCC", "confidence": 0.92, "evidence_refs": refs}
            ],
            "surface_treatments": [
                {"name": "Zinc plated", "confidence": 0.8, "evidence_refs": refs}
            ],
            "dimensions": [
                {"name": "hole diameter", "value": "8.0 +/-0.1", "confidence": 0.88, "evidence_refs": refs}
            ],
            "tolerances": [],
            "special_characteristics": [
                {
                    "id": "SC-001",
                    "name": "hole position",
                    "classification": "SC",
                    "specification": "+/-0.1",
                    "confidence": 0.7,
                    "evidence_refs": refs,
                }
            ],
            "technical_requirements": [
                {"text": "No burrs", "confidence": 0.9, "evidence_refs": refs}
            ],
            "inspection_requirements": [
                {"text": "Check critical dimensions", "confidence": 0.85, "evidence_refs": refs}
            ],
            "manufacturing_clues": [
                {
                    "process_step_id": "P10",
                    "operation": "Blanking",
                    "process_function": "Create blank profile",
                    "equipment": "Press",
                    "confidence": 0.82,
                    "evidence_refs": refs,
                },
                {
                    "process_step_id": "P20",
                    "operation": "Piercing",
                    "process_function": "Create mounting holes",
                    "equipment": "Piercing die",
                    "special_characteristics": ["SC-001"],
                    "confidence": 0.78,
                    "evidence_refs": refs,
                },
                {
                    "process_step_id": "P30",
                    "operation": "Surface treatment",
                    "process_function": "Apply corrosion protection",
                    "confidence": 0.76,
                    "evidence_refs": refs,
                },
            ],
            "uncertainties": [
                {"text": "Exact process sequence requires engineer review", "confidence": 0.6, "evidence_refs": refs}
            ],
        }

    def _assert_xlsx(self, path: Path):
        self.assertTrue(Path(path).exists())
        with ZipFile(path) as archive:
            names = set(archive.namelist())
        self.assertIn("[Content_Types].xml", names)
        self.assertIn("xl/workbook.xml", names)

    def _xlsx_text(self, path: Path) -> str:
        with ZipFile(path) as archive:
            return "\n".join(
                archive.read(name).decode("utf-8")
                for name in archive.namelist()
                if name.endswith(".xml")
            )

    def _sheet_names(self, path: Path) -> list[str]:
        from xml.etree import ElementTree

        ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        with ZipFile(path) as archive:
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        return [node.attrib["name"] for node in workbook.findall(".//main:sheet", ns)]


def _canonical_review_key(value):
    text = str(value or "").strip()
    if text.startswith("failure_mode:"):
        return "pfmea:" + text.split(":", 1)[1]
    if text.startswith("control_item:"):
        return "control_plan:" + text.split(":", 1)[1]
    if text.startswith("process_step:"):
        return "pfd:" + text.split(":", 1)[1]
    if text.startswith("PFMEA-"):
        return "pfmea:" + text
    if text.startswith("CP-"):
        return "control_plan:" + text
    return text


def _rows_by_step(rows):
    by_step = {}
    for row in rows:
        by_step.setdefault(row["process_step_id"], []).append(row)
    return by_step


def _assert_pfmea_ai_risk_row(test_case, row):
    required_fields = {
        "severity",
        "occurrence",
        "detection",
        "action_priority",
        "S",
        "O",
        "D",
        "AP",
        "prevention_control",
        "detection_control",
        "recommended_action",
        "ai_reasoning",
        "confidence",
        "ai_inferred",
        "needs_confirmation",
        "evidence_refs",
    }
    test_case.assertTrue(required_fields.issubset(row))
    test_case.assertIn(row["action_priority"], {"H", "M", "L"})
    test_case.assertTrue(row["prevention_control"])
    test_case.assertTrue(row["detection_control"])
    test_case.assertTrue(row["recommended_action"])
    test_case.assertTrue(row["ai_reasoning"])
    test_case.assertTrue(row["ai_inferred"])
    test_case.assertIsInstance(row["needs_confirmation"], bool)
    test_case.assertIsInstance(row["evidence_refs"], list)
    test_case.assertGreaterEqual(row["confidence"], 0.0)
    test_case.assertLessEqual(row["confidence"], 0.9)


if __name__ == "__main__":
    unittest.main()
