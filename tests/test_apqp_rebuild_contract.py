import copy
import importlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree

from minos_core.adapters.fixture_json import load_fixture_payload

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "apqp_chain"
SAMPLES_DIR = ROOT / "configs" / "samples"
NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REQUIRED_SHEETS = [
    "摘要",
    "质量门状态",
    "正式导出审计",
    "知识推荐与行动闭环",
    "过程流程图",
    "PFMEA",
    "控制计划",
    "三表追溯矩阵",
    "人工复核清单",
]


def _load_json(name):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _import_first(*module_names):
    errors = []
    for module_name in module_names:
        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            errors.append(f"{module_name}: {exc}")
    raise AssertionError(
        "Cannot import expected MINOS-CORE module:\n" + "\n".join(errors)
    )


def _get_first(module, *names):
    for name in names:
        value = getattr(module, name, None)
        if value is not None:
            return value
    raise AssertionError(f"{module.__name__} must expose one of: {', '.join(names)}")


def _as_mapping(value):
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if hasattr(value, "__dict__"):
        return vars(value)
    raise AssertionError(f"Unsupported domain object type: {type(value)!r}")


def _validation_ok(result):
    if result is None:
        return True
    if isinstance(result, bool):
        return result
    if isinstance(result, tuple):
        return bool(result[0])
    if isinstance(result, dict):
        return bool(result.get("ok", result.get("valid", False)))
    if hasattr(result, "ok"):
        return bool(result.ok)
    if hasattr(result, "valid"):
        return bool(result.valid)
    return bool(result)


def _validation_messages(result):
    if isinstance(result, tuple) and len(result) > 1:
        return str(result[1])
    if isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False)
    return str(result)


def _sheet_names(xlsx_path):
    with zipfile.ZipFile(xlsx_path) as archive:
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    return [
        item.attrib["name"] for item in workbook.findall("main:sheets/main:sheet", NS)
    ]


def _assert_basic_xlsx_structure(testcase, xlsx_path):
    with zipfile.ZipFile(xlsx_path) as archive:
        names = set(archive.namelist())
    testcase.assertIn("[Content_Types].xml", names)
    testcase.assertIn("_rels/.rels", names)
    testcase.assertIn("xl/workbook.xml", names)
    testcase.assertIn("xl/_rels/workbook.xml.rels", names)
    testcase.assertTrue(
        any(name.startswith("xl/worksheets/sheet") for name in names),
        "xlsx package must contain worksheet XML files",
    )


def _worksheet_xml(xlsx_path, index):
    with zipfile.ZipFile(xlsx_path) as archive:
        return archive.read(f"xl/worksheets/sheet{index}.xml").decode("utf-8")


def _passing_export_gate(**overrides):
    values = {
        "stage": "export",
        "can_continue": True,
        "allow_user_export": True,
        "evidence_sufficient": True,
        "evidence_coverage": {
            "coverage_ratio": 1,
            "covered_items": 1,
            "required_items": 1,
            "ai_inferred_refs": [],
        },
        "uncovered_evidence_items": [],
        "missing_evidence_refs": [],
        "needs_confirmation_items": [],
        "pending_fields": [],
        "ai_inferred_items": [],
        "manual_review_items": [],
        "review_issues": [],
        "sync_issues": [],
        "linkage_gaps": [],
        "validation": SimpleNamespace(messages=[]),
        "audit": SimpleNamespace(
            counts={
                "process_steps": 0,
                "failure_modes": 0,
                "controls": 0,
                "mechanical_links": 0,
                "weak_links": 0,
            }
        ),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class DomainAndValidationContractTests(unittest.TestCase):
    def test_domain_core_exposes_business_objects_without_file_io(self):
        domain_module = _import_first("minos_core.domain")
        for name in (
            "Product",
            "Drawing",
            "Characteristic",
            "ProcessStep",
            "FailureMode",
            "ControlItem",
            "Evidence",
            "TraceLink",
        ):
            self.assertTrue(
                hasattr(domain_module, name), f"missing domain object: {name}"
            )
        self.assertFalse(
            hasattr(domain_module, "_read_json"),
            "Domain Core must not own fixture file IO",
        )

    def test_domain_loader_reads_complete_apqp_fixture(self):
        domain_module = _import_first("minos_core.domain")
        load_chain = _get_first(
            domain_module,
            "load_apqp_chain",
            "load_domain_bundle",
            "load_chain",
        )

        chain = _as_mapping(load_chain(FIXTURE_DIR))

        self.assertIn("process_flow", chain)
        self.assertIn("pfmea", chain)
        self.assertIn("control_plan", chain)
        self.assertIn("evidence", chain)
        self.assertEqual(len(_as_mapping(chain["process_flow"])["steps"]), 3)
        self.assertEqual(len(_as_mapping(chain["pfmea"])["rows"]), 4)
        self.assertEqual(len(_as_mapping(chain["control_plan"])["rows"]), 4)
        self.assertEqual(len(chain["evidence"]), 6)

    def test_fixture_json_adapter_owns_fixture_file_loading(self):
        fixture_adapter = _import_first("minos_core.adapters.fixture_json")
        load_payload = _get_first(
            fixture_adapter, "load_fixture_payload", "load_apqp_chain"
        )

        chain = load_payload(FIXTURE_DIR)

        self.assertIn("process_flow", chain)
        self.assertIn("pfmea", chain)
        self.assertIn("control_plan", chain)
        self.assertIn("evidence", chain)
        self.assertIsInstance(chain["evidence"], list)
        self.assertEqual(chain["evidence"][0]["evidence_id"], "EV-PFD-ROUTE-001")

    def test_fixture_json_adapter_keeps_legacy_directory_without_evidence(self):
        fixture_adapter = _import_first("minos_core.adapters.fixture_json")
        load_payload = _get_first(fixture_adapter, "load_fixture_payload")

        with tempfile.TemporaryDirectory() as tmp:
            fixture_dir = Path(tmp) / "legacy_fixture"
            fixture_dir.mkdir()
            for name in ("process_flow.json", "pfmea.json", "control_plan.json"):
                shutil.copy(FIXTURE_DIR / name, fixture_dir / name)

            chain = load_payload(fixture_dir)

        self.assertIn("process_flow", chain)
        self.assertIn("pfmea", chain)
        self.assertIn("control_plan", chain)
        self.assertNotIn("evidence", chain)

    def test_validation_accepts_complete_fixture(self):
        domain_module = _import_first("minos_core.domain")
        validation_module = _import_first("minos_core.validation")
        load_chain = _get_first(
            domain_module, "load_apqp_chain", "load_domain_bundle", "load_chain"
        )
        validate_chain = _get_first(
            validation_module,
            "validate_apqp_chain",
            "validate_chain",
            "validate_domain_bundle",
        )

        result = validate_chain(load_chain(FIXTURE_DIR))

        self.assertTrue(_validation_ok(result), _validation_messages(result))

    def test_domain_objects_preserve_evidence_references(self):
        domain_module = _import_first("minos_core.domain")
        apqp_chain_type = _get_first(domain_module, "APQPChain")
        payload = {
            "process_flow": {
                "document_type": "process_flow",
                "steps": [
                    {
                        "process_step_id": "P10",
                        "operation": "Cut",
                        "evidence_refs": ["EV-PFD-001"],
                    }
                ],
                "links": [
                    {
                        "from": "P10",
                        "to": "P20",
                        "link_type": "sequence",
                        "evidence_refs": "EV-LINK-001",
                    }
                ],
            },
            "pfmea": {
                "document_type": "pfmea",
                "rows": [
                    {
                        "pfmea_id": "PFMEA-P10-001",
                        "process_step_id": "P10",
                        "failure_mode": "Burr",
                        "evidence_refs": ["EV-FMEA-001"],
                    }
                ],
            },
            "control_plan": {
                "document_type": "control_plan",
                "rows": [
                    {
                        "control_plan_id": "CP-P10-001",
                        "process_step_id": "P10",
                        "pfmea_id": "PFMEA-P10-001",
                        "evidence_refs": ["EV-CP-001"],
                    }
                ],
            },
            "evidence": [
                {
                    "evidence_id": "EV-PFD-001",
                    "source": "drawing",
                    "content": "PFD basis",
                },
                {
                    "evidence_id": "EV-FMEA-001",
                    "source": "analysis",
                    "content": "PFMEA basis",
                },
                {
                    "evidence_id": "EV-CP-001",
                    "source": "inspection",
                    "content": "Control basis",
                },
                {
                    "evidence_id": "EV-LINK-001",
                    "source": "trace",
                    "content": "Trace basis",
                },
            ],
        }

        chain = apqp_chain_type(**payload)
        dumped = chain.model_dump()

        self.assertEqual(chain.process_steps[0].evidence_refs, ["EV-PFD-001"])
        self.assertEqual(chain.failure_modes[0].evidence_refs, ["EV-FMEA-001"])
        self.assertEqual(chain.controls[0].evidence_refs, ["EV-CP-001"])
        self.assertEqual(chain.links[0].evidence_refs, ["EV-LINK-001"])
        self.assertEqual(dumped["process_steps"][0]["evidence_refs"], ["EV-PFD-001"])
        self.assertEqual(dumped["failure_modes"][0]["evidence_refs"], ["EV-FMEA-001"])
        self.assertEqual(dumped["controls"][0]["evidence_refs"], ["EV-CP-001"])
        self.assertEqual(dumped["links"][0]["evidence_refs"], ["EV-LINK-001"])

    def test_validation_fails_when_mandatory_pfmea_has_no_control_plan_row(self):
        validation_module = _import_first("minos_core.validation")
        validate_chain = _get_first(
            validation_module,
            "validate_apqp_chain",
            "validate_chain",
            "validate_domain_bundle",
        )
        chain = {
            "process_flow": _load_json("process_flow.json"),
            "pfmea": _load_json("pfmea.json"),
            "control_plan": _load_json("control_plan.json"),
        }
        chain["control_plan"] = copy.deepcopy(chain["control_plan"])
        chain["control_plan"]["rows"] = [
            row
            for row in chain["control_plan"]["rows"]
            if row["pfmea_id"] != "PFMEA-P20-002"
        ]

        result = validate_chain(chain)

        self.assertFalse(
            _validation_ok(result), "mandatory PFMEA row without CP coverage must fail"
        )
        self.assertIn("PFMEA-P20-002", _validation_messages(result))


class XlsxExportContractTests(unittest.TestCase):
    def test_xlsx_writer_deduplicates_sheet_names_and_writes_valid_zip_structure(self):
        exporter_module = _import_first(
            "minos_core.exporters.xlsx",
            "minos_core.exporters.xlsx_export",
            "minos_core.xlsx_export",
        )
        write_xlsx = _get_first(exporter_module, "write_xlsx", "write_workbook")
        long_name = "Duplicate/Sheet*Name That Is Longer Than Thirty One Characters"
        sheets = [
            {"name": long_name, "headers": ["id", "value"], "rows": [["1", "alpha"]]},
            {
                "name": long_name.lower(),
                "headers": ["id", "value"],
                "rows": [["2", "beta"]],
            },
            {"name": long_name, "headers": ["id", "value"], "rows": [["3", "gamma"]]},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            xlsx_path = Path(tmp) / "dedupe.xlsx"
            write_xlsx(xlsx_path, sheets)

            _assert_basic_xlsx_structure(self, xlsx_path)
            names = _sheet_names(xlsx_path)

        self.assertEqual(len(names), 3)
        self.assertEqual(len(names), len(set(name.lower() for name in names)))
        self.assertTrue(all(len(name) <= 31 for name in names))
        self.assertTrue(all("/" not in name and "*" not in name for name in names))

    def test_apqp_workbook_contains_quality_gate_and_manual_review_sheets(self):
        exporter_module = _import_first(
            "minos_core.exporters.apqp_workbook",
            "minos_core.exporters.xlsx",
            "minos_core.apqp_workbook",
        )
        export_workbook = _get_first(
            exporter_module,
            "export_apqp_workbook",
            "write_apqp_workbook",
            "export_workbook",
        )
        chain = {
            "process_flow": _load_json("process_flow.json"),
            "pfmea": _load_json("pfmea.json"),
            "control_plan": _load_json("control_plan.json"),
        }
        with tempfile.TemporaryDirectory() as tmp:
            xlsx_path = Path(tmp) / "apqp.xlsx"
            export_workbook(chain, xlsx_path)

            _assert_basic_xlsx_structure(self, xlsx_path)
            names = _sheet_names(xlsx_path)

        self.assertEqual(
            names,
            REQUIRED_SHEETS,
        )

    def test_apqp_workbook_quality_gate_sheet_contains_key_fields(self):
        exporter_module = _import_first("minos_core.exporters.apqp_workbook")
        export_workbook = _get_first(exporter_module, "export_apqp_workbook")
        chain = {
            "process_flow": _load_json("process_flow.json"),
            "pfmea": _load_json("pfmea.json"),
            "control_plan": _load_json("control_plan.json"),
        }
        with tempfile.TemporaryDirectory() as tmp:
            xlsx_path = Path(tmp) / "apqp.xlsx"
            export_workbook(chain, xlsx_path)
            with zipfile.ZipFile(xlsx_path) as archive:
                gate_sheet = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
                audit_sheet = archive.read("xl/worksheets/sheet3.xml").decode("utf-8")
                review_sheet = archive.read("xl/worksheets/sheet9.xml").decode("utf-8")

        self.assertIn("允许用户导出", gate_sheet)
        self.assertIn("证据充分", gate_sheet)
        self.assertIn("证据覆盖率", gate_sheet)
        self.assertIn("缺失证据引用数", gate_sheet)
        self.assertIn("待确认证据数", gate_sheet)
        self.assertIn("明细复核项数", gate_sheet)
        self.assertIn("正式导出审计", audit_sheet)
        self.assertIn("allow_final_export", audit_sheet)
        self.assertIn("review_confirmations", audit_sheet)
        self.assertIn("edit_history", audit_sheet)
        self.assertIn("soft_deleted_items", audit_sheet)
        self.assertIn("对象ID", review_sheet)
        self.assertIn("复核说明", review_sheet)

    def test_apqp_workbook_synthesizes_traceability_rows_from_pfmea_and_controls(self):
        exporter_module = _import_first("minos_core.exporters.apqp_workbook")
        export_workbook = _get_first(exporter_module, "export_apqp_workbook")
        chain = {
            "failure_modes": [
                {
                    "pfmea_id": "PFMEA-P10-001",
                    "process_step_id": "P10",
                    "failure_mode": "Burr",
                }
            ],
            "controls": [
                {
                    "control_plan_id": "CP-P10-001",
                    "pfmea_id": "PFMEA-P10-001",
                    "process_name": "Cut",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            xlsx_path = Path(tmp) / "apqp.xlsx"
            export_workbook(
                chain,
                xlsx_path,
                require_gate=False,
                quality_gate=_passing_export_gate(),
            )
            trace_sheet = _worksheet_xml(xlsx_path, 8)

        self.assertIn("PFMEA-P10-001", trace_sheet)
        self.assertIn("CP-P10-001", trace_sheet)
        self.assertIn('r="A2"', trace_sheet)

    def test_apqp_workbook_synthesizes_traceability_rows_from_nested_tables(self):
        exporter_module = _import_first("minos_core.exporters.apqp_workbook")
        export_workbook = _get_first(exporter_module, "export_apqp_workbook")
        chain = {
            "pfmea": {
                "document_type": "pfmea",
                "rows": [
                    {
                        "pfmea_id": "PFMEA-P20-002",
                        "process_step_id": "P20",
                        "failure_mode": "Crack",
                    }
                ],
            },
            "control_plan": {
                "document_type": "control_plan",
                "rows": [
                    {
                        "control_plan_id": "CP-P20-002",
                        "pfmea_id": "PFMEA-P20-002",
                        "process_name": "Form",
                    }
                ],
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            xlsx_path = Path(tmp) / "apqp.xlsx"
            export_workbook(
                chain,
                xlsx_path,
                require_gate=False,
                quality_gate=_passing_export_gate(),
            )
            trace_sheet = _worksheet_xml(xlsx_path, 8)

        self.assertIn("PFMEA-P20-002", trace_sheet)
        self.assertIn("CP-P20-002", trace_sheet)
        self.assertIn('r="A2"', trace_sheet)

    def test_apqp_workbook_prefers_explicit_traceability_matrix(self):
        exporter_module = _import_first("minos_core.exporters.apqp_workbook")
        export_workbook = _get_first(exporter_module, "export_apqp_workbook")
        chain = {
            "traceability_matrix": [
                {
                    "step_no": "P30",
                    "characteristic": "explicit characteristic",
                    "process_flow_ref": "PFD-P30",
                    "pfmea_ref": "PFMEA-EXPLICIT",
                    "control_plan_ref": "CP-EXPLICIT",
                }
            ],
            "failure_modes": [
                {
                    "pfmea_id": "PFMEA-SYNTH-NOT-USED",
                    "process_step_id": "P40",
                    "failure_mode": "Warp",
                }
            ],
            "controls": [
                {
                    "control_plan_id": "CP-SYNTH-NOT-USED",
                    "pfmea_id": "PFMEA-SYNTH-NOT-USED",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            xlsx_path = Path(tmp) / "apqp.xlsx"
            export_workbook(
                chain,
                xlsx_path,
                require_gate=False,
                quality_gate=_passing_export_gate(),
            )
            trace_sheet = _worksheet_xml(xlsx_path, 8)

        self.assertIn("PFMEA-EXPLICIT", trace_sheet)
        self.assertIn("CP-EXPLICIT", trace_sheet)
        self.assertNotIn("PFMEA-SYNTH-NOT-USED", trace_sheet)
        self.assertNotIn("CP-SYNTH-NOT-USED", trace_sheet)

    def test_apqp_workbook_prefers_nested_explicit_traceability_matrix(self):
        exporter_module = _import_first("minos_core.exporters.apqp_workbook")
        export_workbook = _get_first(exporter_module, "export_apqp_workbook")
        chain = {
            "traceability_matrix": {
                "document_type": "traceability_matrix",
                "rows": [
                    {
                        "step_no": "P50",
                        "characteristic": "nested explicit characteristic",
                        "process_flow_ref": "PFD-P50",
                        "pfmea_ref": "PFMEA-NESTED-EXPLICIT",
                        "control_plan_ref": "CP-NESTED-EXPLICIT",
                    }
                ],
            },
            "failure_modes": [
                {
                    "pfmea_id": "PFMEA-NESTED-SYNTH-NOT-USED",
                    "process_step_id": "P60",
                    "failure_mode": "Scratch",
                }
            ],
            "controls": [
                {
                    "control_plan_id": "CP-NESTED-SYNTH-NOT-USED",
                    "pfmea_id": "PFMEA-NESTED-SYNTH-NOT-USED",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            xlsx_path = Path(tmp) / "apqp.xlsx"
            export_workbook(
                chain,
                xlsx_path,
                require_gate=False,
                quality_gate=_passing_export_gate(),
            )
            trace_sheet = _worksheet_xml(xlsx_path, 8)

        self.assertIn("P50", trace_sheet)
        self.assertIn("nested explicit characteristic", trace_sheet)
        self.assertIn("PFD-P50", trace_sheet)
        self.assertIn("PFMEA-NESTED-EXPLICIT", trace_sheet)
        self.assertIn("CP-NESTED-EXPLICIT", trace_sheet)
        self.assertNotIn("PFMEA-NESTED-SYNTH-NOT-USED", trace_sheet)
        self.assertNotIn("CP-NESTED-SYNTH-NOT-USED", trace_sheet)

    def test_apqp_workbook_synthesizes_when_nested_traceability_matrix_rows_are_empty(self):
        exporter_module = _import_first("minos_core.exporters.apqp_workbook")
        export_workbook = _get_first(exporter_module, "export_apqp_workbook")
        chain = {
            "traceability_matrix": {
                "document_type": "traceability_matrix",
                "rows": [],
            },
            "failure_modes": [
                {
                    "pfmea_id": "PFMEA-P70-001",
                    "process_step_id": "P70",
                    "failure_mode": "Dent",
                }
            ],
            "controls": [
                {
                    "control_plan_id": "CP-P70-001",
                    "pfmea_id": "PFMEA-P70-001",
                    "process_name": "Inspect",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            xlsx_path = Path(tmp) / "apqp.xlsx"
            export_workbook(
                chain,
                xlsx_path,
                require_gate=False,
                quality_gate=_passing_export_gate(),
            )
            trace_sheet = _worksheet_xml(xlsx_path, 8)

        self.assertIn("PFMEA-P70-001", trace_sheet)
        self.assertIn("CP-P70-001", trace_sheet)
        self.assertIn('r="A2"', trace_sheet)
        self.assertNotIn('r="A3"', trace_sheet)

    def test_apqp_workbook_writes_review_issues_when_manual_review_items_are_empty(self):
        exporter_module = _import_first("minos_core.exporters.apqp_workbook")
        export_workbook = _get_first(exporter_module, "export_apqp_workbook")
        gate = _passing_export_gate(
            manual_review_items=[],
            review_issues=[
                {
                    "issue_id": "DRAWING-RISK-OCR-001",
                    "category": "drawing_risk",
                    "severity": "risk",
                    "message": "图纸 OCR 风险需要人工复核。",
                    "resolved": False,
                }
            ],
        )

        with tempfile.TemporaryDirectory() as tmp:
            xlsx_path = Path(tmp) / "apqp.xlsx"
            export_workbook(
                {},
                xlsx_path,
                require_gate=False,
                quality_gate=gate,
            )
            review_sheet = _worksheet_xml(xlsx_path, 9)

        self.assertIn("DRAWING-RISK-OCR-001", review_sheet)
        self.assertIn("drawing_risk", review_sheet)
        self.assertIn("图纸 OCR 风险需要人工复核。", review_sheet)
        self.assertIn('r="A2"', review_sheet)

    def test_apqp_workbook_review_issue_fallback_only_writes_unresolved_issues(self):
        exporter_module = _import_first("minos_core.exporters.apqp_workbook")
        export_workbook = _get_first(exporter_module, "export_apqp_workbook")
        gate = _passing_export_gate(
            manual_review_items=[],
            review_issues=[
                {
                    "issue_id": "RI-HANDLED",
                    "category": "drawing_risk",
                    "status": "已处理",
                    "message": "handled",
                },
                {
                    "issue_id": "RI-CONFIRMED",
                    "category": "drawing_risk",
                    "status": "已确认",
                    "message": "confirmed",
                },
                {
                    "issue_id": "RI-ACCEPTED",
                    "category": "drawing_risk",
                    "status": "已采纳",
                    "message": "accepted",
                },
                {
                    "issue_id": "RI-NO-IMPACT",
                    "category": "drawing_risk",
                    "status": "无影响",
                    "message": "no impact",
                },
                {
                    "issue_id": "RI-IGNORED",
                    "category": "drawing_risk",
                    "status": "已忽略",
                    "ignore_reason": "人工判断不影响导出",
                    "message": "ignored",
                },
                {
                    "issue_id": "RI-OPEN",
                    "category": "drawing_risk",
                    "status": "待处理",
                    "message": "open",
                },
            ],
        )

        with tempfile.TemporaryDirectory() as tmp:
            xlsx_path = Path(tmp) / "apqp.xlsx"
            export_workbook(
                {},
                xlsx_path,
                require_gate=False,
                quality_gate=gate,
            )
            review_sheet = _worksheet_xml(xlsx_path, 9)

        self.assertIn("RI-OPEN", review_sheet)
        self.assertNotIn("RI-HANDLED", review_sheet)
        self.assertNotIn("RI-CONFIRMED", review_sheet)
        self.assertNotIn("RI-ACCEPTED", review_sheet)
        self.assertNotIn("RI-NO-IMPACT", review_sheet)
        self.assertNotIn("RI-IGNORED", review_sheet)


class CliContractTests(unittest.TestCase):
    def _run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "minos_core.cli", *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_cli_list_validate_export(self):
        list_result = self._run_cli("list", "--samples-dir", str(SAMPLES_DIR))
        self.assertEqual(list_result.returncode, 0, list_result.stderr)
        self.assertIn("door_hinge", list_result.stderr)
        self.assertIn("limiter", list_result.stderr)
        self.assertIn("stamping", list_result.stderr)

        validate_result = self._run_cli("validate", "--input", str(FIXTURE_DIR))
        self.assertEqual(validate_result.returncode, 0, validate_result.stderr)

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "fixture-apqp.xlsx"
            export_result = self._run_cli(
                "export",
                "--input",
                str(FIXTURE_DIR),
                "--output",
                str(output_path),
            )
            self.assertEqual(export_result.returncode, 0, export_result.stderr)
            self.assertTrue(
                output_path.exists(), export_result.stdout + export_result.stderr
            )
            self.assertEqual(
                _sheet_names(output_path),
                REQUIRED_SHEETS,
            )

    def test_cli_export_blocks_quality_gate_bypass(self):
        fixture = load_fixture_payload(FIXTURE_DIR)
        fixture["evidence"][0]["needs_confirmation"] = True

        with tempfile.TemporaryDirectory() as tmp:
            fixture_path = Path(tmp) / "fixture.json"
            output_path = Path(tmp) / "blocked.xlsx"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

            export_result = self._run_cli(
                "export",
                "--input",
                str(fixture_path),
                "--output",
                str(output_path),
            )

            self.assertNotEqual(export_result.returncode, 0)
            self.assertFalse(output_path.exists())
            self.assertIn(
                "APQP export blocked by export gate",
                export_result.stdout + export_result.stderr,
            )


class PipelineArchitectureTests(unittest.TestCase):
    def test_pipeline_declares_fixed_stage_order(self):
        pipeline_module = _import_first("minos_core.pipeline")

        self.assertEqual(
            pipeline_module.PIPELINE_STAGES,
            (
                "ingest",
                "analyze",
                "generate_pfd",
                "brainstorm_failure_modes",
                "generate_pfmea",
                "generate_control_plan",
                "assemble_generated_apqp_chain",
                "generate_draft",
                "validate",
                "export",
            ),
        )


if __name__ == "__main__":
    unittest.main()
