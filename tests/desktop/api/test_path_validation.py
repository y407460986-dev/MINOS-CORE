from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from minos_desktop.api.app import create_app

pytestmark = pytest.mark.asyncio


def _pdf(path):
    path.write_bytes(b"%PDF-1.7\n% test\n")
    return path


def _png(path):
    path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")
    return path


async def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("MINOS_DESKTOP_API_TOKEN", "test-token")
    app = create_app(db_path=tmp_path / "desktop.sqlite3", output_dir=tmp_path / "out")
    transport = ASGITransport(app=app)
    return AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer test-token"},
    )


async def test_create_project_rejects_missing_drawing_path(tmp_path, monkeypatch):
    async with await _client(tmp_path, monkeypatch) as client:
        response = await client.post(
            "/api/projects",
            json={
                "project_name": "missing drawing",
                "drawing_path": str(tmp_path / "missing.pdf"),
                "output_dir": str(tmp_path / "out"),
            },
        )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


async def test_create_project_rejects_disallowed_drawing_extension(tmp_path, monkeypatch):
    drawing = tmp_path / "drawing.txt"
    drawing.write_text("not a drawing", encoding="utf-8")

    async with await _client(tmp_path, monkeypatch) as client:
        response = await client.post(
            "/api/projects",
            json={
                "project_name": "bad extension",
                "drawing_path": str(drawing),
                "output_dir": str(tmp_path / "out"),
            },
        )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


async def test_create_project_rejects_magic_number_mismatch(tmp_path, monkeypatch):
    drawing = tmp_path / "fake.pdf"
    drawing.write_text("not really a pdf", encoding="utf-8")

    async with await _client(tmp_path, monkeypatch) as client:
        response = await client.post(
            "/api/projects",
            json={
                "project_name": "bad magic",
                "drawing_path": str(drawing),
                "output_dir": str(tmp_path / "out"),
            },
        )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


async def test_create_project_rejects_null_byte_output_dir(tmp_path, monkeypatch):
    drawing = _pdf(tmp_path / "drawing.pdf")

    async with await _client(tmp_path, monkeypatch) as client:
        response = await client.post(
            "/api/projects",
            json={
                "project_name": "bad output",
                "drawing_path": str(drawing),
                "output_dir": f"{tmp_path}\x00bad",
            },
        )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


async def test_create_project_rejects_output_dir_that_is_file(tmp_path, monkeypatch):
    drawing = _pdf(tmp_path / "drawing.pdf")
    output_file = tmp_path / "out.txt"
    output_file.write_text("not a directory", encoding="utf-8")

    async with await _client(tmp_path, monkeypatch) as client:
        response = await client.post(
            "/api/projects",
            json={
                "project_name": "file output",
                "drawing_path": str(drawing),
                "output_dir": str(output_file),
            },
        )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


async def test_create_project_accepts_pdf_png_jpg_components_and_normalizes_paths(
    tmp_path, monkeypatch
):
    drawing = _pdf(tmp_path / "drawing.pdf")
    component = _png(tmp_path / "component.png")
    output_dir = tmp_path / "out"

    async with await _client(tmp_path, monkeypatch) as client:
        response = await client.post(
            "/api/projects",
            json={
                "project_name": "good drawing",
                "drawing_path": str(drawing),
                "component_drawings": [str(component)],
                "output_dir": str(output_dir),
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["drawing_path"] == str(drawing.resolve())
    assert body["component_drawings"] == [str(component.resolve())]
    assert body["output_dir"] == str(output_dir.resolve())


async def test_default_output_dir_rejects_file_path(tmp_path, monkeypatch):
    output_file = tmp_path / "default-output.txt"
    output_file.write_text("not a directory", encoding="utf-8")

    async with await _client(tmp_path, monkeypatch) as client:
        response = await client.patch(
            "/api/settings/default-output-dir",
            json={"output_dir": str(output_file)},
        )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
