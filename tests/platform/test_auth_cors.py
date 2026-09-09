from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from minos_platform import db

pytestmark = pytest.mark.asyncio


async def _client():
    tmpdir = tempfile.TemporaryDirectory()
    db_path = Path(tmpdir.name) / "test_platform.sqlite3"
    await db.init_db(f"sqlite+aiosqlite:///{db_path}")
    from minos_platform.app import app

    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    return tmpdir, client


async def _cleanup(tmpdir: tempfile.TemporaryDirectory[str]) -> None:
    if db._engine is not None:
        await db._engine.dispose()
        db._engine = None
        db._session_factory = None
    tmpdir.cleanup()


async def test_platform_auth_required_rejects_missing_configured_token(monkeypatch):
    monkeypatch.setenv("MINOS_PLATFORM_AUTH_REQUIRED", "1")
    monkeypatch.delenv("MINOS_PLATFORM_API_TOKEN", raising=False)
    tmpdir, client = await _client()
    try:
        async with client:
            response = await client.get("/api/projects")
    finally:
        await _cleanup(tmpdir)

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize(
    ("auth_required", "expected_status"),
    [
        ("", 401),
        ("1", 401),
        ("true", 401),
        ("0", 200),
        ("false", 200),
        ("no", 200),
        ("off", 200),
    ],
)
async def test_platform_auth_flag_is_fail_closed_without_token(
    monkeypatch, auth_required, expected_status
):
    monkeypatch.setenv("MINOS_PLATFORM_AUTH_REQUIRED", auth_required)
    monkeypatch.delenv("MINOS_PLATFORM_API_TOKEN", raising=False)
    tmpdir, client = await _client()
    try:
        async with client:
            response = await client.get("/api/projects")
    finally:
        await _cleanup(tmpdir)

    assert response.status_code == expected_status


async def test_platform_auth_required_by_default_without_auth_env(monkeypatch):
    monkeypatch.delenv("MINOS_PLATFORM_AUTH_REQUIRED", raising=False)
    monkeypatch.delenv("MINOS_PLATFORM_API_TOKEN", raising=False)
    tmpdir, client = await _client()
    try:
        async with client:
            response = await client.get("/api/projects")
    finally:
        await _cleanup(tmpdir)

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


async def test_platform_auth_explicitly_disabled_allows_requests(monkeypatch):
    monkeypatch.setenv("MINOS_PLATFORM_AUTH_REQUIRED", "0")
    monkeypatch.delenv("MINOS_PLATFORM_API_TOKEN", raising=False)
    tmpdir, client = await _client()
    try:
        async with client:
            response = await client.get("/api/projects")
    finally:
        await _cleanup(tmpdir)

    assert response.status_code == 200


async def test_platform_auth_required_checks_bearer_token(monkeypatch):
    monkeypatch.setenv("MINOS_PLATFORM_AUTH_REQUIRED", "1")
    monkeypatch.setenv("MINOS_PLATFORM_API_TOKEN", "platform-secret")
    tmpdir, client = await _client()
    try:
        async with client:
            missing = await client.get("/api/projects")
            wrong = await client.get(
                "/api/projects",
                headers={"Authorization": "Bearer wrong"},
            )
            accepted = await client.get(
                "/api/projects",
                headers={"Authorization": "Bearer platform-secret"},
            )
    finally:
        await _cleanup(tmpdir)

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert accepted.status_code == 200


async def test_platform_auth_required_allows_cors_preflight(monkeypatch):
    monkeypatch.setenv("MINOS_PLATFORM_AUTH_REQUIRED", "1")
    monkeypatch.setenv("MINOS_PLATFORM_API_TOKEN", "platform-secret")
    tmpdir, client = await _client()
    try:
        async with client:
            response = await client.options(
                "/api/projects",
                headers={
                    "Origin": "http://127.0.0.1:1420",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "authorization,content-type",
                },
            )
    finally:
        await _cleanup(tmpdir)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:1420"


async def test_platform_default_auth_allows_cors_preflight_without_token(monkeypatch):
    monkeypatch.delenv("MINOS_PLATFORM_AUTH_REQUIRED", raising=False)
    monkeypatch.delenv("MINOS_PLATFORM_API_TOKEN", raising=False)
    tmpdir, client = await _client()
    try:
        async with client:
            response = await client.options(
                "/api/projects",
                headers={
                    "Origin": "http://127.0.0.1:1420",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "authorization,content-type",
                },
            )
    finally:
        await _cleanup(tmpdir)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:1420"


async def test_platform_cors_rejects_unlisted_localhost_port(monkeypatch):
    monkeypatch.setenv("MINOS_PLATFORM_AUTH_REQUIRED", "0")
    monkeypatch.delenv("MINOS_PLATFORM_API_TOKEN", raising=False)
    tmpdir, client = await _client()
    try:
        async with client:
            response = await client.options(
                "/api/projects",
                headers={
                    "Origin": "http://localhost:9999",
                    "Access-Control-Request-Method": "GET",
                },
            )
    finally:
        await _cleanup(tmpdir)

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


async def test_platform_endpoint_fixture_explicitly_disables_auth(test_client):
    response = await test_client.get("/api/projects")

    assert response.status_code == 200
