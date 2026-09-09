"""Structured logging configuration for MINOS-CORE.

Wraps :mod:`structlog` so every component shares a consistent processor chain,
contextvar-based correlation IDs, and a JSON / console rendering switch driven
by environment variables. The module is import-safe even when callers never
invoke :func:`configure_logging`; in that case structlog uses its default
configuration and standard library logging keeps working unchanged.
"""

from __future__ import annotations

import logging
import os
import sys
from types import FrameType
from typing import Any, cast

import structlog
from structlog.contextvars import (
    bind_contextvars,
    clear_contextvars,
    merge_contextvars,
    unbind_contextvars,
)
from structlog.types import EventDict, Processor

from .redaction import redact_sensitive_data

__all__ = [
    "configure_logging",
    "get_logger",
    "bind_request_context",
    "clear_request_context",
    "unbind_request_context",
]


_ENV_LEVEL = "MINOS_LOG_LEVEL"
_ENV_JSON = "MINOS_LOG_JSON"

# Tracks whether configure_logging() has run during this process so callers can
# safely import this module multiple times without the chain being rebuilt.
_CONFIGURED: bool = False


def _resolve_level(level: str | int | None) -> int:
    """Translate the requested level into a stdlib logging integer."""

    if isinstance(level, int):
        return level
    name = (level or os.getenv(_ENV_LEVEL) or "INFO").upper().strip()
    return logging.getLevelName(name) if not name.isdigit() else int(name)


def _resolve_json(json_format: bool | None) -> bool:
    """Decide whether to emit JSON based on the explicit flag and env."""

    if json_format is not None:
        return json_format
    raw = (os.getenv(_ENV_JSON, "") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _add_caller_info(_: Any, __: str, event_dict: EventDict) -> EventDict:
    """Populate caller filename, function, and line number when available."""

    frame: FrameType | None = sys._getframe(1)
    # Walk past structlog and logging frames to reach the actual caller.
    skip_modules = ("structlog", "logging")
    while frame is not None:
        module_name = frame.f_globals.get("__name__", "")
        if not any(module_name == mod or module_name.startswith(mod + ".")
                   for mod in skip_modules):
            break
        frame = frame.f_back
    if frame is None:
        return event_dict
    event_dict.setdefault("caller_filename", os.path.basename(frame.f_code.co_filename))
    event_dict.setdefault("caller_func", frame.f_code.co_name)
    event_dict.setdefault("caller_lineno", frame.f_lineno)
    return event_dict


def _redact_processor(_: Any, __: str, event_dict: EventDict) -> EventDict:
    """Redact sensitive information from event dict."""
    return redact_sensitive_data(event_dict)


def _build_processors(json_format: bool) -> list[Processor]:
    """Assemble the structlog processor chain shared across all loggers."""

    processors: list[Processor] = [
        merge_contextvars,
        _redact_processor,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_caller_info,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]
    if json_format:
        processors.append(structlog.processors.JSONRenderer(sort_keys=True))
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=False))
    return processors


def configure_logging(
    level: str | int | None = "INFO",
    json_format: bool | None = False,
) -> None:
    """Configure stdlib logging and structlog with MINOS conventions.

    Args:
        level: Stdlib logging level name (``DEBUG``/``INFO``/``WARNING``/...) or
            integer. Falls back to ``MINOS_LOG_LEVEL`` then ``INFO``.
        json_format: If ``True`` emit JSON; if ``False`` emit human-readable
            console output; if ``None`` consult ``MINOS_LOG_JSON``.
    """

    global _CONFIGURED

    resolved_level = _resolve_level(level)
    use_json = _resolve_json(json_format)

    # Reset stdlib root handlers so repeated configuration does not duplicate
    # log lines in tests or interactive sessions.
    root_logger = logging.getLogger()
    for existing in list(root_logger.handlers):
        root_logger.removeHandler(existing)
    handler = logging.StreamHandler(sys.stderr)
    # We render through structlog's processor chain; the stdlib handler should
    # not add its own prefix/suffix on top of the rendered string.
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.setLevel(resolved_level)
    root_logger.addHandler(handler)
    root_logger.setLevel(resolved_level)

    processors = _build_processors(use_json)

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _CONFIGURED = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger; configure with defaults on first call."""

    if not _CONFIGURED:
        configure_logging()
    logger = structlog.get_logger(name) if name else structlog.get_logger()
    return cast(structlog.stdlib.BoundLogger, logger)


def bind_request_context(
    *,
    request_id: str | None = None,
    project_id: str | None = None,
    run_id: str | None = None,
    **extra: Any,
) -> None:
    """Bind correlation IDs to the current contextvars scope."""

    bindings: dict[str, Any] = {}
    if request_id is not None:
        bindings["request_id"] = request_id
    if project_id is not None:
        bindings["project_id"] = project_id
    if run_id is not None:
        bindings["run_id"] = run_id
    bindings.update(extra)
    if bindings:
        bind_contextvars(**bindings)


def unbind_request_context(*keys: str) -> None:
    """Remove the supplied keys from the current logging context."""

    if keys:
        unbind_contextvars(*keys)


def clear_request_context() -> None:
    """Drop every contextvar binding set via :func:`bind_request_context`."""

    clear_contextvars()
