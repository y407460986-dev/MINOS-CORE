"""Shared pytest fixtures for minos_platform tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from minos_platform import db

ROOT = Path(__file__).resolve().parents[2]
DEMO_PACKAGE = ROOT / "tests" / "fixtures" / "demo_input_package"


@pytest.fixture
async def test_client():
    """Provide an AsyncClient wired to a test platform app with a temp DB.

    Initializes a temporary SQLite DB before the client is available and
    cleans up the engine after the test completes.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_platform.sqlite3"
        db_url = f"sqlite+aiosqlite:///{db_path}"
        # Initialize the test DB before the client starts its lifespan
        await db.init_db(db_url)

        from minos_platform.app import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        # Teardown: close the test engine
        if db._engine is not None:
            await db._engine.dispose()
            db._engine = None
            db._session_factory = None


@pytest.fixture
def test_artifacts_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def demo_package_path():
    return str(DEMO_PACKAGE)


@pytest.fixture
def realistic_package_path():
    return str(ROOT / "tests" / "fixtures" / "realistic_input_package")


@pytest.fixture
def demo_sha256():
    # Real SHA256 of tests/fixtures/demo_input_package (directory hash)
    return "f96b1b7a734767929e90d07430de96fb5e6362553af424141cc37a3d4ed40442"


@pytest.fixture
def realistic_sha256():
    # Placeholder — real value depends on realistic_input_package content
    return "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3"