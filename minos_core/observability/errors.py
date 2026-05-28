"""Unified error hierarchy for MINOS-CORE.

The goal is to provide a small, predictable set of exception types that both
the pipeline and the desktop API can raise, plus helpers that turn those
exceptions into Chinese-localised user messages and structured log payloads.
We deliberately keep the hierarchy shallow: callers should reach for one of
the documented subclasses rather than inventing new ones for one-off cases.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from typing import Any, Mapping

__all__ = [
    "MinosError",
    "ConfigurationError",
    "ValidationError",
    "ExternalServiceError",
    "ResourceError",
    "PipelineError",
    "format_error_for_user",
    "format_error_for_log",
]


@dataclass
class _ErrorMetadata:
    """Lightweight container for code/context/retriable defaults."""

    code: str = "MINOS_ERROR"
    user_message_zh: str = "处理过程中发生未知错误。"
    retriable: bool = False


class MinosError(Exception):
    """Base class for all MINOS errors.

    Attributes:
        code: A short stable identifier suitable for log filtering and metrics.
        context: Arbitrary structured metadata that aids debugging. Sensitive
            values (API keys, full request bodies) must NOT be placed here.
        retriable: Whether retrying the same operation has a reasonable chance
            of succeeding.
        user_message_zh: A user-facing Chinese message; defaults to a generic
            string when not overridden by subclasses or callers.

    The stdlib bridges below (``ConfigurationError`` → ``RuntimeError``,
    ``ValidationError`` → ``ValueError``) make MINOS errors safe drop-in
    replacements where existing call sites still ``except`` on the legacy type.
    """

    _metadata: _ErrorMetadata = _ErrorMetadata()

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        context: Mapping[str, Any] | None = None,
        retriable: bool | None = None,
        user_message_zh: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code or self._metadata.code
        self.context: dict[str, Any] = dict(context or {})
        self.retriable = (
            self._metadata.retriable if retriable is None else bool(retriable)
        )
        self.user_message_zh = user_message_zh or self._metadata.user_message_zh
        if cause is not None:
            self.__cause__ = cause

    @property
    def message(self) -> str:
        """The original developer-facing message passed to ``__init__``."""

        return self.args[0] if self.args else ""

    def with_context(self, **extra: Any) -> "MinosError":
        """Return ``self`` after merging additional context entries."""

        self.context.update(extra)
        return self


class ConfigurationError(MinosError, RuntimeError):
    """Raised when configuration is missing, malformed, or contradictory."""

    _metadata = _ErrorMetadata(
        code="MINOS_CONFIG_ERROR",
        user_message_zh="系统配置缺失或不正确，请检查配置项后重试。",
        retriable=False,
    )


class ValidationError(MinosError, ValueError):
    """Raised when user-supplied data fails validation."""

    _metadata = _ErrorMetadata(
        code="MINOS_VALIDATION_ERROR",
        user_message_zh="输入数据未通过校验，请检查后重新提交。",
        retriable=False,
    )


class ExternalServiceError(MinosError, RuntimeError):
    """Raised when a downstream service (AI, OCR, HTTP) misbehaves."""

    _metadata = _ErrorMetadata(
        code="MINOS_EXTERNAL_SERVICE_ERROR",
        user_message_zh="外部服务调用失败，可稍后重试或切换备用服务。",
        retriable=True,
    )


class ResourceError(MinosError, RuntimeError):
    """Raised when a local resource (filesystem, subprocess, memory) fails."""

    _metadata = _ErrorMetadata(
        code="MINOS_RESOURCE_ERROR",
        user_message_zh="本地资源访问失败，请检查磁盘空间或进程权限。",
        retriable=False,
    )


class PipelineError(MinosError, RuntimeError):
    """Raised when the APQP pipeline fails during a specific stage."""

    _metadata = _ErrorMetadata(
        code="MINOS_PIPELINE_ERROR",
        user_message_zh="流水线执行失败，请查看详细错误并重试当前阶段。",
        retriable=True,
    )

    def __init__(
        self,
        message: str,
        *,
        stage: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        if stage:
            self.context.setdefault("stage", stage)


def format_error_for_user(err: BaseException) -> str:
    """Return a Chinese user-facing message for the given exception."""

    if isinstance(err, MinosError):
        return err.user_message_zh
    return f"处理过程中发生未预期的错误：{err.__class__.__name__}"


def format_error_for_log(err: BaseException) -> dict[str, Any]:
    """Return a structured payload safe to feed into the logging pipeline."""

    payload: dict[str, Any] = {
        "error_type": err.__class__.__name__,
        "error_message": str(err) or err.__class__.__name__,
    }
    if isinstance(err, MinosError):
        payload["error_code"] = err.code
        payload["retriable"] = err.retriable
        if err.context:
            payload["context"] = dict(err.context)
    cause = err.__cause__ or err.__context__
    if cause is not None and cause is not err:
        payload["cause_type"] = cause.__class__.__name__
        payload["cause_message"] = str(cause)
    payload["traceback"] = "".join(
        traceback.format_exception(type(err), err, err.__traceback__)
    ).strip()
    return payload
