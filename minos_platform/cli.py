"""CLI entry point for minos_platform server."""

from __future__ import annotations

import subprocess
import sys


def main(argv: list[str] | None = None) -> int:
    """Start the uvicorn server for minos_platform."""
    host = "0.0.0.0"
    port = 8000
    if argv:
        for i, arg in enumerate(argv):
            if arg == "--host" and i + 1 < len(argv):
                host = argv[i + 1]
            elif arg == "--port" and i + 1 < len(argv):
                port = argv[i + 1]

    return subprocess.run(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "minos_platform.app:app",
            "--host",
            host,
            "--port",
            port,
            "--workers",
            "1",
        ],
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
