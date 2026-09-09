"""Command-line launcher for the MINOS desktop sidecar API."""

from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path

from minos_core.observability.logging import get_logger
from minos_desktop.services import DEFAULT_DESKTOP_DB_PATH, DEFAULT_DESKTOP_OUTPUT_DIR

logger = get_logger("minos_desktop")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="minos-desktop-api")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db-path", default=str(DEFAULT_DESKTOP_DB_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_DESKTOP_OUTPUT_DIR))
    parser.add_argument(
        "--token",
        default="",
        help="Bearer token required by the local API. Defaults to a generated token.",
    )
    args = parser.parse_args(argv)

    token = args.token or os.getenv("MINOS_DESKTOP_API_TOKEN") or secrets.token_urlsafe(24)
    os.environ["MINOS_DESKTOP_API_TOKEN"] = token

    from .app import create_app

    app = create_app(db_path=Path(args.db_path), output_dir=Path(args.output_dir))
    logger.info("desktop_api_listening", host=args.host, port=args.port)

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
