"""Unit tests for ``minos_core.observability.config_diagnostics``."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from minos_core.observability.config_diagnostics import (
    ConfigSource,
    describe_config_sources,
    format_config_sources,
)


_RESET_ENV = {
    "MINOS_LOG_LEVEL",
    "MINOS_LOG_JSON",
    "MINOS_OPENAI_BASE_URL",
    "OPENAI_BASE_URL",
    "ARK_BASE_URL",
    "MINOS_OPENAI_MODEL",
    "OPENAI_MODEL",
    "ARK_MODEL",
    "MINOS_OPENAI_API_KEY",
    "OPENAI_API_KEY",
    "ARK_API_KEY",
    "MINOS_BACKUP_AI_ENDPOINTS",
    "MINOS_MINERU_COMMAND",
    "MINERU_COMMAND",
    "MINOS_CODEX_HOME",
    "CODEX_HOME",
}


class DescribeConfigSourcesTests(unittest.TestCase):
    """The describe helper should reflect environment vs default values."""

    def setUp(self) -> None:
        # Snapshot and clear any vars that influence the diagnostics output.
        self._snapshot = {k: os.environ.get(k) for k in _RESET_ENV}
        for key in _RESET_ENV:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._snapshot.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _by_key(self, sources: list[ConfigSource], key: str) -> ConfigSource:
        for src in sources:
            if src.key == key:
                return src
        raise AssertionError(f"missing key {key!r} in {sources}")

    def test_defaults_resolve_when_no_env_set(self) -> None:
        sources = describe_config_sources()

        log_level = self._by_key(sources, "log_level")
        self.assertEqual(log_level.source, "default")
        self.assertEqual(log_level.value, "INFO")

        ai_base = self._by_key(sources, "ai_base_url")
        self.assertEqual(ai_base.source, "default")
        self.assertIn("allincoding", ai_base.value)

        api_key = self._by_key(sources, "ai_api_key")
        self.assertEqual(api_key.source, "unset")

        backup = self._by_key(sources, "backup_ai_endpoints")
        self.assertEqual(backup.source, "unset")

    def test_env_var_overrides_default(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "MINOS_LOG_LEVEL": "DEBUG",
                "MINOS_OPENAI_BASE_URL": "https://override.example",
            },
        ):
            sources = describe_config_sources()

        self.assertEqual(self._by_key(sources, "log_level").value, "DEBUG")
        self.assertEqual(self._by_key(sources, "log_level").source, "env")
        ai_base = self._by_key(sources, "ai_base_url")
        self.assertEqual(ai_base.value, "https://override.example")
        self.assertEqual(ai_base.detail, "MINOS_OPENAI_BASE_URL")

    def test_secret_env_value_is_redacted(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"MINOS_OPENAI_API_KEY": "redaction-test-value-1234567890"},
        ):
            sources = describe_config_sources()

        api_key = self._by_key(sources, "ai_api_key")
        self.assertEqual(api_key.source, "env")
        # The redacted form should never reveal the full secret.
        self.assertNotIn("supersecret", api_key.value)
        self.assertIn("len=", api_key.value)

    def test_codex_config_marked_unset_when_path_missing(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"MINOS_CODEX_HOME": "/definitely/not/a/real/codex/home"},
        ):
            sources = describe_config_sources()

        codex = self._by_key(sources, "codex_config_file")
        self.assertEqual(codex.source, "unset")


class FormatConfigSourcesTests(unittest.TestCase):
    """The formatter should produce stable, human-readable output."""

    def test_format_handles_empty_list(self) -> None:
        self.assertEqual(format_config_sources([]), "(no configuration sources detected)")

    def test_format_includes_keys_values_and_sources(self) -> None:
        rendered = format_config_sources([
            ConfigSource(key="log_level", value="INFO", source="default", detail="hardcoded"),
            ConfigSource(key="ai_base_url", value="https://example.com", source="env", detail="MINOS_OPENAI_BASE_URL"),
        ])

        self.assertIn("log_level", rendered)
        self.assertIn("INFO", rendered)
        self.assertIn("default", rendered)
        self.assertIn("MINOS_OPENAI_BASE_URL", rendered)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
