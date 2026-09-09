"""Tests for stage collection normalization helpers."""

from minos_core.stage._utils import _dedupe_key, _dedupe_values, _list_value, _text_value


def test_dedupe_key_handles_link_and_fallback_values() -> None:
    assert _dedupe_key({"from": "P10", "to_id": "P20", "link_type": "sequence"}) == (
        "link:P10:P20:sequence"
    )
    assert _dedupe_key({"operation": "Stamping"}) == repr({"operation": "Stamping"})
    assert _dedupe_key("value") == "'value'"


def test_dedupe_values_preserves_first_occurrence() -> None:
    first = {"evidence_id": "E-1", "text": "first"}
    duplicate = {"evidence_id": "E-1", "text": "second"}
    assert _dedupe_values([first, duplicate, "x", "x"]) == [first, "x"]


def test_text_value_skips_missing_and_blank_fields() -> None:
    assert _text_value({"a": None, "b": "  ", "c": 42}, "a", "b", "c") == "42"
    assert _text_value({}, "missing") == ""


def test_list_value_normalizes_supported_shapes() -> None:
    assert _list_value({"value": None}, "value") == []
    assert _list_value({"value": [1, 2]}, "value") == [1, 2]
    assert _list_value({"value": (1, 2)}, "value") == [1, 2]
    assert set(_list_value({"value": {1, 2}}, "value")) == {1, 2}
    assert _list_value({"value": " item "}, "value") == ["item"]
    assert _list_value({"value": "  "}, "value") == []
