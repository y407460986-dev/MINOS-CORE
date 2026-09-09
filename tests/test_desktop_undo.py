import os
import tempfile
import unittest

from minos_desktop.services import DesktopRunService


class TestDesktopRunServiceUndo(unittest.TestCase):
    """Service-layer undo/redo tests for the desktop sidecar."""

    def make_result(self, operation="Before", status="needs_review"):
        return {
            "status": status,
            "process_flow": {
                "steps": [
                    {
                        "process_step_id": "P10",
                        "operation": operation,
                        "needs_confirmation": True,
                    }
                ]
            },
            "pfmea": {"rows": []},
            "control_plan": {"rows": []},
            "manual_review": {"required": status == "needs_review", "items": []},
        }

    def test_save_with_undo_allows_undo_and_redo_current_result(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            run = run_service.save_result(None, self.make_result("Before"), tmpdir)

            saved = run_service.save_with_undo(run.id, self.make_result("After", "draft_ready"))
            undone = run_service.undo_run(run.id)
            redone = run_service.redo_run(run.id)
            reloaded = run_service.get_run(run.id)

        self.assertEqual(saved.current_result["process_flow"]["steps"][0]["operation"], "After")
        self.assertEqual(undone.current_result["process_flow"]["steps"][0]["operation"], "Before")
        self.assertEqual(redone.current_result["process_flow"]["steps"][0]["operation"], "After")
        self.assertEqual(reloaded.current_result["process_flow"]["steps"][0]["operation"], "After")
        self.assertEqual(reloaded.state.status, "draft_ready")

    def test_new_save_after_undo_clears_redo_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "desktop.sqlite3")
            run_service = DesktopRunService(db_path)
            run = run_service.save_result(None, self.make_result("Initial"), tmpdir)

            run_service.save_with_undo(run.id, self.make_result("First edit"))
            self.assertEqual(
                run_service.undo_run(run.id).current_result["process_flow"]["steps"][0]["operation"],
                "Initial",
            )
            run_service.save_with_undo(run.id, self.make_result("Second edit"))
            redone = run_service.redo_run(run.id)
            reloaded = run_service.get_run(run.id)

        self.assertIsNone(redone)
        self.assertEqual(reloaded.current_result["process_flow"]["steps"][0]["operation"], "Second edit")


if __name__ == "__main__":
    unittest.main()
