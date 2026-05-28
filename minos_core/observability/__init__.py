"""Observability primitives for MINOS-CORE.

This package centralises three concerns that were previously scattered across
modules:

* Structured logging via :mod:`structlog` (:mod:`minos_core.observability.logging`).
* A small, semantic exception hierarchy (:mod:`minos_core.observability.errors`).
* Resource-management context managers for temp dirs and subprocesses
  (:mod:`minos_core.observability.resources`).
* Configuration provenance helpers used by ``minos-core doctor``
  (:mod:`minos_core.observability.config_diagnostics`).

Public re-exports make the intended API explicit.
"""

from .config_diagnostics import (
    ConfigSource,
    describe_config_sources,
    format_config_sources,
)
from .errors import (
    ConfigurationError,
    ExternalServiceError,
    MinosError,
    PipelineError,
    ResourceError,
    ValidationError,
    format_error_for_log,
    format_error_for_user,
)
from .logging import (
    bind_request_context,
    clear_request_context,
    configure_logging,
    get_logger,
    unbind_request_context,
)
from .resources import managed_subprocess, temporary_directory

__all__ = [
    # logging
    "configure_logging",
    "get_logger",
    "bind_request_context",
    "clear_request_context",
    "unbind_request_context",
    # errors
    "MinosError",
    "ConfigurationError",
    "ValidationError",
    "ExternalServiceError",
    "ResourceError",
    "PipelineError",
    "format_error_for_user",
    "format_error_for_log",
    # resources
    "temporary_directory",
    "managed_subprocess",
    # config diagnostics
    "ConfigSource",
    "describe_config_sources",
    "format_config_sources",
]
