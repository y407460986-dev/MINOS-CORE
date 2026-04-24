import copy
import importlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "apqp_chain"
SAMPLES_DIR = ROOT / "configs" / "samples"
NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


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
        self.assertEqual(len(_as_mapping(chain["process_flow"])["steps"]), 3)
        self.assertEqual(len(_as_mapping(chain["pfmea"])["rows"]), 4)
        self.assertEqual(len(_as_mapping(chain["control_plan"])["rows"]), 4)

    def test_fixture_json_adapter_owns_fixture_file_loading(self):
        fixture_adapter = _import_first("minos_core.adapters.fixture_json")
        load_payload = _get_first(
            fixture_adapter, "load_fixture_payload", "load_apqp_chain"
        )

        chain = load_payload(FIXTURE_DIR)

        self.assertIn("process_flow", chain)
        self.assertIn("pfmea", chain)
        self.assertIn("control_plan", chain)

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

    def test_apqp_workbook_contains_five_required_sheets(self):
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
            ["摘要", "过程流程图", "PFMEA", "控制计划", "三表追溯矩阵"],
        )


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
        self.assertIn("door_hinge", list_result.stdout)
        self.assertIn("limiter", list_result.stdout)
        self.assertIn("stamping", list_result.stdout)

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
                ["摘要", "过程流程图", "PFMEA", "控制计划", "三表追溯矩阵"],
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
                "validate",
                "export",
            ),
        )


if __name__ == "__main__":
    unittest.main()
