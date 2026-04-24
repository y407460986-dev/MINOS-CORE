import importlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from minos_core.domain import load_apqp_chain
from minos_core.pipeline import export_fixture
from minos_core.validation import validate_chain


ROOT = Path(__file__).resolve().parents[1]
NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REQUIRED_SHEETS = ["摘要", "过程流程图", "PFMEA", "控制计划", "三表追溯矩阵"]

LEGACY_WORKBOOKS = {
    "door_hinge": Path(r"C:\Users\fgtan\Desktop\知识库种子\门铰链\JLH01000300-门铰链.xlsx"),
    "stamping": Path(r"C:\Users\fgtan\Desktop\知识库种子\冲压件\1004258-冲压件.xlsx"),
    "limiter": Path(r"C:\Users\fgtan\Desktop\知识库种子\限位器\XWQ01000100-限位器.xlsx"),
}


def _load_convert_legacy_workbook():
    candidates = (
        "minos_core.adapters.legacy_excel",
        "minos_core.adapters.legacy",
    )
    errors = []
    for module_name in candidates:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            errors.append(f"{module_name}: {exc}")
            continue
        converter = getattr(module, "convert_legacy_workbook", None)
        if converter is not None:
            return converter
        errors.append(f"{module_name}: convert_legacy_workbook not found")
    raise AssertionError("Cannot import convert_legacy_workbook:\n" + "\n".join(errors))


def _resolve_fixture_dir(result, expected_dir):
    if result is None:
        return expected_dir
    if isinstance(result, (str, Path)):
        return Path(result)
    if isinstance(result, dict):
        for key in ("fixture_dir", "output_dir", "path"):
            if key in result:
                return Path(result[key])
    for attr in ("fixture_dir", "output_dir", "path"):
        if hasattr(result, attr):
            return Path(getattr(result, attr))
    return expected_dir


def _read_fixture(fixture_dir):
    return {
        "process_flow": json.loads((fixture_dir / "process_flow.json").read_text(encoding="utf-8")),
        "pfmea": json.loads((fixture_dir / "pfmea.json").read_text(encoding="utf-8")),
        "control_plan": json.loads((fixture_dir / "control_plan.json").read_text(encoding="utf-8")),
    }


def _rows(payload, key):
    value = payload.get(key, [])
    if isinstance(value, list):
        return value
    return []


def _validation_messages(result):
    if hasattr(result, "messages"):
        return "\n".join(str(item) for item in result.messages)
    if isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False)
    return str(result)


def _sheet_names(xlsx_path):
    with zipfile.ZipFile(xlsx_path) as archive:
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    return [item.attrib["name"] for item in workbook.findall("main:sheets/main:sheet", NS)]


def _assert_basic_xlsx_structure(testcase, xlsx_path):
    with zipfile.ZipFile(xlsx_path) as archive:
        names = set(archive.namelist())
    testcase.assertIn("[Content_Types].xml", names)
    testcase.assertIn("_rels/.rels", names)
    testcase.assertIn("xl/workbook.xml", names)
    testcase.assertIn("xl/_rels/workbook.xml.rels", names)
    testcase.assertTrue(any(name.startswith("xl/worksheets/sheet") for name in names))


class LegacyExcelAdapterTests(unittest.TestCase):
    def test_convert_legacy_workbooks_to_valid_fixtures_and_export_workbooks(self):
        convert_legacy_workbook = _load_convert_legacy_workbook()

        for sample_id, workbook_path in LEGACY_WORKBOOKS.items():
            with self.subTest(sample=sample_id):
                self.assertTrue(workbook_path.exists(), f"missing legacy workbook: {workbook_path}")
                with tempfile.TemporaryDirectory() as tmp:
                    fixture_dir = Path(tmp) / sample_id
                    result = convert_legacy_workbook(workbook_path, fixture_dir)
                    fixture_dir = _resolve_fixture_dir(result, fixture_dir)

                    payload = _read_fixture(fixture_dir)
                    self.assertGreater(len(_rows(payload["process_flow"], "steps")), 0)
                    self.assertGreater(len(_rows(payload["pfmea"], "rows")), 0)
                    self.assertGreater(len(_rows(payload["control_plan"], "rows")), 0)

                    chain = load_apqp_chain(fixture_dir)
                    validation_result = validate_chain(chain)
                    self.assertTrue(validation_result, _validation_messages(validation_result))

                    workbook_output = Path(tmp) / f"{sample_id}-apqp.xlsx"
                    export_fixture(fixture_dir, workbook_output)
                    _assert_basic_xlsx_structure(self, workbook_output)
                    self.assertEqual(_sheet_names(workbook_output), REQUIRED_SHEETS)


if __name__ == "__main__":
    unittest.main()
