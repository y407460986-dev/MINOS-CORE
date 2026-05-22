from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from minos_core.cli import main


class CompareOCREnginesCLITests(unittest.TestCase):
    def test_compare_ocr_engines_prints_json_for_default_engines_and_writes_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            drawing_path = root / "drawing.png"
            output_path = root / "compare.json"
            drawing_path.write_bytes(b"fake image")
            calls: list[str] = []

            def analyze_drawing_with_ocr(**kwargs):
                engine = kwargs["ocr_engine"]
                calls.append(engine)
                return _bundle(engine)

            buffer = io.StringIO()
            with (
                patch("minos_core.drawing_input.load_drawing_source", return_value={"path": str(drawing_path)}),
                patch("minos_core.drawing_input.render_drawing_pages", return_value=[]),
                patch(
                    "minos_core.drawing_ocr_analysis.analyze_drawing_with_ocr",
                    side_effect=analyze_drawing_with_ocr,
                ),
                redirect_stdout(buffer),
            ):
                code = main(
                    [
                        "compare-ocr-engines",
                        "--input",
                        str(drawing_path),
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertEqual(code, 0)
            self.assertEqual(calls, ["auto", "pdf_text", "rapidocr", "mineru"])
            stdout_payload = json.loads(buffer.getvalue())
            file_payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(stdout_payload, file_payload)
            self.assertEqual(stdout_payload["input"], str(drawing_path))
            self.assertEqual([item["engine"] for item in stdout_payload["results"]], calls)
            self.assertEqual(stdout_payload["results"][0]["drawing_number"], "AUTO-001")
            self.assertEqual(stdout_payload["results"][0]["part_name"], "auto bracket")
            self.assertEqual(stdout_payload["results"][0]["revision"], "A")
            self.assertEqual(stdout_payload["results"][0]["material_count"], 1)
            self.assertEqual(stdout_payload["results"][0]["special_characteristic_count"], 1)
            self.assertEqual(stdout_payload["results"][0]["dimension_count"], 2)
            self.assertEqual(stdout_payload["results"][0]["technical_requirement_count"], 1)
            self.assertEqual(stdout_payload["results"][0]["evidence_count"], 3)
            self.assertEqual(stdout_payload["results"][0]["ocr_text_length"], 42)
            self.assertEqual(stdout_payload["results"][0]["status"], "ok")
            self.assertIsNone(stdout_payload["results"][0]["error"])
            self.assertEqual(stdout_payload["results"][0]["engine"], "auto")
            self.assertEqual(stdout_payload["results"][1]["part_name"], "pdf_text bracket")
            self.assertEqual(stdout_payload["results"][2]["part_name"], "rapidocr bracket")
            self.assertEqual(stdout_payload["results"][3]["part_name"], "mineru bracket")

    def test_compare_ocr_engines_reports_engine_error_without_stopping_comparison(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            drawing_path = Path(tmpdir) / "drawing.png"
            drawing_path.write_bytes(b"fake image")

            def analyze_drawing_with_ocr(**kwargs):
                engine = kwargs["ocr_engine"]
                if engine == "rapidocr":
                    raise RuntimeError("rapidocr unavailable")
                return _bundle(engine)

            buffer = io.StringIO()
            with (
                patch("minos_core.drawing_input.load_drawing_source", return_value={"path": str(drawing_path)}),
                patch("minos_core.drawing_input.render_drawing_pages", return_value=[]),
                patch(
                    "minos_core.drawing_ocr_analysis.analyze_drawing_with_ocr",
                    side_effect=analyze_drawing_with_ocr,
                ),
                redirect_stdout(buffer),
            ):
                code = main(
                    [
                        "compare-ocr-engines",
                        "--input",
                        str(drawing_path),
                        "--engines",
                        "auto,pdf_text,rapidocr",
                    ]
                )

            self.assertEqual(code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertEqual([item["status"] for item in payload["results"]], ["ok", "ok", "error"])
            self.assertEqual(payload["results"][2]["engine"], "rapidocr")
            self.assertEqual(payload["results"][2]["error"], "rapidocr unavailable")
            self.assertIsNone(payload["results"][2]["drawing_number"])
            self.assertEqual(payload["results"][2]["evidence_count"], 0)


def _bundle(engine: str) -> dict:
    return {
        "drawing_identity": {
            "drawing_number": f"{engine.upper()}-001",
            "part_name": f"{engine} bracket",
            "revision": "A",
        },
        "materials": [{"name": "SPCC"}],
        "special_characteristics": [{"name": "CC"}],
        "dimensions": [{"name": "diameter"}, {"name": "length"}],
        "technical_requirements": [{"text": "deburr"}],
        "evidence": [{}, {}, {}],
        "metadata": {"ocr": {"text_length": 42}},
    }


if __name__ == "__main__":
    unittest.main()
