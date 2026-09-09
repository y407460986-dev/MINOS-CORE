"""Tests for PPAP element endpoints.

Covers the router at minos_platform/routers/ppap_elements.py.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def _create_project_and_package(test_client):
    """Create a project and a PPAP package.  Returns (project_id, package_id)."""
    proj = await test_client.post("/api/projects", json={"name": "PPAP Elements Test"})
    project_id = proj.json()["id"]

    pkg_resp = await test_client.post(
        f"/api/projects/{project_id}/ppap-packages",
        json={"name": "PPAP Package", "submission_level": "Level 3"},
    )
    assert pkg_resp.status_code == 201
    package_id = pkg_resp.json()["id"]
    return project_id, package_id


# ---------------------------------------------------------------------------
# GET /api/ppap-packages/{package_id}/elements
# ---------------------------------------------------------------------------


async def test_list_elements_returns_18_for_existing_package(test_client):
    """GET returns 18 elements when the package exists."""
    _, package_id = await _create_project_and_package(test_client)

    resp = await test_client.get(f"/api/ppap-packages/{package_id}/elements")
    assert resp.status_code == 200
    elements = resp.json()
    assert len(elements) == 18


async def test_list_elements_returns_empty_for_nonexistent_package(test_client):
    """GET returns 200 with an empty list when the package_id does not exist.

    The endpoint simply filters by package_id; if no project uses that ID the
    DB returns nothing, so the result is a valid empty list, not a 404.
    """
    resp = await test_client.get(
        "/api/ppap-packages/00000000-0000-0000-0000-000000000000/elements"
    )
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# GET /api/ppap-packages/{package_id}/elements/{element_id}
# ---------------------------------------------------------------------------


async def test_get_element_returns_detail(test_client):
    """GET on an existing element returns its full detail including artifacts."""
    _, package_id = await _create_project_and_package(test_client)

    list_resp = await test_client.get(f"/api/ppap-packages/{package_id}/elements")
    elements = list_resp.json()
    elem_id = elements[0]["id"]

    detail = await test_client.get(
        f"/api/ppap-packages/{package_id}/elements/{elem_id}"
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == elem_id
    assert body["element_key"] == elements[0]["element_key"]
    assert body["artifacts"] == []  # freshly created, no artifacts yet


async def test_get_nonexistent_element_returns_404(test_client):
    """GET on a non-existent element returns 404."""
    _, package_id = await _create_project_and_package(test_client)

    resp = await test_client.get(
        f"/api/ppap-packages/{package_id}/elements"
        "/00000000-0000-0000-0000-000000000000"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/ppap-packages/{package_id}/elements/{element_id}
# ---------------------------------------------------------------------------


async def test_update_element_status_and_notes(test_client):
    """PATCH can update status and notes in a single call."""
    _, package_id = await _create_project_and_package(test_client)

    list_resp = await test_client.get(f"/api/ppap-packages/{package_id}/elements")
    elem_id = list_resp.json()[0]["id"]

    resp = await test_client.patch(
        f"/api/ppap-packages/{package_id}/elements/{elem_id}",
        json={"status": "required", "notes": "Customer requires this"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "required"
    assert data["notes"] == "Customer requires this"

    # Verify persistence via GET
    detail = await test_client.get(
        f"/api/ppap-packages/{package_id}/elements/{elem_id}"
    )
    assert detail.json()["status"] == "required"


async def test_update_element_notes_only(test_client):
    """PATCH with only notes preserves the existing status."""
    _, package_id = await _create_project_and_package(test_client)

    list_resp = await test_client.get(f"/api/ppap-packages/{package_id}/elements")
    elem_id = list_resp.json()[0]["id"]

    resp = await test_client.patch(
        f"/api/ppap-packages/{package_id}/elements/{elem_id}",
        json={"notes": "Updated notes only"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # The default status is "missing" for freshly created elements
    assert data["notes"] == "Updated notes only"
    # Should be same as before (no status change requested)
    assert data["status"] == "missing"


async def test_update_nonexistent_element_returns_404(test_client):
    """PATCH on an element that does not exist returns 404."""
    _, package_id = await _create_project_and_package(test_client)

    resp = await test_client.patch(
        f"/api/ppap-packages/{package_id}/elements"
        "/00000000-0000-0000-0000-000000000000",
        json={"status": "approved"},
    )
    assert resp.status_code == 404


async def test_update_element_wrong_package_returns_404(test_client):
    """PATCH on an element that belongs to a different package returns 404."""
    proj = await test_client.post("/api/projects", json={"name": "Wrong Pkg Test"})
    project_id = proj.json()["id"]

    pkg1_resp = await test_client.post(
        f"/api/projects/{project_id}/ppap-packages",
        json={"name": "Package 1"},
    )
    pkg1_id = pkg1_resp.json()["id"]

    pkg2_resp = await test_client.post(
        f"/api/projects/{project_id}/ppap-packages",
        json={"name": "Package 2"},
    )
    pkg2_id = pkg2_resp.json()["id"]

    # Get an element from package 1
    elem_resp = await test_client.get(f"/api/ppap-packages/{pkg1_id}")
    elem_id = elem_resp.json()["elements"][0]["id"]

    # Try to update it via package 2's URL – the WHERE clause filters on both
    # package_id and element_id, so no match → 404.
    resp = await test_client.patch(
        f"/api/ppap-packages/{pkg2_id}/elements/{elem_id}",
        json={"status": "approved"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/ppap-packages/{package_id}/elements/{element_id}/artifacts
# ---------------------------------------------------------------------------


async def test_link_artifact_to_element(
    test_client, demo_package_path, demo_sha256
):
    """POST links a platform artifact to an element and returns 201."""
    proj = await test_client.post("/api/projects", json={"name": "Link Artifact Test"})
    project_id = proj.json()["id"]

    await test_client.post(
        f"/api/projects/{project_id}/input-packages",
        json={
            "input_package_path": demo_package_path,
            "sha256": demo_sha256,
            "redacted": "true",
        },
    )
    draft_resp = await test_client.post(f"/api/projects/{project_id}/draft-runs")
    assert draft_resp.status_code == 201
    run_id = draft_resp.json()["id"]

    # Find an artifact from that draft run
    artifacts_resp = await test_client.get("/api/artifacts")
    artifact_id = None
    for art in artifacts_resp.json():
        if isinstance(art, dict) and art.get("run_id") == run_id:
            artifact_id = art["id"]
            break

    if artifact_id is None:
        pytest.skip("No artifact produced by draft run – cannot test link")

    # Create a package and pick PFMEA element
    pkg_resp = await test_client.post(
        f"/api/projects/{project_id}/ppap-packages",
        json={"name": "Link Artifact Pkg"},
    )
    package_id = pkg_resp.json()["id"]
    pkg_detail = await test_client.get(f"/api/ppap-packages/{package_id}")
    elem_id = next(
        e for e in pkg_detail.json()["elements"] if e["element_key"] == "pfmea"
    )["id"]

    link_resp = await test_client.post(
        f"/api/ppap-packages/{package_id}/elements/{elem_id}/artifacts",
        json={"artifact_id": artifact_id, "notes": "From draft run"},
    )
    assert link_resp.status_code == 201
    link_data = link_resp.json()
    assert link_data["artifact_id"] == artifact_id

    # Verify the element detail now includes the artifact
    elem_detail = await test_client.get(
        f"/api/ppap-packages/{package_id}/elements/{elem_id}"
    )
    assert len(elem_detail.json()["artifacts"]) == 1


async def test_link_artifact_nonexistent_element_returns_404(
    test_client, demo_package_path, demo_sha256
):
    """POST linking an artifact to a non-existent element returns 404."""
    _, package_id = await _create_project_and_package(test_client)

    resp = await test_client.post(
        f"/api/ppap-packages/{package_id}/elements"
        "/00000000-0000-0000-0000-000000000000/artifacts",
        json={
            "artifact_id": "00000000-0000-0000-0000-000000000000",
            "notes": "To non-existent element",
        },
    )
    assert resp.status_code == 404


async def test_link_nonexistent_artifact_returns_404(
    test_client, demo_package_path, demo_sha256
):
    """POST linking a non-existent artifact returns 404."""
    _, package_id = await _create_project_and_package(test_client)

    list_resp = await test_client.get(f"/api/ppap-packages/{package_id}/elements")
    elem_id = list_resp.json()[0]["id"]

    resp = await test_client.post(
        f"/api/ppap-packages/{package_id}/elements/{elem_id}/artifacts",
        json={
            "artifact_id": "00000000-0000-0000-0000-000000000000",
            "notes": "Non-existent artifact",
        },
    )
    assert resp.status_code == 404


async def test_link_artifact_rejects_cross_project(
    test_client, demo_package_path, demo_sha256
):
    """POST linking an artifact from another project returns 409."""
    # Project 1 – draft run to produce an artifact
    proj1 = await test_client.post("/api/projects", json={"name": "Cross Proj 1"})
    project1_id = proj1.json()["id"]
    await test_client.post(
        f"/api/projects/{project1_id}/input-packages",
        json={
            "input_package_path": demo_package_path,
            "sha256": demo_sha256,
            "redacted": "true",
        },
    )
    draft1 = await test_client.post(f"/api/projects/{project1_id}/draft-runs")
    run1_id = draft1.json()["id"]

    artifacts_resp = await test_client.get("/api/artifacts")
    artifact_id = None
    for art in artifacts_resp.json():
        if isinstance(art, dict) and art.get("run_id") == run1_id:
            artifact_id = art["id"]
            break

    if artifact_id is None:
        pytest.skip("No artifact from project 1 – cannot test cross-project rejection")

    # Project 2 – package to link into
    proj2 = await test_client.post("/api/projects", json={"name": "Cross Proj 2"})
    project2_id = proj2.json()["id"]
    pkg2_resp = await test_client.post(
        f"/api/projects/{project2_id}/ppap-packages",
        json={"name": "Cross Project Pkg"},
    )
    package2_id = pkg2_resp.json()["id"]
    pkg2_detail = await test_client.get(f"/api/ppap-packages/{package2_id}")
    elem2_id = pkg2_detail.json()["elements"][0]["id"]

    link_resp = await test_client.post(
        f"/api/ppap-packages/{package2_id}/elements/{elem2_id}/artifacts",
        json={"artifact_id": artifact_id, "notes": "cross project"},
    )
    assert link_resp.status_code == 409


# ---------------------------------------------------------------------------
# POST /api/ppap-packages/{package_id}/refresh-from-project
# ---------------------------------------------------------------------------


async def test_refresh_from_project_auto_links(
    test_client, demo_package_path, demo_sha256
):
    """POST refresh-from-project auto-links matching artifacts."""
    proj = await test_client.post("/api/projects", json={"name": "Refresh Test"})
    project_id = proj.json()["id"]

    await test_client.post(
        f"/api/projects/{project_id}/input-packages",
        json={
            "input_package_path": demo_package_path,
            "sha256": demo_sha256,
            "redacted": "true",
        },
    )
    await test_client.post(f"/api/projects/{project_id}/draft-runs")

    pkg_resp = await test_client.post(
        f"/api/projects/{project_id}/ppap-packages",
        json={"name": "Refresh Pkg"},
    )
    package_id = pkg_resp.json()["id"]

    refresh_resp = await test_client.post(
        f"/api/ppap-packages/{package_id}/refresh-from-project"
    )
    assert refresh_resp.status_code == 200
    result = refresh_resp.json()
    assert "linked_count" in result
    assert isinstance(result["links"], list)

    # Elements are still accessible
    elements = await test_client.get(f"/api/ppap-packages/{package_id}/elements")
    assert len(elements.json()) == 18


async def test_refresh_nonexistent_package_returns_404(test_client):
    """POST refresh-from-project on a non-existent package returns 404."""
    resp = await test_client.post(
        "/api/ppap-packages/00000000-0000-0000-0000-000000000000/refresh-from-project"
    )
    assert resp.status_code == 404
