import inspect
import importlib
import importlib.util
import unittest

import minos_core.edit_patch as edit_patch
import minos_core.pipeline as pipeline
import minos_core.three_table_linkage as three_table_linkage
from minos_core.edit_patch import (
    _build_review_dashboard,
    _manual_review_items_from_edit_gate,
    _manual_review_payload,
)
from minos_core.three_table_result import (
    build_three_table_generation_envelope,
    dedupe_strings,
    three_table_manual_review,
)


class ArchitectureSeamTests(unittest.TestCase):
    def test_three_table_result_helpers_are_not_shadowed_in_pipeline(self):
        self.assertIs(pipeline._dedupe_strings, dedupe_strings)
        self.assertIs(pipeline._three_table_manual_review, three_table_manual_review)
        self.assertIs(
            pipeline._three_table_generation_envelope.__globals__[
                "build_three_table_generation_envelope"
            ],
            build_three_table_generation_envelope,
        )

    def test_edit_patch_uses_three_table_result_for_manual_review(self):
        reports = importlib.import_module("minos_core.edit_patch_reports")

        self.assertIs(reports.three_table_manual_review, three_table_manual_review)
        self.assertFalse(hasattr(edit_patch, "_three_table_manual_review"))
        self.assertNotIn(
            "from .pipeline import _three_table_manual_review",
            inspect.getsource(edit_patch) + inspect.getsource(reports),
        )

    def test_edit_patch_report_builders_live_behind_report_seam(self):
        self.assertIsNotNone(importlib.util.find_spec("minos_core.edit_patch_reports"))

        reports = importlib.import_module("minos_core.edit_patch_reports")
        self.assertIs(_build_review_dashboard, reports.build_review_dashboard)
        self.assertIs(_manual_review_payload, reports.build_manual_review_payload)
        self.assertIs(
            _manual_review_items_from_edit_gate,
            reports.manual_review_items_from_edit_gate,
        )

    def test_three_table_linkage_sync_view_lives_behind_report_seam(self):
        self.assertIsNotNone(
            importlib.util.find_spec("minos_core.three_table_linkage_reports")
        )
        reports = importlib.import_module("minos_core.three_table_linkage_reports")
        self.assertIs(
            three_table_linkage._build_sync_snapshot,
            reports.build_sync_snapshot,
        )
        self.assertIs(
            three_table_linkage._build_sync_issues,
            reports.build_sync_issues,
        )
        self.assertIs(
            three_table_linkage._build_sync_suggestions,
            reports.build_sync_suggestions,
        )


if __name__ == "__main__":
    unittest.main()
