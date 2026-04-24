"""Input and file-system adapters."""

from .fixture_json import load_fixture_payload
from .legacy_excel import convert_legacy_workbook

__all__ = ["convert_legacy_workbook", "load_fixture_payload"]
