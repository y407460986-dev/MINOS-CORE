import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from PIL import Image

from minos_core.adapters.multimodal import FakeMultimodalDrawingAnalyzer
from minos_core.cli import main
from minos_core.drawing_analysis import (
    DrawingAnalysisError,
    analyze_drawing_pages,
)
from minos_core.drawing_input import (
    load_drawing_source,
    render_drawing_pages,
)
from minos_core.drawing_to_pfd import infer_process_flow_from_drawing
from minos_core.exporters.three_table_workbooks import (
    export_split_three_table_workbooks,
    export_three_table_workbook,
)
from minos_core.generate_control_plan import (
    generate_control_plan_from_pfmea,
)
from minos_core.pfd_to_pfmea_ai import (
    infer_pfmea_from_process_flow,
)
from minos_core.pipeline import generate_three_tables_from_drawing
from minos_core.schemas import validate_bundle_schema
from minos_core.three_table_result import build_three_table_generation_envelope


class IntegrationTests(unittest.TestCase):
    """End-to-end integration tests for three table generation workflow."""

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
                    "cause_process_parameter": "原因过程参数值",
                    "prevention_control_target": "预防控制对象值",
                    "prevention_control_timing": "预防控制时机值",
                    "severity": 7,
                    "occurrence": 4,
                    "detection": 5,
                    "action_priority": "M",
                    "detection_control": "探测控制值",
                    "detection_control_target": "探测对象值",
                    "detection_control_timing": "探测时机值",
                    "control_logic_review": "控制逻辑复核值",
                    "special_characteristics": "CC",
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
                    "process_parameter": "冲压力",
                    "parameter_specification": "10-12 kN",
                    "process_control_method": "参数锁定和首件确认",
                    "setup_verification": "换型首件确认",
                    "poka_yoke_device": "参数权限锁",
                    "poka_yoke_verification": "每班验证参数锁有效",
                    "process_record": "冲压参数记录表",
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
            self.assertIn("措施后 S/O/D/AP", text)
            self.assertIn("特殊特性", text)
            self.assertIn("原因过程参数", text)
            self.assertIn("预防控制对象", text)
            self.assertIn("预防控制时机", text)
            self.assertIn("探测对象", text)
            self.assertIn("探测时机", text)
            self.assertIn("控制逻辑复核", text)
            self.assertIn("CC", text)
            self.assertIn("标准结构过程项", text)
            self.assertIn("标准功能过程项", text)
            self.assertIn("标准功能工作要素", text)
            self.assertIn("原因过程参数值", text)
            self.assertIn("预防控制对象值", text)
            self.assertIn("预防控制时机值", text)
            self.assertIn("探测对象值", text)
            self.assertIn("探测时机值", text)
            self.assertIn("控制逻辑复核值", text)
            self.assertIn("标准优化措施", text)
            self.assertIn("标准责任人", text)
            self.assertIn("标准状态", text)
            self.assertNotIn("旧过程项", text)
            self.assertNotIn("旧推荐措施", text)
            self.assertNotIn("RPN", text)
        for text in (unified_text, split_cp_text):
            self.assertIn("特性编号", text)
            self.assertIn("产品特性", text)
            self.assertIn("过程特性", text)
            self.assertIn("特殊特性分类", text)
            self.assertIn("规格和公差", text)
            self.assertIn("过程参数", text)
            self.assertIn("参数规格", text)
            self.assertIn("过程控制方法", text)
            self.assertIn("首件/换型确认", text)
            self.assertIn("防错装置", text)
            self.assertIn("防错验证", text)
            self.assertIn("过程记录", text)
            self.assertIn("标准设备", text)
            self.assertIn("CH-01", text)
            self.assertIn("标准产品特性", text)
            self.assertIn("标准过程特性", text)
            self.assertIn("标准特殊分类", text)
            self.assertIn("标准规格公差", text)
            self.assertIn("冲压力", text)
            self.assertIn("10-12 kN", text)
            self.assertIn("参数锁定和首件确认", text)
            self.assertIn("换型首件确认", text)
            self.assertIn("参数权限锁", text)
            self.assertIn("每班验证参数锁有效", text)
            self.assertIn("冲压参数记录表", text)
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

    def test_three_table_result_builder_preserves_envelope_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            final_gate = {
                "stage": "final_three_table",
                "can_continue": False,
                "allow_user_export": False,
                "manual_review_items": [
                    {
                        "item_id": "failure_mode:PFMEA-P10-001",
                        "category": "pfmea",
                        "severity": "blocker",
                        "message": "PFMEA 行需要人工确认。",
                    }
                ],
                "needs_confirmation_items": [],
            }

            envelope = build_three_table_generation_envelope(
                status="needs_review",
                drawing_analysis={"evidence": []},
                process_flow={"steps": []},
                pfmea={"rows": []},
                control_plan={"rows": []},
                chain={"metadata": {}},
                quality_gates={"final_three_table": final_gate},
                exports={},
                output_dir=root,
                inputs={"drawing_path": "drawing.png"},
                blocked_stage=None,
                warnings=["warning"],
                part_family_classification={"family": "stamping"},
                family_context={"route": "demo"},
            )

            self.assertEqual(envelope["document_type"], "three_table_generation_result")
            self.assertEqual(envelope["quality_gate"], final_gate)
            self.assertEqual(envelope["manual_review"]["raw_count"], 1)
            self.assertEqual(envelope["manual_review"]["items"][0]["category"], "PFMEA 复核")
            self.assertEqual(envelope["metadata"]["part_family_classification"]["family"], "stamping")
            self.assertTrue(Path(envelope["manifest"]["path"]).exists())

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
            captured: dict[str, object] = {}
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

            def generate_three_tables(*args, **kwargs):
                captured["ocr_engine"] = kwargs["ocr_engine"]
                return fake_result

            with patch(
                "minos_core.pipeline.generate_three_tables_from_drawing",
                side_effect=generate_three_tables,
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
                        "--ocr-engine",
                        "mineru",
                        "--context-json",
                        '{"part_family":"hinge"}',
                    ]
                )

            self.assertEqual(code, 0)
            saved = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "needs_review")
            self.assertEqual(captured["ocr_engine"], "mineru")

    def test_analyze_drawing_cli_accepts_mineru_ocr_engine(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = self._write_png(Path(tmpdir) / "drawing.png")
            result_path = Path(tmpdir) / "analysis.json"
            captured: dict[str, object] = {}

            def analyze_for_mode(*args, **kwargs):
                captured["ocr_engine"] = kwargs["ocr_engine"]
                return {"metadata": {}}, [], "ocr", []

            with patch(
                "minos_core.pipeline._analyze_drawing_pages_for_mode",
                side_effect=analyze_for_mode,
            ):
                with patch(
                    "minos_core.pipeline._effective_ocr_engine",
                    return_value="mineru",
                ):
                    code = main(
                        [
                            "analyze-drawing",
                            "--input",
                            str(image_path),
                            "--output",
                            str(result_path),
                            "--ocr-engine",
                            "mineru",
                        ]
                    )

            self.assertEqual(code, 0)
            self.assertEqual(captured["ocr_engine"], "mineru")


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


_PFMEA_CONTROL_LOGIC_FIELDS = (
    "cause_process_parameter",
    "prevention_control_target",
    "prevention_control_timing",
    "detection_control_target",
    "detection_control_timing",
    "control_logic_review",
)


def _assert_pfmea_ai_risk_row(test_case, row):
    required_fields = {
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
        *_PFMEA_CONTROL_LOGIC_FIELDS,
        "preventive_action",
        "detection_action",
        "optimization_action",
        "recommended_action",
        "responsible_person",
        "target_date",
        "status",
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
    for field in _PFMEA_CONTROL_LOGIC_FIELDS:
        test_case.assertTrue(row[field], field)
    test_case.assertTrue(row["optimization_action"])
    test_case.assertTrue(row["recommended_action"])
    test_case.assertTrue(row["ai_reasoning"])
    test_case.assertTrue(row["ai_inferred"])
    test_case.assertNotIn("rpn", row)
    test_case.assertNotIn("after_rpn", row)
    test_case.assertIsInstance(row["needs_confirmation"], bool)
    test_case.assertIsInstance(row["evidence_refs"], list)
    test_case.assertGreaterEqual(row["confidence"], 0.0)
    test_case.assertLessEqual(row["confidence"], 0.9)


if __name__ == "__main__":
    unittest.main()
