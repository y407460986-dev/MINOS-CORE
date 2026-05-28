"""Tests for entry-point based plugin discovery."""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import unittest
from typing import Any, Iterable, Mapping
from unittest import mock

from minos_core.plugins import (
    OCR_ENGINES_GROUP,
    KNOWLEDGE_SOURCES_GROUP,
    PluginError,
    get_knowledge_source,
    get_ocr_engine,
    load_entry_point_plugins,
    register_ocr_engine,
    reset_registry,
)


class _GoodOCREngine:
    """OCR engine plugin used as a fixture during entry-point loading."""

    def __init__(self, name: str = "fake") -> None:
        self.name = name

    def analyze(
        self,
        pages: Iterable[Any],
        *,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {"engine": self.name}


class _GoodKnowledgeSource:
    """Knowledge source plugin used as a fixture during entry-point loading."""

    def __init__(self, family_key: str = "fake_family") -> None:
        self.family_key = family_key

    def load(self) -> dict[str, Any]:
        return {"family_key": self.family_key}


def _good_ocr_factory() -> _GoodOCREngine:
    return _GoodOCREngine("from_factory")


def _broken_factory() -> _GoodOCREngine:
    raise RuntimeError("synthetic plugin import failure")


class _FakeEntryPoint:
    """Stand-in for ``importlib.metadata.EntryPoint`` we can drive in tests."""

    def __init__(self, name: str, group: str, value: Any) -> None:
        self.name = name
        self.group = group
        self._value = value

    def load(self) -> Any:
        if isinstance(self._value, BaseException):
            raise self._value
        return self._value


class _FakeEntryPoints:
    """Mimic the dual-shape return value of ``entry_points()``.

    Modern Python returns a ``SelectableGroups`` with ``.select(group=...)``;
    older callers passed a dict. Both are exercised here.
    """

    def __init__(self, entries: list[_FakeEntryPoint]) -> None:
        self._entries = entries

    def select(self, *, group: str) -> list[_FakeEntryPoint]:
        return [ep for ep in self._entries if ep.group == group]


def _patch_entry_points(entries: list[_FakeEntryPoint]) -> mock._patch:
    """Patch ``importlib.metadata.entry_points`` used by the loader module."""

    return mock.patch.object(
        importlib_metadata,
        "entry_points",
        return_value=_FakeEntryPoints(entries),
    )


class EntryPointDiscoveryTests(unittest.TestCase):
    """End-to-end tests for :func:`load_entry_point_plugins`."""

    def setUp(self) -> None:
        reset_registry()

    def tearDown(self) -> None:
        reset_registry()

    def test_loads_ocr_and_knowledge_plugins(self) -> None:
        entries = [
            _FakeEntryPoint("ocr_a", OCR_ENGINES_GROUP, _GoodOCREngine("ocr_a")),
            _FakeEntryPoint(
                "kb_a", KNOWLEDGE_SOURCES_GROUP, _GoodKnowledgeSource("kb_a")
            ),
        ]

        with _patch_entry_points(entries):
            summary = load_entry_point_plugins()

        self.assertEqual(summary, {"ocr_engines": 1, "knowledge_sources": 1})
        self.assertEqual(get_ocr_engine("ocr_a").name, "ocr_a")
        self.assertEqual(get_knowledge_source("kb_a").family_key, "kb_a")

    def test_factory_callable_is_invoked(self) -> None:
        entries = [
            _FakeEntryPoint("factory", OCR_ENGINES_GROUP, _good_ocr_factory),
        ]

        with _patch_entry_points(entries):
            summary = load_entry_point_plugins()

        self.assertEqual(summary["ocr_engines"], 1)
        self.assertEqual(get_ocr_engine("from_factory").name, "from_factory")

    def test_failed_load_does_not_crash_host(self) -> None:
        good = _GoodOCREngine("survivor")
        entries = [
            _FakeEntryPoint(
                "broken", OCR_ENGINES_GROUP, RuntimeError("plugin import failed")
            ),
            _FakeEntryPoint("survivor", OCR_ENGINES_GROUP, good),
        ]

        with _patch_entry_points(entries):
            summary = load_entry_point_plugins()

        self.assertEqual(summary["ocr_engines"], 1)
        self.assertEqual(get_ocr_engine("survivor").name, "survivor")
        with self.assertRaises(PluginError):
            get_ocr_engine("broken")

    def test_factory_that_raises_is_skipped(self) -> None:
        entries = [
            _FakeEntryPoint("broken_factory", OCR_ENGINES_GROUP, _broken_factory),
            _FakeEntryPoint("ok", OCR_ENGINES_GROUP, _GoodOCREngine("ok")),
        ]

        with _patch_entry_points(entries):
            summary = load_entry_point_plugins()

        self.assertEqual(summary["ocr_engines"], 1)
        self.assertEqual(get_ocr_engine("ok").name, "ok")

    def test_duplicate_registration_in_entry_points_is_skipped(self) -> None:
        register_ocr_engine(_GoodOCREngine("conflict"))

        entries = [
            _FakeEntryPoint(
                "conflict", OCR_ENGINES_GROUP, _GoodOCREngine("conflict")
            ),
            _FakeEntryPoint("fresh", OCR_ENGINES_GROUP, _GoodOCREngine("fresh")),
        ]

        with _patch_entry_points(entries):
            summary = load_entry_point_plugins()

        self.assertEqual(summary["ocr_engines"], 1)
        self.assertEqual(get_ocr_engine("fresh").name, "fresh")

    def test_no_entry_points_returns_zeroes(self) -> None:
        with _patch_entry_points([]):
            summary = load_entry_point_plugins()

        self.assertEqual(summary, {"ocr_engines": 0, "knowledge_sources": 0})


if __name__ == "__main__":
    unittest.main()
