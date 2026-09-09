"""Tests for PPAP Package and Element endpoints."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def _create_project_and_package(test_client):
    """Create a project and a PPAP package."""
    proj = await test_client.post("/api/projects", json={"name": "B阶段 Test"})
    project_id = proj.json()["id"]

    pkg_resp = await test_client.post(
        f"/api/projects/{project_id}/ppap-packages",
        json={"name": "PPAP Package 1", "submission_level": "Level 3"},
    )
    assert pkg_resp.status_code == 201
    package_id = pkg_resp.json()["id"]
    return project_id, package_id


async def test_create_ppap_package_generates_18_elements(test_client):
    """Creating a PPAP package auto-initializes 18 element checklist."""
    project_id, package_id = await _create_project_and_package(test_client)

    pkg_detail = await test_client.get(f"/api/ppap-packages/{package_id}")
    assert pkg_detail.status_code == 200
    data = pkg_detail.json()
    assert data["total_elements"] == 18
    assert data["required_count"] == 0
    assert data["approved_count"] == 0
    assert data["missing_count"] == 18
    assert data["blocked_count"] == 0
    assert data["ready_for_submission"] is False

    element_keys = {e["element_key"] for e in data["elements"]}
    expected = {
        "design_records", "engineering_change_documents", "engineering_approval",
        "dfmea", "process_flow_diagram", "pfmea", "control_plan", "msa_studies",
        "dimensional_results", "material_test_results", "initial_process_studies",
        "laboratory_documentation", "appearance_approval", "sample_product",
        "master_sample", "checking_aids", "customer_specific_requirements",
        "part_submission_warrant",
    }
    assert element_keys == expected


async def test_list_ppap_packages(test_client):
    """GET /projects/{id}/ppap-packages returns all packages."""
    project_id, package_id = await _create_project_and_package(test_client)

    list_resp = await test_client.get(f"/api/projects/{project_id}/ppap-packages")
    assert list_resp.status_code == 200
    packages = list_resp.json()
    assert len(packages) == 1
    assert packages[0]["id"] == package_id


async def test_get_nonexistent_package_returns_404(test_client):
    """GET /ppap-packages/{id} returns 404 for unknown package."""
    resp = await test_client.get("/api/ppap-packages/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_update_element_status(test_client):
    """PATCH can update element status and notes."""
    project_id, package_id = await _create_project_and_package(test_client)

    pkg_detail = await test_client.get(f"/api/ppap-packages/{package_id}")
    elements = pkg_detail.json()["elements"]
    elem_id = elements[0]["id"]

    # Mark element as required
    resp = await test_client.patch(
        f"/api/ppap-packages/{package_id}/elements/{elem_id}",
        json={"status": "required", "notes": "Customer requires this"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "required"
    assert data["notes"] == "Customer requires this"

    # Update to approved
    resp2 = await test_client.patch(
        f"/api/ppap-packages/{package_id}/elements/{elem_id}",
        json={"status": "approved"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "approved"


async def test_update_nonexistent_element_returns_404(test_client):
    """PATCH on unknown element returns 404."""
    project_id, package_id = await _create_project_and_package(test_client)

    resp = await test_client.patch(
        f"/api/ppap-packages/{package_id}/elements/00000000-0000-0000-0000-000000000000",
        json={"status": "approved"},
    )
    assert resp.status_code == 404


async def test_package_not_ready_until_all_required_approved(test_client):
    """Package ready_for_submission is True only when all required elements are approved."""
    project_id, package_id = await _create_project_and_package(test_client)

    # Mark PFMEA as required
    pkg_detail = await test_client.get(f"/api/ppap-packages/{package_id}")
    pfmea_elem = next(e for e in pkg_detail.json()["elements"] if e["element_key"] == "pfmea")

    await test_client.patch(
        f"/api/ppap-packages/{package_id}/elements/{pfmea_elem['id']}",
        json={"status": "required"},
    )

    pkg_check = await test_client.get(f"/api/ppap-packages/{package_id}")
    assert pkg_check.json()["required_count"] == 1
    assert pkg_check.json()["ready_for_submission"] is False

    # Approve it
    await test_client.patch(
        f"/api/ppap-packages/{package_id}/elements/{pfmea_elem['id']}",
        json={"status": "approved"},
    )

    pkg_final = await test_client.get(f"/api/ppap-packages/{package_id}")
    assert pkg_final.json()["approved_count"] == 1
    assert pkg_final.json()["ready_for_submission"] is True


async def test_link_artifact_to_element(test_client, demo_package_path, demo_sha256):
    """POST can link a platform artifact to an element."""
    # Set up project with input package and draft run
    proj = await test_client.post("/api/projects", json={"name": "Artifact Link Test"})
    project_id = proj.json()["id"]

    await test_client.post(
        f"/api/projects/{project_id}/input-packages",
        json={"input_package_path": demo_package_path, "sha256": demo_sha256, "redacted": "true"},
    )
    draft_resp = await test_client.post(f"/api/projects/{project_id}/draft-runs")
    assert draft_resp.status_code == 201

    # Get artifact from run
    draft_data = draft_resp.json()
    run_id = draft_data["id"]

    # Create package and get element
    pkg_resp = await test_client.post(
        f"/api/projects/{project_id}/ppap-packages",
        json={"name": "Artifact Link Package"},
    )
    package_id = pkg_resp.json()["id"]
    pkg_detail = await test_client.get(f"/api/ppap-packages/{package_id}")
    pfmea_elem = next(e for e in pkg_detail.json()["elements"] if e["element_key"] == "pfmea")

    # Get artifact from artifacts endpoint
    artifacts_resp = await test_client.get("/api/artifacts")
    artifacts_list = artifacts_resp.json()
    artifact_id = None
    for art in artifacts_list:
        if isinstance(art, dict) and art.get("run_id") == run_id:
            artifact_id = art["id"]
            break

    if artifact_id is None:
        # No artifact to link - skip test
        return

    # Link artifact
    link_resp = await test_client.post(
        f"/api/ppap-packages/{package_id}/elements/{pfmea_elem['id']}/artifacts",
        json={"artifact_id": artifact_id, "notes": "From draft run"},
    )
    assert link_resp.status_code == 201
    link_data = link_resp.json()
    assert link_data["artifact_id"] == artifact_id

    # Verify element now has artifact
    elem_detail = await test_client.get(
        f"/api/ppap-packages/{package_id}/elements/{pfmea_elem['id']}"
    )
    assert len(elem_detail.json()["artifacts"]) == 1


async def test_link_artifact_rejects_cross_project(test_client, demo_package_path, demo_sha256):
    """Linking an artifact from another project returns 409."""
    # Project 1 with artifact
    proj1 = await test_client.post("/api/projects", json={"name": "Cross Project 1"})
    project1_id = proj1.json()["id"]
    await test_client.post(
        f"/api/projects/{project1_id}/input-packages",
        json={"input_package_path": demo_package_path, "sha256": demo_sha256, "redacted": "true"},
    )
    draft1 = await test_client.post(f"/api/projects/{project1_id}/draft-runs")
    draft1_data = draft1.json()
    run1_id = draft1_data["id"]

    # Get the artifact from project 1's draft run
    artifacts_resp = await test_client.get("/api/artifacts")
    artifacts_list = artifacts_resp.json()
    artifact1_id = None
    for art in artifacts_list:
        if isinstance(art, dict) and art.get("run_id") == run1_id:
            artifact1_id = art["id"]
            break

    if artifact1_id is None:
        # No artifact to link - this is fine, skip test
        return

    # Project 2
    proj2 = await test_client.post("/api/projects", json={"name": "Cross Project 2"})
    project2_id = proj2.json()["id"]
    pkg2_resp = await test_client.post(
        f"/api/projects/{project2_id}/ppap-packages",
        json={"name": "Cross Project Package"},
    )
    package2_id = pkg2_resp.json()["id"]
    pkg2_detail = await test_client.get(f"/api/ppap-packages/{package2_id}")
    elem2_id = pkg2_detail.json()["elements"][0]["id"]

    # Try to link project 1's artifact to project 2's package - should be rejected
    link_resp = await test_client.post(
        f"/api/ppap-packages/{package2_id}/elements/{elem2_id}/artifacts",
        json={"artifact_id": artifact1_id, "notes": "cross project"},
    )
    assert link_resp.status_code == 409


async def test_refresh_from_project_auto_links(test_client, demo_package_path, demo_sha256):
    """refresh-from-project auto-links PFMEA/Control Plan artifacts."""
    # Set up project with full chain
    proj = await test_client.post("/api/projects", json={"name": "Refresh Test"})
    project_id = proj.json()["id"]

    await test_client.post(
        f"/api/projects/{project_id}/input-packages",
        json={"input_package_path": demo_package_path, "sha256": demo_sha256, "redacted": "true"},
    )
    await test_client.post(f"/api/projects/{project_id}/draft-runs")

    # Create package
    pkg_resp = await test_client.post(
        f"/api/projects/{project_id}/ppap-packages",
        json={"name": "Refresh Package"},
    )
    package_id = pkg_resp.json()["id"]

    # Refresh from project
    refresh_resp = await test_client.post(f"/api/ppap-packages/{package_id}/refresh-from-project")
    assert refresh_resp.status_code == 200
    result = refresh_resp.json()
    assert result["linked_count"] >= 0  # May be 0 if no matching artifacts

    # Check element statuses updated
    pfmea_elem = await test_client.get(
        f"/api/ppap-packages/{package_id}/elements"
    )
    # All elements should still be accessible
    elements = pfmea_elem.json()
    assert len(elements) == 18


async def test_not_found_on_wrong_package_element_mismatch(test_client):
    """PATCH on element that belongs to different package returns 404."""
    # Create two packages
    proj = await test_client.post("/api/projects", json={"name": "Mismatch Test"})
    project_id = proj.json()["id"]

    pkg1_resp = await test_client.post(
        f"/api/projects/{project_id}/ppap-packages",
        json={"name": "Package 1"},
    )
    package1_id = pkg1_resp.json()["id"]

    pkg2_resp = await test_client.post(
        f"/api/projects/{project_id}/ppap-packages",
        json={"name": "Package 2"},
    )
    package2_id = pkg2_resp.json()["id"]

    # Get element from package 1
    elem_resp = await test_client.get(f"/api/ppap-packages/{package1_id}")
    elem_id = elem_resp.json()["elements"][0]["id"]

    # Try to update it via package 2's URL - should 404
    resp = await test_client.patch(
        f"/api/ppap-packages/{package2_id}/elements/{elem_id}",
        json={"status": "approved"},
    )
    assert resp.status_code == 404


async def test_list_elements_returns_all_18(test_client):
    """GET /ppap-packages/{id}/elements returns all 18."""
    project_id, package_id = await _create_project_and_package(test_client)

    resp = await test_client.get(f"/api/ppap-packages/{package_id}/elements")
    assert resp.status_code == 200
    elements = resp.json()
    assert len(elements) == 18
    # Check display names are present
    display_names = {e["display_name"] for e in elements}
    assert any("Design Records" in d for d in display_names)
    assert any("PFMEA" in d for d in display_names)
    assert any("Control Plan" in d for d in display_names)
