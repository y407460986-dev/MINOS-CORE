"""CLI launcher for the MINOS desktop shell."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="minos-desktop")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run UI-neutral desktop delivery preflight checks and exit",
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory to check during --smoke; defaults to out/desktop",
    )
    parser.add_argument(
        "--db-path",
        help="SQLite DB path to check during --smoke; defaults to out/desktop/minos_desktop.sqlite3",
    )
    parser.add_argument(
        "--require-ai-config",
        action="store_true",
        help="Treat missing AI key as a failed smoke check without making a network call",
    )
    args = parser.parse_args(argv)
    if args.smoke:
        from .preflight import run_desktop_preflight

        report = run_desktop_preflight(
            output_dir=args.output_dir,
            db_path=args.db_path,
            require_ai_config=args.require_ai_config,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] != "failed" else 2

    try:
        from .qt_app import run_desktop_app
    except ModuleNotFoundError as exc:
        if exc.name == "PySide6":
            print(
                "PySide6 is not installed. Install the desktop extra with: "
                'pip install -e ".[desktop]"'
            )
            return 2
        raise
    return run_desktop_app()


if __name__ == "__main__":
    raise SystemExit(main())
