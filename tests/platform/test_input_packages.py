"""Tests for POST /api/projects/{project_id}/input-packages."""

from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def imported_demo_package(tmp_path, monkeypatch, demo_package_path):
    """Copy the shared fixture under the platform's trusted import root."""
    import_root = tmp_path / "imports"
    import_root.mkdir()
    monkeypatch.setenv("MINOS_PLATFORM_IMPORT_ROOT", str(import_root))
    package_path = import_root / "demo_input_package"
    shutil.copytree(demo_package_path, package_path)
    return str(package_path)


async def test_register_input_package_success(
    test_client, imported_demo_package, demo_sha256
):
    """Registering a valid input package on a created project returns 201."""
    # Arrange
    proj = await test_client.post("/api/projects", json={"name": "Success Test"})
    project_id = proj.json()["id"]

    # Act
    resp = await test_client.post(
        f"/api/projects/{project_id}/input-packages",
        json={
            "input_package_path": imported_demo_package,
            "sha256": demo_sha256,
            "redacted": "true",
        },
    )

    # Assert
    assert resp.status_code == 201
    body = resp.json()
    assert body["package_path"].endswith("demo_input_package")
    assert body["sha256"] == demo_sha256
    assert body["redacted"] == "true"
    assert "id" in body
    assert "created_at" in body


async def test_register_input_package_non_existent_project(
    test_client, demo_package_path, demo_sha256
):
    """Registering an input package on a non-existent project returns 404 with NOT_FOUND_PROJECT."""
    # Act
    resp = await test_client.post(
        "/api/projects/00000000-0000-0000-0000-000000000000/input-packages",
        json={
            "input_package_path": demo_package_path,
            "sha256": demo_sha256,
            "redacted": "true",
        },
    )

    # Assert
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND_PROJECT"


@pytest.mark.usefixtures("imported_demo_package")
async def test_register_input_package_rejects_source_outside_import_root(
    test_client, demo_package_path, demo_sha256
):
    """Registering a source outside the trusted import root returns 422."""
    proj = await test_client.post("/api/projects", json={"name": "Outside Root Test"})
    project_id = proj.json()["id"]

    resp = await test_client.post(
        f"/api/projects/{project_id}/input-packages",
        json={
            "input_package_path": str(demo_package_path),
            "sha256": demo_sha256,
            "redacted": "true",
        },
    )

    assert resp.status_code == 422
    assert resp.json()["code"] == "INVALID_INPUT_PATH"


async def test_register_input_package_wrong_state(
    test_client, imported_demo_package, demo_sha256
):
    """Registering an input package when the project is not in 'created' state returns 409."""
    # Arrange — create project and register input to advance state to "input_registered"
    proj = await test_client.post("/api/projects", json={"name": "Wrong State Test"})
    project_id = proj.json()["id"]

    first = await test_client.post(
        f"/api/projects/{project_id}/input-packages",
        json={
            "input_package_path": imported_demo_package,
            "sha256": demo_sha256,
            "redacted": "true",
        },
    )
    assert first.status_code == 201  # sanity: first registration must succeed

    # Act — second registration while project is in "input_registered" state
    resp = await test_client.post(
        f"/api/projects/{project_id}/input-packages",
        json={
            "input_package_path": imported_demo_package,
            "sha256": demo_sha256,
            "redacted": "true",
        },
    )

    # Assert
    assert resp.status_code == 409
    assert resp.json()["code"] == "INVALID_STATE_TRANSITION"
