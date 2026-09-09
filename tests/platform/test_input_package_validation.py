"""Tests for input package validation (SHA256, path existence)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_sha256_mismatch_rejected(test_client, demo_package_path):
    """Submitting an input package with wrong sha256 returns 422 with code SHA256_MISMATCH."""
    proj = await test_client.post("/api/projects", json={"name": "SHA256 Mismatch Test"})
    project_id = proj.json()["id"]

    # Use a deliberately wrong hash that will never match the actual file
    wrong_sha256 = "0000000000000000000000000000000000000000000000000000000000000000"

    resp = await test_client.post(
        f"/api/projects/{project_id}/input-packages",
        json={
            "input_package_path": demo_package_path,
            "sha256": wrong_sha256,
            "redacted": "true",
        },
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "SHA256_MISMATCH"


async def test_input_package_not_found(test_client):
    """Submitting a non-existent input package path returns 404 with code INPUT_PACKAGE_NOT_FOUND."""
    proj = await test_client.post("/api/projects", json={"name": "Input Package Not Found Test"})
    project_id = proj.json()["id"]

    resp = await test_client.post(
        f"/api/projects/{project_id}/input-packages",
        json={
            "input_package_path": "/tmp/this/path/does/not/exist/package.json",
            "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "redacted": "true",
        },
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "INPUT_PACKAGE_NOT_FOUND"
