"""Plugin extension points for MINOS-CORE.

This package exposes a small registry that lets third parties contribute new
OCR engines and knowledge sources without forking the core. The registry is
deliberately minimal: an in-process dictionary keyed by name, plus an
entry-point loader that discovers plugins shipped via ``pyproject.toml``.

Two extension surfaces are supported:

* :data:`OCREnginePlugin` -- structural protocol describing an OCR engine.
  Implementations must define a ``name`` attribute and an ``analyze`` method
  that accepts iterable drawing pages plus a context mapping.
* :data:`KnowledgeSourcePlugin` -- structural protocol describing a part
  family knowledge source. Implementations must expose a ``family_key``
  attribute and a ``load`` method returning a knowledge dictionary.

Public API
----------

``register_ocr_engine`` and ``register_knowledge_source`` register concrete
plugin instances. ``get_ocr_engine`` and ``get_knowledge_source`` look up a
plugin by name. ``iter_ocr_engines`` and ``iter_knowledge_sources`` iterate the
registered set. ``load_entry_point_plugins`` discovers and registers plugins
declared via the ``minos_core.ocr_engines`` and ``minos_core.knowledge_sources``
entry-point groups; failures are logged and never crash the host.

The plugin registry is not yet wired into the live pipeline. Hosts that wish
to opt in should call ``load_entry_point_plugins()`` once at startup and then
look up plugins by name.
"""

from __future__ import annotations

from .entrypoints import (
    KNOWLEDGE_SOURCES_GROUP,
    OCR_ENGINES_GROUP,
    load_entry_point_plugins,
)
from .registry import (
    KnowledgeSourcePlugin,
    OCREnginePlugin,
    PluginError,
    get_knowledge_source,
    get_ocr_engine,
    iter_knowledge_sources,
    iter_ocr_engines,
    register_knowledge_source,
    register_ocr_engine,
    reset_registry,
)

__all__ = [
    "OCREnginePlugin",
    "KnowledgeSourcePlugin",
    "PluginError",
    "register_ocr_engine",
    "register_knowledge_source",
    "get_ocr_engine",
    "get_knowledge_source",
    "iter_ocr_engines",
    "iter_knowledge_sources",
    "reset_registry",
    "load_entry_point_plugins",
    "OCR_ENGINES_GROUP",
    "KNOWLEDGE_SOURCES_GROUP",
]
