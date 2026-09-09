from __future__ import annotations

import ast
import inspect
from pathlib import Path

from minos_desktop.services import DesktopRunService

PUBLIC_METHODS = {
    "run_project",
    "start_chain_run",
    "confirm_pfd_stage",
    "generate_pfmea_for_confirmed_pfd",
    "confirm_pfmea_stage",
    "generate_cp_for_confirmed_pfmea",
    "confirm_cp_stage",
    "regenerate_pfmea_stage",
    "regenerate_cp_stage",
    "get_chain_state",
    "save_chain_run",
    "save_result",
    "save_run",
    "get_run",
    "list_recent_runs",
    "restore_run",
    "apply_edit_patch_to_run",
    "refresh_run_result",
    "handle_recommendation",
    "resolve_change_impact",
    "batch_confirm_automation_review",
    "accept_automation_fix_suggestion",
    "apply_recommendation_to_run",
    "ignore_recommendation_in_run",
    "resolve_action_in_run",
    "review_dashboard",
    "preview_edit_patch_for_run",
    "apply_live_edit_to_run",
    "save_with_undo",
    "undo_run",
    "redo_run",
    "export_run",
}


def test_facade_explicitly_declares_the_32_public_methods() -> None:
    declared = {
        name for name, value in DesktopRunService.__dict__.items() if callable(value) and not name.startswith("_")
    }
    assert declared == PUBLIC_METHODS
    assert "__getattr__" not in DesktopRunService.__dict__


def test_composed_services_share_repository_and_history(tmp_path: Path) -> None:
    service = DesktopRunService(tmp_path / "desktop.sqlite3")

    assert service._chain.repository is service.repository
    assert service._edit.repository is service.repository
    assert service._export.repository is service.repository
    assert service._edit.history is service.history


def test_implementation_modules_do_not_import_facade_or_each_other_backwards() -> None:
    services_dir = Path(inspect.getfile(DesktopRunService)).parent
    for filename in (
        "run_chain_service.py",
        "run_edit_service.py",
        "run_export_service.py",
        "run_edit_helpers.py",
        "run_record_mapper.py",
    ):
        tree = ast.parse((services_dir / filename).read_text(encoding="utf-8"))
        imported = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        assert not any(module.endswith(("run_service", "run_core")) for module in imported), filename


def test_chain_analyzer_is_an_explicit_call_dependency() -> None:
    from minos_desktop.services.run_chain_service import ChainGenerationService

    signature = inspect.signature(ChainGenerationService.start_chain_run)
    assert "analyzer" in signature.parameters
