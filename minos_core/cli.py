"""Command line interface for MINOS Core."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .adapters.fixture_json import load_fixture_payload
from .config import list_samples
from .domain import APQPChain
from .validation import validate_chain


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="minos-core")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List configured sample metadata")
    list_parser.add_argument(
        "--samples-dir", default=None, help="Optional sample metadata directory"
    )
    subparsers.add_parser("list-samples", help="List configured sample metadata")

    validate_parser = subparsers.add_parser("validate", help="Validate an APQP fixture")
    validate_parser.add_argument(
        "--fixture", help="Fixture JSON file or fixture directory"
    )
    validate_parser.add_argument(
        "--input", help="Fixture JSON file or fixture directory"
    )

    export_parser = subparsers.add_parser("export", help="Export an APQP fixture")
    export_parser.add_argument(
        "--fixture", help="Fixture JSON file or fixture directory"
    )
    export_parser.add_argument("--input", help="Fixture JSON file or fixture directory")
    export_parser.add_argument("--output", required=True, help="Output workbook path")
    export_parser.add_argument("--label", default="", help="Optional export label")

    audit_parser = subparsers.add_parser(
        "audit", help="Audit APQP fixture quality without blocking export"
    )
    audit_parser.add_argument(
        "--fixture", help="Fixture JSON file or fixture directory"
    )
    audit_parser.add_argument("--input", help="Fixture JSON file or fixture directory")
    audit_parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON"
    )

    convert_parser = subparsers.add_parser(
        "convert-legacy", help="Convert a legacy Excel seed workbook"
    )
    convert_parser.add_argument(
        "--sample-id",
        required=True,
        help="Sample identifier for the generated fixtures",
    )
    convert_parser.add_argument(
        "--display-name", required=True, help="Display name for the generated fixtures"
    )
    convert_parser.add_argument(
        "--input", required=True, help="Legacy .xlsx seed workbook path"
    )
    convert_parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for process_flow/pfmea/control_plan JSON",
    )
    convert_parser.add_argument(
        "--profile",
        default=None,
        help="Optional profile: door_hinge, stamping, or limiter",
    )

    args = parser.parse_args(argv)
    if args.command in {"list", "list-samples"}:
        return _list_samples(getattr(args, "samples_dir", None))
    if args.command == "validate":
        return _validate(args.fixture or args.input)
    if args.command == "export":
        return _export(args.fixture or args.input, args.output, args.label)
    if args.command == "audit":
        return _audit(args.fixture or args.input, args.json)
    if args.command == "convert-legacy":
        return _convert_legacy(
            args.input, args.output_dir, args.sample_id, args.display_name, args.profile
        )
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


def _audit(fixture: str, as_json: bool) -> int:
    if not fixture:
        raise ValueError("--fixture or --input is required")
    from .audit import audit_chain, audit_report_json

    report = audit_chain(load_fixture_payload(fixture))
    print(audit_report_json(report) if as_json else report.to_text())
    return 0


def _convert_legacy(
    workbook: str,
    output_dir: str,
    sample_id: str,
    display_name: str,
    profile: str | None,
) -> int:
    from .adapters.legacy_excel import convert_legacy_workbook

    paths = convert_legacy_workbook(
        workbook, output_dir, sample_id, display_name, profile
    )
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
