"""Unit tests for ``minos_core.observability.errors``."""

from __future__ import annotations

import unittest

from minos_core.observability.errors import (
    ConfigurationError,
    ExternalServiceError,
    MinosError,
    PipelineError,
    ResourceError,
    ValidationError,
    format_error_for_log,
    format_error_for_user,
)


class MinosErrorBaseTests(unittest.TestCase):
    """The base class supplies sensible defaults and accepts overrides."""

    def test_default_metadata_is_applied(self) -> None:
        err = MinosError("something broke")

        self.assertEqual(err.code, "MINOS_ERROR")
        self.assertEqual(err.context, {})
        self.assertFalse(err.retriable)
        self.assertEqual(err.message, "something broke")
        self.assertEqual(err.user_message_zh, "处理过程中发生未知错误。")

    def test_constructor_overrides_replace_defaults(self) -> None:
        cause = ValueError("upstream")
        err = MinosError(
            "wrapped",
            code="CUSTOM_CODE",
            context={"id": 1},
            retriable=True,
            user_message_zh="自定义提示",
            cause=cause,
        )

        self.assertEqual(err.code, "CUSTOM_CODE")
        self.assertEqual(err.context, {"id": 1})
        self.assertTrue(err.retriable)
        self.assertEqual(err.user_message_zh, "自定义提示")
        self.assertIs(err.__cause__, cause)

    def test_with_context_merges_extra_entries(self) -> None:
        err = MinosError("e", context={"a": 1}).with_context(b=2)

        self.assertEqual(err.context, {"a": 1, "b": 2})


class ErrorSubclassTests(unittest.TestCase):
    """Each subclass should expose a unique code and Chinese message."""

    def test_configuration_error_metadata(self) -> None:
        err = ConfigurationError("missing api key")
        self.assertEqual(err.code, "MINOS_CONFIG_ERROR")
        self.assertFalse(err.retriable)
        self.assertIn("配置", err.user_message_zh)

    def test_validation_error_metadata(self) -> None:
        err = ValidationError("bad input")
        self.assertEqual(err.code, "MINOS_VALIDATION_ERROR")
        self.assertFalse(err.retriable)
        self.assertIn("校验", err.user_message_zh)

    def test_external_service_error_is_retriable(self) -> None:
        err = ExternalServiceError("503 from AI")
        self.assertEqual(err.code, "MINOS_EXTERNAL_SERVICE_ERROR")
        self.assertTrue(err.retriable)

    def test_resource_error_metadata(self) -> None:
        err = ResourceError("disk full")
        self.assertEqual(err.code, "MINOS_RESOURCE_ERROR")
        self.assertFalse(err.retriable)

    def test_pipeline_error_records_stage(self) -> None:
        err = PipelineError("stage failed", stage="generate_pfd")
        self.assertEqual(err.code, "MINOS_PIPELINE_ERROR")
        self.assertEqual(err.context["stage"], "generate_pfd")
        self.assertTrue(err.retriable)


class FormattingHelperTests(unittest.TestCase):
    """``format_error_for_user`` / ``format_error_for_log`` payload shape."""

    def test_format_error_for_user_uses_subclass_message(self) -> None:
        err = ValidationError("not used")

        self.assertEqual(format_error_for_user(err), err.user_message_zh)

    def test_format_error_for_user_with_plain_exception(self) -> None:
        err = RuntimeError("boom")

        message = format_error_for_user(err)
        self.assertIn("RuntimeError", message)
        self.assertIn("未预期", message)

    def test_format_error_for_log_includes_minos_metadata(self) -> None:
        cause = ValueError("inner")
        try:
            raise PipelineError(
                "pipeline tripped",
                stage="ingest",
                context={"file": "drawing.pdf"},
                cause=cause,
            )
        except PipelineError as captured:
            payload = format_error_for_log(captured)

        self.assertEqual(payload["error_type"], "PipelineError")
        self.assertEqual(payload["error_code"], "MINOS_PIPELINE_ERROR")
        self.assertTrue(payload["retriable"])
        self.assertEqual(payload["context"], {"stage": "ingest", "file": "drawing.pdf"})
        self.assertEqual(payload["cause_type"], "ValueError")
        self.assertEqual(payload["cause_message"], "inner")
        self.assertIn("traceback", payload)
        self.assertIn("PipelineError", payload["traceback"])

    def test_format_error_for_log_with_plain_exception(self) -> None:
        try:
            raise RuntimeError("outer")
        except RuntimeError as captured:
            payload = format_error_for_log(captured)

        self.assertEqual(payload["error_type"], "RuntimeError")
        self.assertEqual(payload["error_message"], "outer")
        self.assertNotIn("error_code", payload)
        self.assertIn("traceback", payload)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
