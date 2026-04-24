"""Command line interface for MINOS Core."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .config import list_samples
from .domain import APQPChain
from .validation import validate_chain


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="minos-core")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List configured sample metadata")
    list_parser.add_argument("--samples-dir", default=None, help="Optional sample metadata directory")
    subparsers.add_parser("list-samples", help="List configured sample metadata")

    validate_parser = subparsers.add_parser("validate", help="Validate an APQP fixture")
    validate_parser.add_argument("--fixture", help="Fixture JSON file or fixture directory")
    validate_parser.add_argument("--input", help="Fixture JSON file or fixture directory")

    export_parser = subparsers.add_parser("export", help="Export an APQP fixture")
    export_parser.add_argument("--fixture", help="Fixture JSON file or fixture directory")
    export_parser.add_argument("--input", help="Fixture JSON file or fixture directory")
    export_parser.add_argument("--output", required=True, help="Output workbook path")
    export_parser.add_argument("--label", default="", help="Optional export label")

    args = parser.parse_args(argv)
    if args.command in {"list", "list-samples"}:
        return _list_samples(getattr(args, "samples_dir", None))
    if args.command == "validate":
        return _validate(args.fixture or args.input)
    if args.command == "export":
        return _export(args.fixture or args.input, args.output, args.label)
    parser.error(f"unknown command: {args.command}")
    return 2


def _list_samples(samples_dir: str | None = None) -> int:
    for sample in list_samples(samples_dir):
        print(
            "\t".join(
                [
                    sample.sample_id,
                    sample.display_name,
                    sample.product_family,
                    sample.apqp_phase,
                    sample.language,
                    sample.workbook_name,
                ]
            )
        )
    return 0


def _validate(fixture: str) -> int:
    if not fixture:
        raise ValueError("--fixture or --input is required")
    chain = APQPChain(**load_fixture_payload(fixture))
    result = validate_chain(chain)
    if not result:
        print(str(result))
        return 2
    print(f"OK: {chain.slug}")
    return 0


def _export(fixture: str, output: str, label: str) -> int:
    if not fixture:
        raise ValueError("--fixture or --input is required")
    from .pipeline import export_fixture

    payload = load_fixture_payload(fixture)
    if label:
        payload["label"] = label
    result = export_fixture(payload, output)
    print(f"Exported: {result}")
    return 0


def load_fixture_payload(fixture: str | Path) -> dict[str, Any]:
    path = Path(fixture)
    if path.is_dir():
        return {
            "process_flow": _read_json(path / "process_flow.json"),
            "pfmea": _read_json(path / "pfmea.json"),
            "control_plan": _read_json(path / "control_plan.json"),
        }
    return _read_json(path)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"fixture must be a JSON object: {path}")
    return data


if __name__ == "__main__":
    raise SystemExit(main())
