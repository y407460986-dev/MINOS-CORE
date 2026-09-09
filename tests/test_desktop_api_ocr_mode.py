from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient

from minos_desktop.api.app import create_app

TEST_API_TOKEN = "test-token"


def _client(transport: ASGITransport) -> AsyncClient:
    return AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {TEST_API_TOKEN}"},
    )


class DesktopApiOCRModeTests(unittest.TestCase):
    def test_project_create_preserves_explicit_ocr_modes(self) -> None:
        for ocr_engine in ("rapidocr", "pdf_text", "mineru"):
            with self.subTest(ocr_engine=ocr_engine):
                asyncio.run(self._project_create_preserves_explicit_ocr_mode(ocr_engine))

    async def _project_create_preserves_explicit_ocr_mode(self, ocr_engine: str) -> None:
        with (
            patch.dict(os.environ, {"MINOS_DESKTOP_API_TOKEN": TEST_API_TOKEN}),
            tempfile.TemporaryDirectory() as tmpdir,
        ):
            root = Path(tmpdir)
            db_path = root / "desktop.sqlite3"
            output_dir = root / "out"
            drawing_file = root / "drawing.pdf"
            drawing_file.write_bytes(b"%PDF-1.4 test file\n")
            app = create_app(db_path=db_path, output_dir=output_dir)
            transport = ASGITransport(app=app)
            async with _client(transport) as client:
                response = await client.post(
                    "/api/projects",
                    json={
                        "project_name": "显式 OCR 项目",
                        "drawing_path": str(drawing_file),
                        "output_dir": str(output_dir),
                        "ocr_engine": ocr_engine,
                    },
                )

            self.assertEqual(response.status_code, 201)
            project_body = response.json()
            self.assertEqual(project_body["ocr_engine"], ocr_engine)
            self.assertEqual(project_body["context"]["ocr_engine"], ocr_engine)

    def test_project_create_defaults_to_mineru_ocr_mode(self) -> None:
        asyncio.run(self._project_create_defaults_to_mineru_ocr_mode())

    async def _project_create_defaults_to_mineru_ocr_mode(self) -> None:
        captured: dict[str, object] = {}

        with (
            patch.dict(os.environ, {"MINOS_DESKTOP_API_TOKEN": TEST_API_TOKEN}),
            tempfile.TemporaryDirectory() as tmpdir,
        ):
            root = Path(tmpdir)
            db_path = root / "desktop.sqlite3"
            output_dir = root / "out"
            drawing_file = root / "drawing.pdf"
            drawing_file.write_bytes(b"%PDF-1.4 test file\n")
            app = create_app(db_path=db_path, output_dir=output_dir)
            transport = ASGITransport(app=app)
            async with _client(transport) as client:
                response = await client.post(
                    "/api/projects",
                    json={
                        "project_name": "默认 OCR 项目",
                        "drawing_path": str(drawing_file),
                        "output_dir": str(output_dir),
                    },
                )

            self.assertEqual(response.status_code, 201)
            project_body = response.json()
            self.assertEqual(project_body["analysis_mode"], "hybrid")
            self.assertEqual(project_body["ocr_engine"], "mineru")
            self.assertEqual(project_body["context"]["analysis_mode"], "hybrid")
            self.assertEqual(project_body["context"]["ocr_engine"], "mineru")

            with patch(
                "minos_desktop.services.run_service.analyze_drawing_for_three_table_chain",
                side_effect=_capturing_analysis(captured),
            ):
                with patch(
                    "minos_core.pipeline_chain.generate_pfd_from_drawing",
                    return_value={
                        "steps": [
                            {
                                "process_step_id": "P10",
                                "operation": "来料检验",
                                "needs_confirmation": True,
                            }
                        ]
                    },
                ):
                    async with _client(transport) as client:
                        run_response = await client.post(
                            f"/api/projects/{project_body['id']}/runs"
                        )

        self.assertEqual(run_response.status_code, 201)
        self.assertEqual(captured["analysis_mode"], "hybrid")
        self.assertEqual(captured["ocr_engine"], "mineru")
        self.assertEqual(captured["component_drawings"], [])
        self.assertIs(captured["context"]["special_characteristic_judge_enabled"], True)

    def test_project_create_stores_ocr_mode_and_chain_run_passes_it(self) -> None:
        asyncio.run(self._project_create_stores_ocr_mode_and_chain_run_passes_it())

    async def _project_create_stores_ocr_mode_and_chain_run_passes_it(self) -> None:
        captured: dict[str, object] = {}

        with (
            patch.dict(os.environ, {"MINOS_DESKTOP_API_TOKEN": TEST_API_TOKEN}),
            tempfile.TemporaryDirectory() as tmpdir,
        ):
            root = Path(tmpdir)
            db_path = root / "desktop.sqlite3"
            output_dir = root / "out"
            drawing_file = root / "drawing.pdf"
            drawing_file.write_bytes(b"%PDF-1.4 test file\n")
            app = create_app(db_path=db_path, output_dir=output_dir)
            transport = ASGITransport(app=app)
            async with _client(transport) as client:
                response = await client.post(
                    "/api/projects",
                    json={
                        "project_name": "OCR 项目",
                        "drawing_path": str(drawing_file),
                        "output_dir": str(output_dir),
                        "analysis_mode": "ocr_only",
                        "ocr_engine": "mineru",
                        "context": {"part_no": "A-001"},
                    },
                )

            self.assertEqual(response.status_code, 201)
            project_body = response.json()
            self.assertEqual(project_body["analysis_mode"], "ocr_only")
            self.assertEqual(project_body["ocr_engine"], "mineru")
            self.assertEqual(project_body["context"]["analysis_mode"], "ocr_only")
            self.assertEqual(project_body["context"]["ocr_engine"], "mineru")
            with patch(
                "minos_desktop.services.run_service.analyze_drawing_for_three_table_chain",
                side_effect=_capturing_analysis(captured),
            ):
                with patch(
                    "minos_core.pipeline_chain.generate_pfd_from_drawing",
                    return_value={
                        "steps": [
                            {
                                "process_step_id": "P10",
                                "operation": "来料检验",
                                "needs_confirmation": True,
                            }
                        ]
                    },
                ):
                    async with _client(transport) as client:
                        run_response = await client.post(
                            f"/api/projects/{project_body['id']}/runs"
                        )

        self.assertEqual(run_response.status_code, 201)
        run_body = run_response.json()
        self.assertEqual(run_body["status"], "needs_review")
        self.assertEqual(run_body["pipeline_mode"], "chain")
        self.assertEqual(run_body["chain_stages"]["pfd"]["status"], "generated")
        self.assertEqual(run_body["current_result"]["pfmea"]["rows"], [])
        self.assertEqual(run_body["current_result"]["control_plan"]["rows"], [])
        self.assertEqual(captured["analysis_mode"], "ocr_only")
        self.assertEqual(captured["ocr_engine"], "mineru")
        self.assertEqual(captured["component_drawings"], [])
        self.assertEqual(captured["context"]["part_no"], "A-001")
        self.assertEqual(captured["context"]["analysis_mode"], "ocr_only")


def _capturing_analysis(captured: dict[str, object]):
    def analyze(
        drawing_path: str,
        output_dir: str,
        *,
        context: dict,
        analysis_mode: str,
        ocr_engine: str,
        component_drawings: list[str] | None = None,
    ) -> dict[str, object]:
        captured["drawing_path"] = drawing_path
        captured["output_dir"] = output_dir
        captured["context"] = dict(context)
        captured["analysis_mode"] = analysis_mode
        captured["ocr_engine"] = ocr_engine
        captured["component_drawings"] = list(component_drawings or [])
        return {
            "drawing_analysis": _fake_result()["drawing_analysis"],
            "drawing_gate": _PassingGate(),
            "part_family_classification": {"family_key": "door_hinge"},
            "family_context": {"family_key": "door_hinge"},
        }

    return analyze


class _PassingGate:
    can_continue = True

    def model_dump(self) -> dict[str, object]:
        return {"can_continue": True}


def _fake_result() -> dict[str, object]:
    return {
        "document_type": "three_table_generation_result",
        "schema_version": "minos-core.three_table_generation_result.v1",
        "status": "needs_review",
        "status_display": "待人工复核",
        "blocked_stage": None,
        "drawing_analysis": {"metadata": {"analysis_source": "ocr"}},
        "process_flow": {"steps": []},
        "pfmea": {"rows": []},
        "control_plan": {"rows": []},
        "quality_gate": {},
        "quality_gates": {},
        "exports": {},
        "manifest": {"run_id": "ocr-test", "path": "manifest.json"},
        "manual_review": {"required": True, "items": []},
        "warnings": [],
    }


if __name__ == "__main__":
    unittest.main()
