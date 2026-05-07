"""Tests for audit trail event recording."""

from __future__ import annotations

import unittest

from minos_core.audit_trail import (
    append_audit_event,
    audit_summary,
    build_audit_event,
)


class AuditTrailTests(unittest.TestCase):
    """Unit tests for audit event construction and recording."""

    @staticmethod
    def _minimal_result() -> dict:
        return {
            "document_type": "three_table_generation_result",
            "metadata": {},
        }

    # ------------------------------------------------------------------
    # test_build_audit_event
    # ------------------------------------------------------------------

    def test_build_audit_event(self):
        event = build_audit_event(
            entity_type="pfmea",
            entity_id="PFMEA-P10-001",
            action="edit",
            reason="修正失效原因描述",
            before={"failure_cause": "A"},
            after={"failure_cause": "B"},
        )
        self.assertTrue(event["event_id"].startswith("AUDIT-"))
        self.assertTrue(len(event["timestamp"]) > 0)
        self.assertEqual(event["entity_type"], "pfmea")
        self.assertEqual(event["entity_id"], "PFMEA-P10-001")
        self.assertEqual(event["action"], "edit")
        self.assertEqual(event["reason"], "修正失效原因描述")
        self.assertEqual(event["actor"], "local_user")
        self.assertEqual(event["source"], "desktop")
        self.assertTrue(len(event["before_hash"]) > 0)
        self.assertTrue(len(event["after_hash"]) > 0)
        self.assertNotEqual(event["before_hash"], event["after_hash"])

    # ------------------------------------------------------------------
    # test_build_audit_event_defaults
    # ------------------------------------------------------------------

    def test_build_audit_event_defaults(self):
        event = build_audit_event()
        self.assertEqual(event["entity_type"], "")
        self.assertEqual(event["entity_id"], "")
        self.assertEqual(event["action"], "")
        self.assertEqual(event["before_hash"], "")
        self.assertEqual(event["after_hash"], "")

    # ------------------------------------------------------------------
    # test_append_audit_event
    # ------------------------------------------------------------------

    def test_append_audit_event(self):
        result = self._minimal_result()
        event = build_audit_event(
            entity_type="process_step",
            entity_id="P10",
            action="confirm",
        )

        patched = append_audit_event(result, event)

        # Original must be unchanged (deep copy)
        self.assertNotIn("audit_trail", result.get("metadata", {}))

        trail = patched["metadata"]["audit_trail"]
        self.assertEqual(len(trail), 1)
        self.assertEqual(trail[0]["event_id"], event["event_id"])

    # ------------------------------------------------------------------
    # test_audit_summary
    # ------------------------------------------------------------------

    def test_audit_summary(self):
        result = self._minimal_result()
        e1 = build_audit_event(action="edit", entity_type="pfmea", entity_id="X")
        e2 = build_audit_event(action="edit", entity_type="control_plan", entity_id="Y")
        e3 = build_audit_event(action="confirm", entity_type="process_step", entity_id="Z")

        result = append_audit_event(result, e1)
        result = append_audit_event(result, e2)
        result = append_audit_event(result, e3)

        summary = audit_summary(result)
        self.assertEqual(summary["total_events"], 3)
        self.assertGreater(len(summary["last_event_at"]), 0)
        self.assertEqual(summary["actions_by_type"]["edit"], 2)
        self.assertEqual(summary["actions_by_type"]["confirm"], 1)
