"""Unit tests for ``minos_core.observability.resources``."""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from minos_core.observability.errors import ResourceError
from minos_core.observability.resources import (
    managed_subprocess,
    temporary_directory,
)


class TemporaryDirectoryTests(unittest.TestCase):
    """``temporary_directory`` should create, yield, and clean up reliably."""

    def test_yields_existing_directory_and_cleans_up(self) -> None:
        captured: list[Path] = []
        with temporary_directory(prefix="mt-") as path:
            captured.append(path)
            self.assertTrue(path.is_dir())
            (path / "child.txt").write_text("hello")

        self.assertFalse(captured[0].exists())

    def test_prefix_is_applied(self) -> None:
        with temporary_directory(prefix="prefix-marker-") as path:
            self.assertTrue(path.name.startswith("prefix-marker-"))

    def test_cleanup_runs_even_after_exception(self) -> None:
        leaked: list[Path] = []
        with self.assertRaises(RuntimeError):
            with temporary_directory(prefix="raise-") as path:
                leaked.append(path)
                self.assertTrue(path.exists())
                raise RuntimeError("boom")

        self.assertFalse(leaked[0].exists())

    def test_creation_failure_raises_resource_error(self) -> None:
        with mock.patch(
            "minos_core.observability.resources.tempfile.mkdtemp",
            side_effect=OSError("disk fail"),
        ):
            with self.assertRaises(ResourceError) as ctx:
                with temporary_directory(prefix="fail-"):
                    pass

        self.assertIn("temporary directory", str(ctx.exception).lower())
        self.assertEqual(ctx.exception.code, "MINOS_RESOURCE_ERROR")
        self.assertEqual(ctx.exception.context.get("prefix"), "fail-")

    def test_parent_directory_is_respected(self) -> None:
        with temporary_directory(prefix="outer-") as parent:
            with temporary_directory(prefix="inner-", parent=parent) as inner:
                self.assertEqual(inner.parent, parent)
            self.assertFalse(inner.exists())


class ManagedSubprocessTests(unittest.TestCase):
    """``managed_subprocess`` should spawn, surface output, and tear down."""

    def test_normal_completion_returns_output(self) -> None:
        with managed_subprocess(
            [sys.executable, "-c", "print('hello-from-sub'); import sys; sys.stdout.flush()"]
        ) as proc:
            stdout, stderr = proc.communicate(timeout=15)

        self.assertEqual(proc.returncode, 0)
        self.assertIn("hello-from-sub", stdout)
        self.assertEqual(stderr, "")

    def test_missing_executable_raises_resource_error(self) -> None:
        with self.assertRaises(ResourceError) as ctx:
            with managed_subprocess(["this-command-should-not-exist-xyz123"]):
                pass

        self.assertEqual(ctx.exception.code, "MINOS_RESOURCE_ERROR")
        self.assertIn("可执行文件", ctx.exception.user_message_zh)

    def test_block_exit_terminates_running_process(self) -> None:
        # Spawn a child that would otherwise sleep for several seconds.
        script = "import time, sys; sys.stdout.write('alive'); sys.stdout.flush(); time.sleep(30)"
        start = time.monotonic()
        with managed_subprocess([sys.executable, "-c", script]) as proc:
            # Give the child a moment to begin executing.
            time.sleep(0.5)
            self.assertIsNone(proc.poll())

        elapsed = time.monotonic() - start
        # Cleanup must finish well before the 30s sleep would have completed.
        self.assertLess(elapsed, 10.0)
        self.assertIsNotNone(proc.poll())

    def test_timeout_triggers_termination(self) -> None:
        script = "import time, sys; sys.stdout.write('start'); sys.stdout.flush(); time.sleep(30)"
        start = time.monotonic()
        with managed_subprocess([sys.executable, "-c", script], timeout=0.5) as proc:
            self.assertIsNone(proc.poll())

        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 10.0)
        self.assertIsNotNone(proc.poll())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
