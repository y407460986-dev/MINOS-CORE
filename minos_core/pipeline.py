"""Pipeline entry points for APQP workflow orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .adapters.fixture_json import load_fixture_payload
from .exporters import export_apqp_workbook
from .stage import assemble_generated_apqp_chain as _assemble_generated_apqp_chain


PIPELINE_STAGES = (
    "ingest",
    "analyze",
    "generate_pfd",
    "brainstorm_failure_modes",
    "generate_pfmea",
    "generate_control_plan",
    "assemble_generated_apqp_chain",
    "validate",
    "export",
)


def validate_fixture(fixture: str | Path | dict[str, Any]) -> Any:
    """Load an APQP fixture, build the domain chain, and validate it."""

    payload = load_fixture_payload(fixture)
    chain = _build_chain(payload)
    result = _validate_chain(chain)
    if not result:
        raise ValueError("APQP chain validation failed:\n" + "\n".join(result.messages))
    return result


def export_fixture(
    fixture: str | Path | dict[str, Any], output_path: str | Path | None = None
) -> Path:
    """Validate an APQP fixture and export the fixed Chinese workbook."""

    payload = load_fixture_payload(fixture)
    chain = _build_chain(payload)
    result = _validate_chain(chain)
    if not result:
        raise ValueError("APQP chain validation failed:\n" + "\n".join(result.messages))
    destination = (
        Path(output_path)
        if output_path is not None
        else _default_output_path(fixture, chain)
    )
    return export_apqp_workbook(chain, destination)



def assemble_generated_apqp_chain(
    process_flow: dict[str, Any] | None = None,
    failure_mode_candidates: dict[str, Any] | None = None,
    pfmea: dict[str, Any] | None = None,
    control_plan: dict[str, Any] | None = None,
    *,
    pfd: dict[str, Any] | None = None,
    brainstorm: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble generated APQP bundles through the stage implementation."""

    return _assemble_generated_apqp_chain(
        pfd if process_flow is None else process_flow,
        brainstorm if failure_mode_candidates is None else failure_mode_candidates,
        pfmea,
        control_plan,
        metadata=metadata,
    )


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
