"""CLI entry point for minos_platform server."""

from __future__ import annotations

import argparse
import subprocess
import sys


def main(argv: list[str] | None = None) -> int:
    """Start the uvicorn server for minos_platform."""
    parser = argparse.ArgumentParser(prog="minos-platform")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1

    return subprocess.run(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "minos_platform.app:app",
            "--host",
            args.host,
            "--port",
            str(args.port),
            "--workers",
            "1",
        ],
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
