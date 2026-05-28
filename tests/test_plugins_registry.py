"""Tests for the in-process plugin registry."""

from __future__ import annotations

import unittest
from typing import Any, Iterable, Mapping

from minos_core.observability.errors import MinosError
from minos_core.plugins import (
    PluginError,
    get_knowledge_source,
    get_ocr_engine,
    iter_knowledge_sources,
    iter_ocr_engines,
    register_knowledge_source,
    register_ocr_engine,
    reset_registry,
)


class _DummyOCREngine:
    """Minimal OCR engine plugin used as a fixture."""

    def __init__(self, name: str = "dummy") -> None:
        self.name = name
        self.calls: list[tuple[Any, Mapping[str, Any]]] = []

    def analyze(
        self,
        pages: Iterable[Any],
        *,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        materialised = list(pages)
        self.calls.append((materialised, dict(context)))
        return {"engine": self.name, "page_count": len(materialised)}


class _DummyKnowledgeSource:
    """Minimal knowledge source plugin used as a fixture."""

    def __init__(self, family_key: str = "demo_family") -> None:
        self.family_key = family_key

    def load(self) -> dict[str, Any]:
        return {"family_key": self.family_key, "rules": []}


class _MissingNameOCREngine:
    """Plugin missing the required ``name`` attribute."""

    def analyze(self, pages: Iterable[Any], *, context: Mapping[str, Any]) -> dict[str, Any]:
        return {}


class _MissingAnalyzeOCREngine:
    """Plugin missing the required ``analyze`` method."""

    def __init__(self) -> None:
        self.name = "no_analyze"


class _MissingFamilyKnowledgeSource:
    """Plugin missing the required ``family_key`` attribute."""

    def load(self) -> dict[str, Any]:
        return {}


class PluginRegistryOCRTests(unittest.TestCase):
    """Behaviour tests for the OCR engine registry."""

    def setUp(self) -> None:
        reset_registry()

    def tearDown(self) -> None:
        reset_registry()

    def test_register_and_retrieve_ocr_engine(self) -> None:
        engine = _DummyOCREngine(name="custom")

        register_ocr_engine(engine)
        retrieved = get_ocr_engine("custom")

        self.assertIs(retrieved, engine)
        result = retrieved.analyze([1, 2, 3], context={"project": "p1"})
        self.assertEqual(result["engine"], "custom")
        self.assertEqual(result["page_count"], 3)

    def test_iter_ocr_engines_returns_registered_plugins(self) -> None:
        a = _DummyOCREngine("a")
        b = _DummyOCREngine("b")
        register_ocr_engine(a)
        register_ocr_engine(b)

        engines = list(iter_ocr_engines())

        self.assertEqual({engine.name for engine in engines}, {"a", "b"})

    def test_duplicate_registration_raises_plugin_error(self) -> None:
        register_ocr_engine(_DummyOCREngine("dup"))

        with self.assertRaises(PluginError) as ctx:
            register_ocr_engine(_DummyOCREngine("dup"))

        self.assertIn("already registered", str(ctx.exception))
        self.assertIsInstance(ctx.exception, MinosError)
        self.assertEqual(ctx.exception.code, "MINOS_PLUGIN_ERROR")

    def test_get_unknown_engine_raises_plugin_error(self) -> None:
        with self.assertRaises(PluginError) as ctx:
            get_ocr_engine("missing")

        self.assertEqual(ctx.exception.context.get("plugin_name"), "missing")

    def test_protocol_violation_missing_name_is_rejected(self) -> None:
        with self.assertRaises(PluginError):
            register_ocr_engine(_MissingNameOCREngine())  # type: ignore[arg-type]

    def test_protocol_violation_missing_analyze_is_rejected(self) -> None:
        with self.assertRaises(PluginError):
            register_ocr_engine(_MissingAnalyzeOCREngine())  # type: ignore[arg-type]


class PluginRegistryKnowledgeSourceTests(unittest.TestCase):
    """Behaviour tests for the knowledge source registry."""

    def setUp(self) -> None:
        reset_registry()

    def tearDown(self) -> None:
        reset_registry()

    def test_register_and_retrieve_knowledge_source(self) -> None:
        source = _DummyKnowledgeSource(family_key="bracket")

        register_knowledge_source(source)
        retrieved = get_knowledge_source("bracket")

        self.assertIs(retrieved, source)
        self.assertEqual(retrieved.load()["family_key"], "bracket")

    def test_duplicate_family_key_raises_plugin_error(self) -> None:
        register_knowledge_source(_DummyKnowledgeSource("dup"))

        with self.assertRaises(PluginError):
            register_knowledge_source(_DummyKnowledgeSource("dup"))

    def test_get_unknown_family_raises_plugin_error(self) -> None:
        with self.assertRaises(PluginError) as ctx:
            get_knowledge_source("not_there")

        self.assertEqual(ctx.exception.context.get("family_key"), "not_there")

    def test_iter_returns_registered_sources(self) -> None:
        register_knowledge_source(_DummyKnowledgeSource("alpha"))
        register_knowledge_source(_DummyKnowledgeSource("beta"))

        keys = sorted(plugin.family_key for plugin in iter_knowledge_sources())

        self.assertEqual(keys, ["alpha", "beta"])

    def test_protocol_violation_missing_family_key_is_rejected(self) -> None:
        with self.assertRaises(PluginError):
            register_knowledge_source(_MissingFamilyKnowledgeSource())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
