from __future__ import annotations

import time

import pytest
from httpx import ASGITransport, AsyncClient

from minos_desktop.api.app import create_app
from minos_desktop.api.auth import create_stream_token


async def _stream_response(tmp_path, monkeypatch, stream_token: str | None):
    monkeypatch.setenv("MINOS_DESKTOP_API_TOKEN", "desktop-api-token")
    app = create_app(db_path=tmp_path / "desktop.sqlite3", output_dir=tmp_path / "out")
    transport = ASGITransport(app=app)
    params = {}
    if stream_token is not None:
        params["stream_token"] = stream_token
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/runs/1/chain/pfmea/stream", params=params)


@pytest.mark.asyncio
async def test_sse_stream_rejects_missing_token(tmp_path, monkeypatch):
    response = await _stream_response(tmp_path, monkeypatch, None)

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_sse_stream_rejects_wrong_token(tmp_path, monkeypatch):
    response = await _stream_response(tmp_path, monkeypatch, "not-a-real-stream-token")

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_sse_stream_accepts_valid_stream_token(tmp_path, monkeypatch):
    monkeypatch.setenv("MINOS_DESKTOP_API_TOKEN", "desktop-api-token")
    stream_token = create_stream_token()

    response = await _stream_response(tmp_path, monkeypatch, stream_token)

    assert response.status_code == 200
    assert "event: done" in response.text


@pytest.mark.asyncio
async def test_sse_stream_rejects_expired_stream_token(tmp_path, monkeypatch):
    monkeypatch.setenv("MINOS_DESKTOP_API_TOKEN", "desktop-api-token")
    stream_token = create_stream_token(now=int(time.time()) - 120)

    response = await _stream_response(tmp_path, monkeypatch, stream_token)

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_frontend_sse_url_uses_stream_token_query() -> None:
    source = (
        __import__("pathlib").Path(__file__).resolve().parents[3]
        / "apps"
        / "desktop-tauri"
        / "src"
        / "api"
        / "sse-client.ts"
    ).read_text(encoding="utf-8")

    assert "getStreamToken" in source
    assert "stream_token" in source
    assert "new EventSource(url)" in source
