"""Tests for release packaging, readiness, and locking."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from minos_core.release_package import (
    RELEASE_LOCK_KEY,
    build_release_readiness,
    create_next_revision,
    create_release_package,
    lock_release,
)


class ReleaseReadinessTests(unittest.TestCase):
    """Unit tests for build_release_readiness."""

    @staticmethod
    def _ready_result() -> dict:
        """A result that passes all readiness checks."""
        return {
            "document_type": "three_table_generation_result",
            "process_flow": {
                "steps": [
                    {
                        "process_step_id": "P10",
                        "sequence": 10,
                        "operation": "Cutting",
                        "review_status": "已确认",
                    }
                ]
            },
            "pfmea": {
                "rows": [
                    {
                        "pfmea_id": "PFMEA-P10-001",
                        "process_step_id": "P10",
                        "failure_mode": "Cut angle wrong",
                        "action_priority": "M",
                        "review_status": "已确认",
                    }
                ]
            },
            "control_plan": {
                "rows": [
                    {
                        "control_plan_id": "CP-P10-001",
                        "process_step_id": "P10",
                        "pfmea_id": "PFMEA-P10-001",
                        "review_status": "已确认",
                    }
                ]
            },
            "metadata": {
                "action_items": [
                    {
                        "action_id": "ACT-001",
                        "priority": "medium",
                        "status": "closed",
                    }
                ],
                "knowledge_recommendations": [],
            },
            "linkage_report": {
                "sync_issues": [],
            },
        }

    @staticmethod
    def _blocked_result() -> dict:
        """A result with blocker-level sync issues and unconfirmed rows."""
        return {
            "document_type": "three_table_generation_result",
            "process_flow": {
                "steps": [
                    {
                        "process_step_id": "P10",
                        "operation": "Cutting",
                        "review_status": "人工新增",
                    }
                ]
            },
            "pfmea": {
                "rows": [
                    {
                        "pfmea_id": "PFMEA-P10-001",
                        "process_step_id": "P10",
                        "failure_mode": "Cut angle wrong",
                        "action_priority": "H",
                        "review_status": "",
                    }
                ]
            },
            "control_plan": {
                "rows": [
                    {
                        "control_plan_id": "CP-P10-001",
                        "process_step_id": "P10",
                        "pfmea_id": "PFMEA-P10-001",
                        "review_status": "",
                    }
                ]
            },
            "metadata": {
                "action_items": [
                    {
                        "action_id": "ACT-001",
                        "priority": "high",
                        "status": "open",
                    }
                ],
                "knowledge_recommendations": [
                    {"id": "REC-001", "status": "unresolved"},
                ],
            },
            "linkage_report": {
                "sync_issues": [
                    {"severity": "blocker", "message": "CP 行缺少 PFD 链接"},
                ],
            },
        }

    # ------------------------------------------------------------------
    # test_build_release_readiness (ready)
    # ------------------------------------------------------------------

    def test_build_release_readiness_ready(self):
        result = self._ready_result()
        readiness = build_release_readiness(result)
        self.assertTrue(readiness["allowed"])
        self.assertEqual(readiness["status"], "ready")
        self.assertEqual(readiness["blocking_count"], 0)

        checks_by_id = {c["check_id"]: c for c in readiness["checks"]}
        self.assertEqual(checks_by_id["sync_complete"]["status"], "passed")
        self.assertEqual(checks_by_id["rows_confirmed"]["status"], "passed")
        self.assertEqual(checks_by_id["recommendations_handled"]["status"], "passed")

    # ------------------------------------------------------------------
    # test_build_release_readiness (blocked)
    # ------------------------------------------------------------------

    def test_build_release_readiness_blocked(self):
        result = self._blocked_result()
        readiness = build_release_readiness(result)
        self.assertFalse(readiness["allowed"])
        self.assertEqual(readiness["status"], "blocked")

        checks_by_id = {c["check_id"]: c for c in readiness["checks"]}
        self.assertEqual(checks_by_id["sync_complete"]["status"], "failed")
        self.assertEqual(checks_by_id["rows_confirmed"]["status"], "failed")
        self.assertEqual(checks_by_id["recommendations_handled"]["status"], "failed")
        # actions_closed is only a warning (non-blocking)
        self.assertEqual(checks_by_id["actions_closed"]["status"], "warning")

    # ------------------------------------------------------------------
    # test_create_release_package
    # ------------------------------------------------------------------

    def test_create_release_package(self):
        result = self._ready_result()
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = create_release_package(
                result,
                output_dir=tmpdir,
                release_id="REL-TEST",
                revision="A",
                actor="tester",
            )
            self.assertEqual(manifest["release_id"], "REL-TEST")
            self.assertEqual(manifest["revision"], "A")
            self.assertTrue(manifest["readiness"]["allowed"])

            release_dir = Path(tmpdir) / "release_REL-TEST"
            self.assertTrue(release_dir.is_dir())

            manifest_file = release_dir / "release_manifest.json"
            self.assertTrue(manifest_file.exists())
            with open(manifest_file, "r", encoding="utf-8") as fh:
                disk_manifest = json.load(fh)
            self.assertEqual(disk_manifest["release_id"], "REL-TEST")

            workbook = release_dir / "unified_workbook.xlsx"
            self.assertTrue(workbook.exists())

    # ------------------------------------------------------------------
    # test_lock_release
    # ------------------------------------------------------------------

    def test_lock_release(self):
        result = self._ready_result()
        locked = lock_release(
            result,
            release_id="REL-001",
            revision="A",
            actor="engineer",
        )
        lock_info = locked["metadata"][RELEASE_LOCK_KEY]
        self.assertTrue(lock_info["locked"])
        self.assertEqual(lock_info["release_id"], "REL-001")
        self.assertEqual(lock_info["revision"], "A")
        self.assertEqual(lock_info["locked_by"], "engineer")
        self.assertGreater(len(lock_info["locked_at"]), 0)

        # Original must be unchanged
        self.assertNotIn(RELEASE_LOCK_KEY, result.get("metadata", {}))

    # ------------------------------------------------------------------
    # test_locked_release_blocks_second_lock
    # ------------------------------------------------------------------

    def test_locked_release_blocks_second_lock(self):
        result = self._ready_result()
        locked = lock_release(result, release_id="REL-001", revision="A")
        with self.assertRaises(RuntimeError) as ctx:
            lock_release(locked, release_id="REL-002", revision="B")
        self.assertIn("already locked", str(ctx.exception))

    # ------------------------------------------------------------------
    # test_create_next_revision
    # ------------------------------------------------------------------

    def test_create_next_revision(self):
        result = self._ready_result()
        locked = lock_release(result, release_id="REL-001", revision="A")
        next_rev = create_next_revision(locked, next_revision="B", actor="engineer")

        # New revision lock is reset
        new_lock = next_rev["metadata"][RELEASE_LOCK_KEY]
        self.assertFalse(new_lock["locked"])
        self.assertEqual(new_lock["revision"], "B")

        # Previous release recorded
        prev = next_rev["metadata"]["previous_release"]
        self.assertTrue(prev["locked"])
        self.assertEqual(prev["release_id"], "REL-001")
        self.assertEqual(prev["revision"], "A")
