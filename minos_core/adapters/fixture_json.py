"""Fixture JSON file-system adapter.

This module owns JSON and directory IO for standard MINOS-CORE fixtures. Domain
objects stay independent from file paths, encodings, and fixture layout.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from minos_core.schemas import validate_bundle_schema


def load_fixture_payload(fixture: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(fixture, dict):
        return _normalize_input_package_payload(fixture)
    path = Path(fixture)
    if path.is_dir():
        input_package_path = path / "input_package.json"
        if input_package_path.exists():
            return _input_package_from_directory(path)
        payload = {
            "process_flow": load_fixture_payload(path / "process_flow.json"),
            "pfmea": load_fixture_payload(path / "pfmea.json"),
            "control_plan": load_fixture_payload(path / "control_plan.json"),
        }
        evidence_path = path / "evidence.json"
        if evidence_path.exists():
            payload["evidence"] = _evidence_rows(
                load_fixture_payload(evidence_path), evidence_path
            )
        return payload
    payload = read_json_object(path)
    if _is_input_package_payload(payload):
        return _normalize_input_package_payload(payload, base_path=path.parent)
    return payload


def load_apqp_chain(fixture: str | Path | dict[str, Any]) -> dict[str, Any]:
    return load_fixture_payload(fixture)


def load_chain(fixture: str | Path | dict[str, Any]) -> dict[str, Any]:
    return load_fixture_payload(fixture)


def load_domain_bundle(fixture: str | Path | dict[str, Any]) -> dict[str, Any]:
    return load_fixture_payload(fixture)


def read_json_object(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    data = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"fixture must be a JSON object: {file_path}")
    return data


def _input_package_from_directory(path: Path) -> dict[str, Any]:
    package = read_json_object(path / "input_package.json")
    if not _is_input_package_payload(package):
        package["document_type"] = "input_package"
    return _normalize_input_package_payload(package, base_path=path)


def _is_input_package_payload(payload: dict[str, Any]) -> bool:
    return payload.get("document_type") == "input_package" or "input_package" in payload


def _normalize_input_package_payload(
    payload: dict[str, Any],
    *,
    base_path: Path | None = None,
) -> dict[str, Any]:
    if not _is_input_package_payload(payload):
        return payload
    package = payload.get("input_package", payload)
    if not isinstance(package, dict):
        raise ValueError("input_package must be a JSON object")

    validate_bundle_schema(package, "input_package")

    evidence_payload = _embedded_or_referenced_object(
        package,
        "evidence",
        default_filename="evidence.json",
        base_path=base_path,
    )
    review_patch = _embedded_or_referenced_object(
        package,
        "review_patch",
        default_filename="review_patch.json",
        base_path=base_path,
        required=False,
    )
    evidence_rows = _evidence_rows(evidence_payload, base_path or Path("input_package"))
    metadata = dict(package.get("metadata", {}))
    metadata.update(
        {
            "input_package_id": str(package.get("package_id", package.get("id", ""))),
            "input_package_schema_version": str(package.get("schema_version", "")),
            "ingest_mode": "input_package",
            "source_ref": str(package.get("source_ref", "input_package")),
            "draft_requires_review": bool(package.get("draft_requires_review", True)),
        }
    )
    if review_patch:
        metadata["review_patch"] = review_patch
    if "source_documents" in package:
        metadata["source_documents"] = package["source_documents"]
    return {
        "document_type": "evidence_bundle",
        "schema_version": str(evidence_payload.get("schema_version", "0.1")),
        "evidence": evidence_rows,
        "metadata": metadata,
    }


def _embedded_or_referenced_object(
    package: dict[str, Any],
    field_name: str,
    *,
    default_filename: str,
    base_path: Path | None,
    required: bool = True,
) -> dict[str, Any]:
    value = package.get(field_name)
    if isinstance(value, dict):
        return value
    path_value = package.get(f"{field_name}_path")
    if path_value is None and base_path is not None:
        candidate = base_path / default_filename
        if candidate.exists():
            path_value = default_filename
    if path_value is not None:
        if base_path is None:
            raise ValueError(f"{field_name}_path requires a base directory")
        path = base_path / str(path_value)
        return read_json_object(path)
    if required:
        raise ValueError(f"input_package must include {field_name} or {field_name}_path")
    return {}


def _evidence_rows(payload: dict[str, Any], path: Path) -> list[dict[str, Any]]:
    evidence = payload.get("evidence", [])
    if not isinstance(evidence, list):
        raise ValueError(f"evidence must be a JSON array: {path}")
    return evidence
