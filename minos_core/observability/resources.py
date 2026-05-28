"""Resource management helpers for MINOS-CORE.

These helpers wrap a few error-prone native primitives (``TemporaryDirectory``
and ``subprocess.Popen``) in well-instrumented context managers so the rest of
the codebase can stay focused on business logic. Logging is intentionally
verbose at the DEBUG level and concise at INFO so production output stays
readable.
"""

from __future__ import annotations

import errno
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any, Iterator, Sequence

from .errors import ResourceError
from .logging import get_logger

__all__ = [
    "temporary_directory",
    "managed_subprocess",
]

_logger = get_logger("minos_core.observability.resources")


def _safe_rmtree(path: Path) -> None:
    """Best-effort recursive delete that tolerates Windows file locks."""

    def _onerror(func: Any, target: str, exc_info: Any) -> None:
        # On Windows, read-only flags or transient locks may prevent deletion.
        # Try once more after relaxing the file mode.
        try:
            os.chmod(target, 0o700)
            func(target)
        except OSError as exc:  # pragma: no cover - logged for diagnostics only
            _logger.warning(
                "temporary_directory.cleanup_failed",
                path=target,
                error=str(exc),
            )

    if not path.exists():
        return
    shutil.rmtree(path, onerror=_onerror)


@contextmanager
def temporary_directory(
    prefix: str = "minos-",
    *,
    parent: str | os.PathLike[str] | None = None,
) -> Iterator[Path]:
    """Yield a freshly-created temporary directory and clean it up on exit.

    Unlike :class:`tempfile.TemporaryDirectory` this helper:

    * Returns a :class:`pathlib.Path` directly.
    * Logs creation and cleanup at DEBUG level for traceability.
    * Wraps creation failures in :class:`~minos_core.observability.errors.ResourceError`.
    * Tolerates Windows-specific cleanup failures without raising.
    """

    parent_path = Path(parent) if parent is not None else None
    try:
        raw_path = tempfile.mkdtemp(prefix=prefix, dir=str(parent_path) if parent_path else None)
    except OSError as exc:
        raise ResourceError(
            "Failed to allocate temporary directory",
            context={"prefix": prefix, "parent": str(parent_path) if parent_path else ""},
            cause=exc,
        ) from exc

    path = Path(raw_path)
    _logger.debug("temporary_directory.created", path=str(path), prefix=prefix)
    started = time.monotonic()
    try:
        yield path
    finally:
        try:
            _safe_rmtree(path)
        except Exception as exc:  # pragma: no cover - defensive fallback
            _logger.warning(
                "temporary_directory.cleanup_error",
                path=str(path),
                error=str(exc),
            )
        else:
            _logger.debug(
                "temporary_directory.cleaned",
                path=str(path),
                duration_s=round(time.monotonic() - started, 3),
            )


def _terminate_process(proc: subprocess.Popen[Any], grace_period: float) -> None:
    """Send ``terminate`` then ``kill`` if the process refuses to exit."""

    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=grace_period)
        return
    except subprocess.TimeoutExpired:
        _logger.warning(
            "managed_subprocess.terminate_timeout",
            pid=proc.pid,
            grace_period_s=grace_period,
        )
    proc.kill()
    try:
        proc.wait(timeout=grace_period)
    except subprocess.TimeoutExpired:  # pragma: no cover - extreme edge case
        _logger.error("managed_subprocess.kill_timeout", pid=proc.pid)


@contextmanager
def managed_subprocess(
    args: Sequence[str],
    *,
    timeout: float | None = None,
    grace_period: float = 5.0,
    cwd: str | os.PathLike[str] | None = None,
    env: dict[str, str] | None = None,
    stdin: IO[Any] | int | None = None,
    stdout: IO[Any] | int | None = subprocess.PIPE,
    stderr: IO[Any] | int | None = subprocess.PIPE,
    text: bool = True,
) -> Iterator[subprocess.Popen[Any]]:
    """Spawn a subprocess and guarantee teardown when the block exits.

    The helper logs the command, exit code, and duration at INFO so operators
    can audit external invocations without sprinkling print statements through
    adapters. Failures during spawn surface as :class:`ResourceError`; the
    caller still owns the success/failure semantics of the command itself.

    Args:
        args: Command arguments forwarded to :class:`subprocess.Popen`.
        timeout: When provided, the process is terminated if it has not exited
            by the time the block completes (``None`` waits indefinitely).
        grace_period: Seconds to wait between ``terminate`` and ``kill``.
        cwd: Working directory for the spawned process.
        env: Environment variables (defaults to inheriting from the parent).
        stdin/stdout/stderr: Standard stream configuration matching
            :class:`subprocess.Popen`.
        text: Whether to decode pipes as text. Defaults to True for ergonomics.
    """

    cmd_summary = " ".join(str(part) for part in args[:4])
    _logger.info(
        "managed_subprocess.spawn",
        cmd=cmd_summary,
        cwd=str(cwd) if cwd else "",
    )
    started = time.monotonic()
    try:
        proc = subprocess.Popen(  # noqa: S603 - command is caller-controlled
            list(args),
            cwd=str(cwd) if cwd is not None else None,
            env=env,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            text=text,
        )
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            user_msg = "未找到所需的可执行文件，请检查依赖是否已安装。"
        else:
            user_msg = "启动外部进程失败，请查看详细错误。"
        raise ResourceError(
            f"Failed to spawn subprocess: {cmd_summary}",
            context={"cmd": cmd_summary, "errno": exc.errno},
            cause=exc,
            user_message_zh=user_msg,
        ) from exc

    try:
        yield proc
    finally:
        if timeout is not None and proc.poll() is None:
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                _logger.warning(
                    "managed_subprocess.timeout",
                    pid=proc.pid,
                    timeout_s=timeout,
                )
                _terminate_process(proc, grace_period)
        elif proc.poll() is None:
            # The block exited without waiting; teardown gracefully.
            _terminate_process(proc, grace_period)

        # Make sure pipes are released even if the caller never consumed them.
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                except OSError:  # pragma: no cover - defensive
                    pass

        exit_code = proc.poll()
        _logger.info(
            "managed_subprocess.exit",
            pid=proc.pid,
            exit_code=exit_code,
            duration_s=round(time.monotonic() - started, 3),
        )


# Suppress unused-import warning for type checkers that do not see
# subprocess.Popen used as a return type otherwise.
_ = sys
