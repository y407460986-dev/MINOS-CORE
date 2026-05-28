"""In-process plugin registry for MINOS-CORE extension points.

The registry stores plugin instances keyed by name. Two protocols define the
extension contract: :class:`OCREnginePlugin` for OCR engines and
:class:`KnowledgeSourcePlugin` for knowledge sources. Misuse (duplicate name,
unknown name, missing attribute) raises :class:`PluginError`, which is a
subclass of :class:`minos_core.observability.errors.MinosError` so it
participates in the project-wide error semantics (code, retriable, Chinese
user message).

The registry is deliberately small and synchronous. Hosts that want to load
plugins declared via ``pyproject.toml`` entry points should call
:func:`minos_core.plugins.entrypoints.load_entry_point_plugins` once at
startup; that function delegates to :func:`register_ocr_engine` and
:func:`register_knowledge_source` for each discovered plugin.
"""

from __future__ import annotations

from typing import Any, Iterable, Iterator, Mapping, Protocol, runtime_checkable

from ..observability.errors import MinosError

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
]


class PluginError(MinosError, RuntimeError):
    """Raised when plugin registration or lookup fails."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "MINOS_PLUGIN_ERROR",
        context: Mapping[str, Any] | None = None,
        user_message_zh: str = "插件注册或加载失败，请检查插件实现是否符合要求。",
    ) -> None:
        super().__init__(
            message,
            code=code,
            context=context,
            retriable=False,
            user_message_zh=user_message_zh,
        )


@runtime_checkable
class OCREnginePlugin(Protocol):
    """Structural protocol for an OCR engine plugin.

    Implementations must expose a ``name`` attribute (used as the registry
    key) and an ``analyze`` callable. ``analyze`` takes an iterable of
    drawing pages plus a context mapping and returns a result dictionary that
    callers will fold into the analysis bundle.
    """

    name: str

    def analyze(
        self,
        pages: Iterable[Any],
        *,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        ...


@runtime_checkable
class KnowledgeSourcePlugin(Protocol):
    """Structural protocol for a part-family knowledge source plugin.

    Implementations must expose a ``family_key`` attribute (used as the
    registry key) and a ``load`` callable that returns a knowledge dictionary
    keyed by the conventions consumed by ``minos_core.part_family_knowledge``.
    """

    family_key: str

    def load(self) -> dict[str, Any]:
        ...


# In-process registries. Tests should call :func:`reset_registry` between
# cases to keep state isolated.
_ocr_engines: dict[str, OCREnginePlugin] = {}
_knowledge_sources: dict[str, KnowledgeSourcePlugin] = {}


def _ensure_ocr_engine(plugin: object) -> OCREnginePlugin:
    """Raise :class:`PluginError` if ``plugin`` does not satisfy the protocol."""

    if not hasattr(plugin, "name") or not isinstance(getattr(plugin, "name"), str):
        raise PluginError(
            "OCR engine plugin must expose a string 'name' attribute",
            context={"plugin_repr": repr(plugin)},
        )
    if not callable(getattr(plugin, "analyze", None)):
        raise PluginError(
            "OCR engine plugin must implement 'analyze(pages, *, context)'",
            context={"plugin_name": getattr(plugin, "name", "?")},
        )
    return plugin  # type: ignore[return-value]


def _ensure_knowledge_source(plugin: object) -> KnowledgeSourcePlugin:
    """Raise :class:`PluginError` if ``plugin`` does not satisfy the protocol."""

    family_key = getattr(plugin, "family_key", None)
    if not isinstance(family_key, str) or not family_key:
        raise PluginError(
            "Knowledge source plugin must expose a non-empty 'family_key'",
            context={"plugin_repr": repr(plugin)},
        )
    if not callable(getattr(plugin, "load", None)):
        raise PluginError(
            "Knowledge source plugin must implement 'load()'",
            context={"family_key": family_key},
        )
    return plugin  # type: ignore[return-value]


def register_ocr_engine(plugin: OCREnginePlugin) -> None:
    """Register an OCR engine plugin under its declared ``name``.

    Args:
        plugin: An object satisfying :class:`OCREnginePlugin`.

    Raises:
        PluginError: If the plugin does not satisfy the protocol or another
            engine with the same name is already registered.
    """

    engine = _ensure_ocr_engine(plugin)
    if engine.name in _ocr_engines:
        raise PluginError(
            f"OCR engine '{engine.name}' is already registered",
            context={"plugin_name": engine.name},
        )
    _ocr_engines[engine.name] = engine


def register_knowledge_source(plugin: KnowledgeSourcePlugin) -> None:
    """Register a knowledge source plugin under its ``family_key``.

    Args:
        plugin: An object satisfying :class:`KnowledgeSourcePlugin`.

    Raises:
        PluginError: If the plugin does not satisfy the protocol or another
            source with the same ``family_key`` is already registered.
    """

    source = _ensure_knowledge_source(plugin)
    if source.family_key in _knowledge_sources:
        raise PluginError(
            f"Knowledge source '{source.family_key}' is already registered",
            context={"family_key": source.family_key},
        )
    _knowledge_sources[source.family_key] = source


def get_ocr_engine(name: str) -> OCREnginePlugin:
    """Look up an OCR engine plugin by ``name``.

    Raises:
        PluginError: If ``name`` is not registered.
    """

    try:
        return _ocr_engines[name]
    except KeyError as exc:
        raise PluginError(
            f"OCR engine '{name}' is not registered",
            context={"plugin_name": name, "available": sorted(_ocr_engines)},
        ) from exc


def get_knowledge_source(family_key: str) -> KnowledgeSourcePlugin:
    """Look up a knowledge source plugin by ``family_key``.

    Raises:
        PluginError: If ``family_key`` is not registered.
    """

    try:
        return _knowledge_sources[family_key]
    except KeyError as exc:
        raise PluginError(
            f"Knowledge source '{family_key}' is not registered",
            context={
                "family_key": family_key,
                "available": sorted(_knowledge_sources),
            },
        ) from exc


def iter_ocr_engines() -> Iterator[OCREnginePlugin]:
    """Iterate over all registered OCR engine plugins."""

    return iter(list(_ocr_engines.values()))


def iter_knowledge_sources() -> Iterator[KnowledgeSourcePlugin]:
    """Iterate over all registered knowledge source plugins."""

    return iter(list(_knowledge_sources.values()))


def reset_registry() -> None:
    """Drop every registered plugin. Intended for tests and embedded hosts."""

    _ocr_engines.clear()
    _knowledge_sources.clear()
