"""Coverage for platform artifact router and utility helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minos_platform import utils


def test_utils_copy_and_parse_review_patch(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "review.json").write_text(json.dumps({"items": []}), encoding="utf-8")
    dest_dir = tmp_path / "artifacts"

    copied = utils.safe_copy_input_file_or_dir(str(source_dir), dest_dir)
    (source_dir / "review.json").write_text("{bad", encoding="utf-8")
    copied_again = utils.safe_copy_input_file_or_dir(str(source_dir), dest_dir)

    assert copied == copied_again
    assert utils.parse_review_patch(copied_again / "review.json") is None
    assert utils.parse_review_patch(copied / "missing.json") is None


def test_artifact_dir_helpers_create_project_and_run_dirs(tmp_path):
    project_dir = utils.resolve_project_artifact_dir("project-1", tmp_path)
    run_dir = utils.resolve_project_run_artifact_dir("project-1", "run-1", tmp_path)

    assert project_dir == tmp_path / "project-1" / "inputs"
    assert run_dir == tmp_path / "project-1" / "runs" / "run-1"
    assert project_dir.is_dir()
    assert run_dir.is_dir()


@pytest.mark.asyncio
async def test_artifact_router_reports_missing_file_on_disk(test_client, demo_package_path, demo_sha256):
    proj = await test_client.post("/api/projects", json={"name": "Artifact Missing File Test"})
    project_id = proj.json()["id"]
    await test_client.post(
        f"/api/projects/{project_id}/input-packages",
        json={"input_package_path": demo_package_path, "sha256": demo_sha256, "redacted": "true"},
    )
    await test_client.post(f"/api/projects/{project_id}/draft-runs")
    export_resp = await test_client.post(
        f"/api/projects/{project_id}/exports",
        json={"export_mode": "draft"},
    )
    export_path = Path(export_resp.json()["export_path"])

    artifacts_resp = await test_client.get("/api/artifacts")
    artifact = next(item for item in artifacts_resp.json() if item["file_path"] == str(export_path))
    export_path.unlink()

    download_resp = await test_client.get(f"/api/artifacts/{artifact['id']}")

    assert download_resp.status_code == 404
    assert "Artifact file not found on disk" in download_resp.json()["detail"]
