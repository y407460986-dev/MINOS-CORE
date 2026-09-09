"""Tests for minos_core.action_tracking."""

from __future__ import annotations

import unittest
from datetime import date

from minos_core.action_tracking import (
    action_items_summary,
    build_action_items,
    unresolved_action_items,
)


def _make_pfmea_row(**overrides):
    """Build a minimal valid PFMEA row dict for testing."""
    row = {
        "pfmea_id": "PFMEA-P10-001",
        "process_step_id": "P10",
        "action_priority": "L",
        "severity": 3,
        "recommended_action": "",
        "responsibility": "",
        "target_date": "",
        "action_status": "",
        "deleted": False,
    }
    row.update(overrides)
    return row


def _make_source(*rows):
    """Wrap a list of PFMEA rows into a source dict."""
    return {"pfmea": {"rows": list(rows)}}


class BuildActionItemsTests(unittest.TestCase):
    """Tests for build_action_items()."""

    def test_high_ap_generates_high_priority_action(self):
        """AP=H generates a high-priority action item."""
        row = _make_pfmea_row(action_priority="H")
        items = build_action_items(_make_source(row))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["priority"], "high")
        self.assertEqual(items[0]["source_pfmea_id"], "PFMEA-P10-001")
        self.assertIn("ACT-PFMEA-P10-001-", items[0]["action_id"])

    def test_severity_9_generates_high_priority_action(self):
        """severity >= 9 generates a high-priority action item."""
        row = _make_pfmea_row(severity=9, action_priority="L")
        items = build_action_items(_make_source(row))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["priority"], "high")

    def test_recommended_action_non_empty_generates_action(self):
        """Non-empty recommended_action triggers action item generation."""
        row = _make_pfmea_row(
            recommended_action="调整冲孔间隙", action_priority="L", severity=3,
        )
        items = build_action_items(_make_source(row))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["description"], "调整冲孔间隙")

    def test_low_risk_no_action_no_item(self):
        """Low-risk row with no recommended_action should NOT generate an item."""
        row = _make_pfmea_row(action_priority="L", severity=3)
        items = build_action_items(_make_source(row))
        self.assertEqual(len(items), 0)

    def test_deleted_row_is_skipped(self):
        """A deleted row should not produce an action item."""
        row = _make_pfmea_row(action_priority="H", deleted=True)
        items = build_action_items(_make_source(row))
        self.assertEqual(len(items), 0)

    def test_action_status_open_generates_action(self):
        """A non-empty action_status that is not 'done' triggers generation."""
        row = _make_pfmea_row(
            action_status="待处理", action_priority="L", severity=3,
        )
        items = build_action_items(_make_source(row))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["status"], "open")

    def test_action_status_maps_chinese_correctly(self):
        """Chinese action_status values map to the correct English status."""
        cases = [
            ("未制定", "open"),
            ("进行中", "in_progress"),
            ("受阻", "blocked"),
            ("已忽略", "ignored"),
        ]
        for raw_status, expected in cases:
            with self.subTest(raw_status=raw_status, expected=expected):
                row = _make_pfmea_row(action_status=raw_status)
                items = build_action_items(_make_source(row))
                self.assertEqual(len(items), 1)
                self.assertEqual(
                    items[0]["status"],
                    expected,
                    f"{raw_status!r} should map to {expected!r}",
                )

    def test_owner_from_responsibility(self):
        """owner field is sourced from responsibility (with fallback to owner)."""
        row = _make_pfmea_row(
            action_priority="H", responsibility="张工", owner="李工",
        )
        items = build_action_items(_make_source(row))
        self.assertEqual(items[0]["owner"], "张工")

    def test_owner_falls_back_to_owner_field(self):
        """When responsibility is empty, owner field is used."""
        row = _make_pfmea_row(
            action_priority="H", responsibility="", owner="王工",
        )
        items = build_action_items(_make_source(row))
        self.assertEqual(items[0]["owner"], "王工")

    def test_due_date_from_target_date(self):
        """due_date is sourced from target_date."""
        row = _make_pfmea_row(action_priority="H", target_date="2026-06-15")
        items = build_action_items(_make_source(row))
        self.assertEqual(items[0]["due_date"], "2026-06-15")

    def test_description_fallback_when_recommended_action_empty(self):
        """When recommended_action is empty, a fallback description is used."""
        row = _make_pfmea_row(action_priority="H", recommended_action="")
        items = build_action_items(_make_source(row))
        self.assertIn("补充高风险", items[0]["description"])

    def test_priority_medium_for_ap_m(self):
        """AP=M yields medium priority (when severity < 9)."""
        row = _make_pfmea_row(
            action_priority="M", severity=3, recommended_action="do something",
        )
        items = build_action_items(_make_source(row))
        self.assertEqual(items[0]["priority"], "medium")

    def test_priority_low_for_ap_l(self):
        """AP=L yields low priority (when severity < 9 and status triggers)."""
        row = _make_pfmea_row(
            action_priority="L", severity=3, recommended_action="do something",
        )
        items = build_action_items(_make_source(row))
        self.assertEqual(items[0]["priority"], "low")

    def test_multiple_rows_generate_sequential_indices(self):
        """Multiple action items from the same PFMEA row get sequential ids."""
        rows = [
            _make_pfmea_row(action_priority="H", severity=3),
            _make_pfmea_row(
                action_priority="L", severity=3, recommended_action="fix",
            ),
        ]
        items = build_action_items(_make_source(*rows))
        self.assertEqual(len(items), 2)
        self.assertIn("ACT-PFMEA-P10-001-001", items[0]["action_id"])
        self.assertIn("ACT-PFMEA-P10-001-002", items[1]["action_id"])

    def test_source_from_failure_modes_key(self):
        """Source dict with 'failure_modes' key is also accepted."""
        row = _make_pfmea_row(action_priority="H")
        source = {"failure_modes": [row]}
        items = build_action_items(source)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["priority"], "high")


class UnresolvedActionItemsTests(unittest.TestCase):
    """Tests for unresolved_action_items()."""

    def _item(self, **overrides):
        """Build a minimal action item dict."""
        item = {
            "action_id": "ACT-PFMEA-P10-001-001",
            "source_pfmea_id": "PFMEA-P10-001",
            "process_step_id": "P10",
            "action_type": "risk_reduction",
            "description": "test action",
            "owner": "",
            "due_date": "",
            "status": "open",
            "priority": "high",
            "closure_evidence_refs": [],
            "manual_confirmation_event": "",
            "ignore_reason": "",
            "created_from": "pfmea",
            "closed_at": "",
            "closed_by": "",
        }
        item.update(overrides)
        return item

    def test_closed_with_evidence_not_unresolved(self):
        """Closed item with evidence is NOT unresolved."""
        item = self._item(
            status="closed", priority="low", closure_evidence_refs=["ev-001"],
        )
        unresolved = unresolved_action_items([item])
        self.assertEqual(len(unresolved), 0)

    def test_closed_without_evidence_unresolved(self):
        """Closed item without evidence IS unresolved."""
        item = self._item(
            status="closed", priority="low", closure_evidence_refs=[],
        )
        unresolved = unresolved_action_items([item])
        self.assertEqual(len(unresolved), 1)

    def test_ignored_without_reason_unresolved(self):
        """Ignored item without ignore_reason IS unresolved."""
        item = self._item(status="ignored", priority="low", ignore_reason="")
        unresolved = unresolved_action_items([item])
        self.assertEqual(len(unresolved), 1)

    def test_ignored_with_reason_not_unresolved(self):
        """Ignored item with ignore_reason is NOT unresolved."""
        item = self._item(
            status="ignored", priority="low",
            ignore_reason="风险可接受，无需处理",
        )
        unresolved = unresolved_action_items([item])
        self.assertEqual(len(unresolved), 0)

    def test_overdue_not_closed_unresolved(self):
        """Overdue item that is neither closed nor ignored IS unresolved."""
        item = self._item(status="open", priority="low", due_date="2020-01-01")
        today = date(2026, 4, 28)
        unresolved = unresolved_action_items([item], today=today)
        self.assertEqual(len(unresolved), 1)

    def test_overdue_but_closed_not_unresolved(self):
        """Overdue item that IS closed is NOT unresolved (overdue check)."""
        item = self._item(
            status="closed", priority="low",
            due_date="2020-01-01", closure_evidence_refs=["ev-001"],
        )
        today = date(2026, 4, 28)
        unresolved = unresolved_action_items([item], today=today)
        self.assertEqual(len(unresolved), 0)

    def test_high_priority_open_unresolved(self):
        """High priority open item IS unresolved."""
        item = self._item(status="open", priority="high")
        unresolved = unresolved_action_items([item])
        self.assertEqual(len(unresolved), 1)

    def test_high_priority_ignored_not_unresolved(self):
        """High priority ignored item with reason is NOT unresolved."""
        item = self._item(
            status="ignored", priority="high",
            ignore_reason="经过评审，风险可控",
        )
        unresolved = unresolved_action_items([item])
        self.assertEqual(len(unresolved), 0)

    def test_closed_with_manual_confirmation_not_unresolved(self):
        """Closed item with manual_confirmation_event (but no evidence refs)
        is NOT unresolved."""
        item = self._item(
            status="closed", priority="low",
            closure_evidence_refs=[],
            manual_confirmation_event="人工确认通过-2026-04-01",
        )
        unresolved = unresolved_action_items([item])
        self.assertEqual(len(unresolved), 0)


class ActionItemsSummaryTests(unittest.TestCase):
    """Tests for action_items_summary()."""

    def _item(self, idx=1, **overrides):
        item = {
            "action_id": f"ACT-PFMEA-P10-001-{idx:03d}",
            "source_pfmea_id": "PFMEA-P10-001",
            "process_step_id": "P10",
            "action_type": "risk_reduction",
            "description": "test action",
            "owner": "",
            "due_date": "",
            "status": "open",
            "priority": "low",
            "closure_evidence_refs": [],
            "manual_confirmation_event": "",
            "ignore_reason": "",
            "created_from": "pfmea",
            "closed_at": "",
            "closed_by": "",
        }
        item.update(overrides)
        return item

    def test_summary_counts_correct(self):
        """Summary reports open/overdue/closed/unresolved/high-priority counts."""
        items = [
            self._item(1, status="open", priority="high", due_date="2020-01-01"),
            self._item(2, status="in_progress", priority="medium"),
            self._item(3, status="blocked", priority="low"),
            self._item(4, status="closed", priority="high", closure_evidence_refs=["ev-001"]),
            self._item(5, status="ignored", priority="low", ignore_reason="ok"),
            self._item(6, status="closed", priority="low"),
            self._item(7, status="ignored", priority="low"),
            self._item(8, status="open", priority="high", due_date="2020-01-01"),
        ]
        today = date(2026, 4, 28)
        summary = action_items_summary(items, today=today)

        self.assertEqual(summary["total"], 8)
        self.assertEqual(summary["open"], 2)
        self.assertEqual(summary["in_progress"], 1)
        self.assertEqual(summary["blocked"], 1)
        self.assertEqual(summary["closed"], 2)
        self.assertEqual(summary["ignored"], 2)
        self.assertEqual(summary["overdue"], 2)
        self.assertEqual(summary["high_priority"], 3)
        self.assertEqual(summary["unresolved"], 4)
        self.assertEqual(summary["high_priority_unresolved"], 2)


if __name__ == "__main__":
    unittest.main()
