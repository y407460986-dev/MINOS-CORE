"""Pipeline entry points for APQP fixture validation and export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .exporters import export_apqp_workbook


def validate_fixture(fixture: str | Path | dict[str, Any]) -> Any:
    """Load an APQP fixture, build the domain chain, and validate it."""

    payload = _load_fixture(fixture)
    chain = _build_chain(payload)
    result = _validate_chain(chain)
    if not result:
        raise ValueError("APQP chain validation failed:\n" + "\n".join(result.messages))
    return result


def export_fixture(fixture: str | Path | dict[str, Any], output_path: str | Path | None = None) -> Path:
    """Validate an APQP fixture and export the fixed Chinese workbook."""

    payload = _load_fixture(fixture)
    chain = _build_chain(payload)
    result = _validate_chain(chain)
    if not result:
        raise ValueError("APQP chain validation failed:\n" + "\n".join(result.messages))
    destination = Path(output_path) if output_path is not None else _default_output_path(fixture, chain)
    return export_apqp_workbook(chain, destination)


def _load_fixture(fixture: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(fixture, dict):
        return fixture
    path = Path(fixture)
    if path.is_dir():
        return {
            "process_flow": _load_fixture(path / "process_flow.json"),
            "pfmea": _load_fixture(path / "pfmea.json"),
            "control_plan": _load_fixture(path / "control_plan.json"),
        }
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("fixture must be a JSON object")
    return data


def _build_chain(payload: dict[str, Any]) -> Any:
    from .domain import APQPChain

    if hasattr(APQPChain, "model_validate"):
        return APQPChain.model_validate(payload)
    if hasattr(APQPChain, "parse_obj"):
        return APQPChain.parse_obj(payload)
    return APQPChain(**payload)


def _validate_chain(chain: Any) -> Any:
    from .validation import validate_chain

    return validate_chain(chain)


def _default_output_path(fixture: str | Path | dict[str, Any], chain: Any) -> Path:
    if isinstance(fixture, (str, Path)):
        return Path(fixture).with_suffix(".xlsx")
    slug = _chain_value(chain, "slug", "id", default="apqp_chain")
    return Path(f"{slug}.xlsx")


def _chain_value(chain: Any, *names: str, default: str) -> str:
    for name in names:
        if isinstance(chain, dict) and name in chain:
            return str(chain[name])
        if hasattr(chain, name):
            return str(getattr(chain, name))
    return default
