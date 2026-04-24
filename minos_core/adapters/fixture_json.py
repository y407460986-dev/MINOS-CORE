"""Fixture JSON file-system adapter.

This module owns JSON and directory IO for standard MINOS-CORE fixtures. Domain
objects stay independent from file paths, encodings, and fixture layout.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_fixture_payload(fixture: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(fixture, dict):
        return fixture
    path = Path(fixture)
    if path.is_dir():
        return {
            "process_flow": load_fixture_payload(path / "process_flow.json"),
            "pfmea": load_fixture_payload(path / "pfmea.json"),
            "control_plan": load_fixture_payload(path / "control_plan.json"),
        }
    return read_json_object(path)


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
