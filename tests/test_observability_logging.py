"""Unit tests for ``minos_core.observability.logging``."""

from __future__ import annotations

import io
import json
import logging
import os
import unittest
from unittest import mock

from minos_core.observability import logging as obs_logging
from minos_core.observability.logging import (
    bind_request_context,
    clear_request_context,
    configure_logging,
    get_logger,
    unbind_request_context,
)


class ConfigureLoggingTests(unittest.TestCase):
    """Behaviour of ``configure_logging`` and the JSON/console renderers."""

    def setUp(self) -> None:
        # Reset module state so each test starts from a clean slate.
        obs_logging._CONFIGURED = False
        clear_request_context()
        # Clear any handlers that previous tests installed on the root logger.
        for handler in list(logging.getLogger().handlers):
            logging.getLogger().removeHandler(handler)

    def tearDown(self) -> None:
        clear_request_context()
        obs_logging._CONFIGURED = False
        for handler in list(logging.getLogger().handlers):
            logging.getLogger().removeHandler(handler)

    def _capture(self, *, json_format: bool, level: str = "INFO") -> str:
        configure_logging(level=level, json_format=json_format)
        # Redirect the configured handler's stream to a buffer instead of
        # relying on ``redirect_stderr`` (which would not affect the handler
        # captured at configure time).
        buffer = io.StringIO()
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.stream = buffer
        log = get_logger("minos.tests.logging")
        log.info("event.fired", step="ingest", count=2)
        for handler in logging.getLogger().handlers:
            handler.flush()
        return buffer.getvalue()

    def test_console_format_includes_event_and_kwargs(self) -> None:
        output = self._capture(json_format=False)

        self.assertIn("event.fired", output)
        self.assertIn("step=ingest", output)
        self.assertIn("count=2", output)
        # ConsoleRenderer emits the log level in lowercase.
        self.assertIn("info", output)

    def test_json_format_emits_valid_json(self) -> None:
        output = self._capture(json_format=True)
        # Take the last non-empty line so any prior output does not interfere.
        lines = [line for line in output.splitlines() if line.strip()]
        self.assertTrue(lines, msg=f"no output captured: {output!r}")
        payload = json.loads(lines[-1])

        self.assertEqual(payload["event"], "event.fired")
        self.assertEqual(payload["step"], "ingest")
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["level"], "info")
        self.assertEqual(payload["logger"], "minos.tests.logging")
        self.assertIn("timestamp", payload)
        self.assertIn("caller_filename", payload)

    def test_env_overrides_pick_up_defaults(self) -> None:
        with mock.patch.dict(os.environ, {"MINOS_LOG_JSON": "true", "MINOS_LOG_LEVEL": "WARNING"}, clear=False):
            configure_logging(level=None, json_format=None)
            self.assertEqual(logging.getLogger().level, logging.WARNING)

    def test_get_logger_auto_configures(self) -> None:
        self.assertFalse(obs_logging._CONFIGURED)
        log = get_logger("auto.config")
        # Calling get_logger before configure_logging should not raise and
        # should set the configured flag.
        self.assertTrue(obs_logging._CONFIGURED)
        log.info("auto.event")


class ContextVarBindingTests(unittest.TestCase):
    """``bind_request_context`` and friends route into structlog contextvars."""

    def setUp(self) -> None:
        obs_logging._CONFIGURED = False
        clear_request_context()
        for handler in list(logging.getLogger().handlers):
            logging.getLogger().removeHandler(handler)

    def tearDown(self) -> None:
        clear_request_context()
        obs_logging._CONFIGURED = False

    def test_bind_then_log_includes_context(self) -> None:
        configure_logging(level="INFO", json_format=True)
        log = get_logger("ctx.bind")
        bind_request_context(request_id="r-1", project_id="p-2", run_id="run-3", custom="x")

        buffer = io.StringIO()
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.stream = buffer
        log.info("ctx.event")
        for handler in logging.getLogger().handlers:
            handler.flush()
        payload = json.loads(buffer.getvalue().splitlines()[-1])

        self.assertEqual(payload["request_id"], "r-1")
        self.assertEqual(payload["project_id"], "p-2")
        self.assertEqual(payload["run_id"], "run-3")
        self.assertEqual(payload["custom"], "x")

    def test_unbind_removes_only_specified_keys(self) -> None:
        configure_logging(level="INFO", json_format=True)
        log = get_logger("ctx.unbind")
        bind_request_context(request_id="r-1", project_id="p-2")
        unbind_request_context("project_id")

        buffer = io.StringIO()
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.stream = buffer
        log.info("ctx.event")
        for handler in logging.getLogger().handlers:
            handler.flush()
        payload = json.loads(buffer.getvalue().splitlines()[-1])

        self.assertEqual(payload["request_id"], "r-1")
        self.assertNotIn("project_id", payload)

    def test_clear_drops_all_bindings(self) -> None:
        configure_logging(level="INFO", json_format=True)
        log = get_logger("ctx.clear")
        bind_request_context(request_id="r-1", project_id="p-2")
        clear_request_context()

        buffer = io.StringIO()
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.stream = buffer
        log.info("ctx.event")
        for handler in logging.getLogger().handlers:
            handler.flush()
        payload = json.loads(buffer.getvalue().splitlines()[-1])

        self.assertNotIn("request_id", payload)
        self.assertNotIn("project_id", payload)


class SensitiveDataRedactionTests(unittest.TestCase):
    """Sensitive data should be redacted before logging."""

    def setUp(self) -> None:
        obs_logging._CONFIGURED = False
        clear_request_context()
        for handler in list(logging.getLogger().handlers):
            logging.getLogger().removeHandler(handler)

    def tearDown(self) -> None:
        clear_request_context()
        obs_logging._CONFIGURED = False
        for handler in list(logging.getLogger().handlers):
            logging.getLogger().removeHandler(handler)

    def test_sensitive_data_redacted_in_logs(self) -> None:
        """Sensitive data should be redacted before logging."""
        configure_logging(level="INFO", json_format=True)
        log = get_logger("test.redaction")
        bind_request_context(request_id="r-1", api_key="sk-secret-key-12345678901234567890")

        buffer = io.StringIO()
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.stream = buffer
        log.info("test.message", token="Bearer abc123def456ghi789jkl012mno345pqr")
        for handler in logging.getLogger().handlers:
            handler.flush()
        output = buffer.getvalue()

        # Verify: api_key should be redacted in log output
        self.assertNotIn("sk-secret-key", output)
        self.assertNotIn("abc123def456ghi789jkl012mno345pqr", output)
        self.assertIn("REDACTED", output)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
