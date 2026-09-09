"""Discover plugins from ``importlib.metadata`` entry points.

MINOS-CORE recognises two entry-point groups:

* ``minos_core.ocr_engines`` -- each entry point loads to an instance (or
  zero-argument factory) implementing :class:`~minos_core.plugins.OCREnginePlugin`.
* ``minos_core.knowledge_sources`` -- each entry point loads to an instance
  (or zero-argument factory) implementing
  :class:`~minos_core.plugins.KnowledgeSourcePlugin`.

Hosts opt into discovery by calling :func:`load_entry_point_plugins` once at
startup. Failures during discovery are logged via the project structured
logger and never propagate, so a broken third-party plugin cannot crash the
host process.
"""

from __future__ import annotations

import importlib.metadata as importlib_metadata
from collections.abc import Iterable
from typing import Any

from ..observability.logging import get_logger
from .registry import (
    PluginError,
    register_knowledge_source,
    register_ocr_engine,
)

__all__ = [
    "OCR_ENGINES_GROUP",
    "KNOWLEDGE_SOURCES_GROUP",
    "load_entry_point_plugins",
]

OCR_ENGINES_GROUP = "minos_core.ocr_engines"
KNOWLEDGE_SOURCES_GROUP = "minos_core.knowledge_sources"

_logger = get_logger("minos_core.plugins.entrypoints")


def _select_entry_points(group: str) -> Iterable[importlib_metadata.EntryPoint]:
    """Return the entry points registered for ``group``.

    Wraps the API differences between Python 3.10 and 3.12: ``entry_points``
    accepts a ``group=`` keyword on modern Python, but older fallbacks return
    a dict-like object. We tolerate both shapes.
    """

    try:
        eps = importlib_metadata.entry_points()
    except Exception as exc:  # pragma: no cover - defensive
        _logger.warning(
            "plugins.entrypoints.discover_failed",
            group=group,
            error=str(exc),
            error_type=exc.__class__.__name__,
        )
        return []

    select = getattr(eps, "select", None)
    if callable(select):
        try:
            return list(select(group=group))
        except Exception as exc:  # pragma: no cover - defensive
            _logger.warning(
                "plugins.entrypoints.select_failed",
                group=group,
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
            return []
    if isinstance(eps, dict):
        return list(eps.get(group, []))
    return [ep for ep in eps if getattr(ep, "group", None) == group]


def _materialise(entry_point: importlib_metadata.EntryPoint) -> Any:
    """Load the entry point and, if it is a zero-arg callable, invoke it."""

    obj = entry_point.load()
    if callable(obj) and not hasattr(obj, "name") and not hasattr(obj, "family_key"):
        # Treat callables that don't already look like plugin instances as
        # zero-argument factories. Plugin classes themselves are callable, so
        # we use the presence of the protocol attributes as the disambiguator.
        try:
            obj = obj()
        except TypeError:
            # Probably a class with required constructor args; surface as-is
            # so the registry rejects it with a clearer error.
            return obj
    return obj


def _load_group(
    group: str,
    register: Any,
    *,
    label: str,
) -> int:
    """Load every entry point in ``group`` and register each one.

    Returns the number of successfully registered plugins.
    """

    registered = 0
    for entry_point in _select_entry_points(group):
        ep_name = getattr(entry_point, "name", "?")
        try:
            plugin = _materialise(entry_point)
        except Exception as exc:
            _logger.warning(
                "plugins.entrypoints.load_failed",
                group=group,
                entry_point=ep_name,
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
            continue
        try:
            register(plugin)
        except PluginError as exc:
            _logger.warning(
                "plugins.entrypoints.register_rejected",
                group=group,
                entry_point=ep_name,
                error=str(exc),
                error_code=exc.code,
            )
            continue
        except Exception as exc:  # pragma: no cover - defensive
            _logger.warning(
                "plugins.entrypoints.register_failed",
                group=group,
                entry_point=ep_name,
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
            continue
        registered += 1
        _logger.info(
            "plugins.entrypoints.registered",
            group=group,
            entry_point=ep_name,
            label=label,
        )
    return registered


def load_entry_point_plugins() -> dict[str, int]:
    """Discover and register every plugin declared via entry points.

    Returns:
        A summary mapping ``{"ocr_engines": int, "knowledge_sources": int}``
        with the number of plugins successfully registered in each group.
    """

    summary = {
        "ocr_engines": _load_group(
            OCR_ENGINES_GROUP, register_ocr_engine, label="ocr_engine"
        ),
        "knowledge_sources": _load_group(
            KNOWLEDGE_SOURCES_GROUP,
            register_knowledge_source,
            label="knowledge_source",
        ),
    }
    _logger.info("plugins.entrypoints.summary", **summary)
    return summary
