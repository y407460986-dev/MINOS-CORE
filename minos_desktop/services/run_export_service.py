"""Export responsibility for desktop runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app_state import DesktopRunRecord
from .history_store import DesktopHistoryStore
from .run_edit_helpers import _evaluate_edit_export_gate
from .run_record_mapper import _stored_result_parts
from .run_repository import RunRepository
from .run_shared import _export_edited_three_tables


class RunExportService:
    def __init__(self, repository: RunRepository, history: DesktopHistoryStore) -> None:
        self.repository = repository
        self.history = history

    def get_run(self, run_id: int) -> DesktopRunRecord:
        return self.repository.get_run(run_id)

    def export_run(self, run_id: int, output_dir: str | Path, export_mode: str = "draft") -> dict[str, Any]:
        if export_mode not in {"draft", "final"}:
            raise ValueError("export_mode must be 'draft' or 'final'")
        record = self.get_run(run_id)
        stored = _stored_result_parts(record.raw_result)
        result = stored["current_result"]
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        exported = _export_edited_three_tables(result, output_path, export_mode)
        return {
            "run_id": run_id,
            "export_mode": export_mode,
            "output_dir": str(output_path),
            "exports": exported.get("exports", exported) if isinstance(exported, dict) else {"export": str(exported)},
            "quality_gate": _evaluate_edit_export_gate(result),
            "export_result": exported,
        }
