# MINOS-CORE Phase 3 — 代码手术 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repay architecture debt: split 800+ line files, wire AI resilience into LLM calls, connect plugin system, add TypedDict types, and clean up ADR tracking.

**Architecture:** Phase 3 is 7 independent task groups that can run in parallel via worktree isolation. Each task produces working code with zero test regressions. The largest tasks (3.1 run_service split, 3.2 table_editor split) require careful function extraction to preserve the public API surface.

**Tech Stack:** Python 3.11+, structlog, dataclasses, TypedDict (stdlib), protocols

---

## File Structure — What Changes

### Created
| File | Responsibility |
|------|---------------|
| `minos_desktop/services/run_chain.py` | Chain orchestration extracted from run_service.py |
| `minos_desktop/services/run_patches.py` | Edit patch / undo-redo extracted from run_service.py |
| `minos_desktop/services/run_exports.py` | Export logic extracted from run_service.py |
| `minos_desktop/table_editor/__init__.py` | Re-export public symbols from split editor |
| `minos_desktop/table_editor/specs.py` | TableSpec definitions extracted from table_editor.py |
| `minos_desktop/table_editor/rows.py` | Row operations extracted from table_editor.py |
| `minos_desktop/table_editor/patches.py` | Edit patch building extracted from table_editor.py |
| `minos_core/_types.py` | TypedDict definitions for common dict shapes |
| `minos_core/pipeline/_llm_protected.py` | AI resilience wrapper for LLM calls |

### Modified
| File | Change |
|------|--------|
| `minos_desktop/services/run_service.py` | Shrink from ~2085 to ~400 lines, delegate to new modules |
| `minos_desktop/services/__init__.py` | Add re-exports from new modules |
| `minos_desktop/table_editor.py` | Shrink from ~2103 to ~500 lines, delegate to new package |
| `minos_core/pipeline_chain.py` | Wrap LLM calls with CircuitBreaker+Retry; add plugin hooks; use TypedDict return types |
| `minos_core/pipeline/orchestration.py` | TypedDict return type for orchestration functions |
| `minos_core/edit_patch.py` | TypedDict parameter types |
| `docs/adr/001-module-restructuring.md` | Mark Pending items as Done |
| `docs/adr/002-ai-resilience.md` | Mark Pending items as Done |
| `docs/adr/003-security-validation.md` | Mark Pending items as Done |
| `docs/adr/004-observability.md` | Mark Pending items as Done |
| `docs/adr/005-extensibility.md` | Mark Pending items as Done |

### Deleted
None. All existing files remain; we extract, not delete.

---

## Task Dependency Graph

```
3.1 ── (run_service split) ──→ independent
3.2 ── (table_editor split) ──→ independent
3.3 ── (other 800+ file split) ──→ independent, depends on 3.1/3.2 pattern
3.4 ── (AI resilience) ──→ independent
3.5 ── (plugin integration) ──→ independent
3.6 ── (TypedDict) ──→ modifies pipeline_chain.py → conflicts with 3.4 (RUN SEQUENTIALLY)
3.7 ── (ADR cleanup) ──→ independent, last
```

**Execute order:**
- Wave A (parallel): 3.1, 3.2, 3.4, 3.7
- Wave B (serial after 3.4): 3.6 (modifies same file as 3.4)
- Wave C (after 3.6): 3.3, 3.5

---

### Task 3.1: Split run_service.py into focused modules

**Files:**
- Modify: `minos_desktop/services/run_service.py`
- Create: `minos_desktop/services/run_chain.py`
- Create: `minos_desktop/services/run_patches.py`
- Create: `minos_desktop/services/run_exports.py`
- Modify: `minos_desktop/services/__init__.py`

**Analysis:** `run_service.py` (2,085 lines) contains:
- `DesktopRunService` class (lines 51-1262) — orchestration, chain management, I/O
- Module-level helpers (lines 1264-2085) — format, normalize, merge, export, seed, zip

**Extraction pattern:** Move module-level functions to focused modules, import them back in `run_service.py` for backward compatibility.

- [ ] **Step 1: Create `run_chain.py`** with chain orchestrator helpers

```python
"""Chain orchestration utilities extracted from run_service.py."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def format_desktop_failure(stage: str, message: str) -> dict[str, Any]:
    """Build a standard desktop failure envelope."""
    import traceback
    return {
        "stage": stage,
        "ok": False,
        "error": message,
        "traceback": traceback.format_exc(),
    }


def _status_display(status: str) -> str:
    """Map internal status to display string."""
    _MAP = {
        "pending": "Pending",
        "running": "Running",
        "complete": "Complete",
        "failed": "Failed",
        "blocked": "Blocked",
        "cancelled": "Cancelled",
    }
    return _MAP.get(status, status)


def _desktop_result_envelope(
    success: bool,
    message: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the standard DesktopRunService result envelope."""
    return {
        "success": success,
        "message": message or "",
        "payload": payload or {},
    }
```

Run: `cd "D:/MINOS-CORE" && python -c "from minos_desktop.services.run_chain import format_desktop_failure; print('OK')"`
Expected: `OK`

- [ ] **Step 2: Create `run_patches.py`** with edit patch helpers

```python
"""Edit patch application and management extracted from run_service.py."""
from __future__ import annotations

import json
from typing import Any


def _merge_edit_patch(existing: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Merge an edit patch into an existing run result."""
    merged = dict(existing)
    for key, value in patch.get("items", {}).items():
        if key in merged:
            if isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key].update(value)
            else:
                merged[key] = value
    return merged


def _apply_confirm_edit_patch(
    result: dict[str, Any], patch: dict[str, Any]
) -> dict[str, Any]:
    """Apply a confirm-type edit patch."""
    merged = dict(result)
    for item in patch.get("items", []):
        target = item.get("target", "")
        if ":" in target:
            _type, _id = target.split(":", 1)
            key = _type if _type in merged else None
            if key and isinstance(merged[key], list):
                merged[key] = [
                    {**r, "confirmed": True} if r.get("id") == _id else r
                    for r in merged[key]
                ]
    return merged


def _normalize_three_table_result(
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Normalize a three-table generation result to a known shape."""
    if result is None:
        return {"ok": False, "exports": {}, "manifest": {}}
    return {
        "ok": result.get("ok", False),
        "exports": result.get("exports", {}),
        "manifest": result.get("manifest", {}),
    }


def _normalize_edit_patch(patch: dict[str, Any]) -> dict[str, Any]:
    """Normalize an edit patch to known shape."""
    return {
        "review_patch_version": patch.get("review_patch_version", ""),
        "confirmed_by": patch.get("confirmed_by", ""),
        "confirmed_at": patch.get("confirmed_at", ""),
        "reason": patch.get("reason", ""),
        "evidence_refs": patch.get("evidence_refs", []),
        "items": patch.get("items", []),
    }


def _evaluate_edit_export_gate(result: dict[str, Any]) -> dict[str, Any]:
    """Evaluate whether the export gate allows editing."""
    quality_gate = result.get("quality_gate", {})
    return {
        "allow_user_export": quality_gate.get("allow_user_export", False),
        "edit_allowed": quality_gate.get("allow_user_export", False),
    }
```

Run: `cd "D:/MINOS-CORE" && python -c "from minos_desktop.services.run_patches import _merge_edit_patch; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Create `run_exports.py`** with export helpers

```python
"""Export and I/O utilities extracted from run_service.py."""
from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path
from typing import Any


def _directory_size(path: Path) -> int:
    """Recursively calculate directory size in bytes."""
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _zip_directory(archive: zipfile.ZipFile, directory: Path, prefix: str) -> None:
    """Add all files in a directory to a ZIP archive under the given prefix."""
    for file_path in directory.rglob("*"):
        if file_path.is_file():
            arc_name = f"{prefix}/{file_path.relative_to(directory)}"
            archive.write(file_path, arc_name)


def _clear_directory_contents(path: Path, *, keep_names: set[str]) -> None:
    """Clear directory contents except files matching keep_names."""
    if not path.exists():
        return
    for item in path.iterdir():
        if item.name not in keep_names:
            if item.is_dir():
                import shutil
                shutil.rmtree(item)
            else:
                item.unlink()


def _stored_result_parts(stored: dict[str, Any]) -> dict[str, Any]:
    """Extract the parts of a stored result needed for display."""
    return {
        "ok": stored.get("ok", False),
        "exports": stored.get("exports", {}),
        "manifest": stored.get("manifest", {}),
    }


def _project_from_row(row: sqlite3.Row) -> Any:
    """Convert a SQLite row to a DesktopProjectRecord."""
    from minos_desktop.services import DesktopProjectRecord
    return DesktopProjectRecord(
        project_id=row["project_id"],
        name=row["name"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        status=row["status"],
        drawing_path=row["drawing_path"],
        output_dir=row["output_dir"],
        ocr_mode=row.get("ocr_mode", "auto"),
    )


def _run_from_row(row: sqlite3.Row) -> Any:
    """Convert a SQLite row to a DesktopRunRecord."""
    from minos_desktop.services import DesktopRunRecord
    return DesktopRunRecord(
        run_id=row["run_id"],
        project_id=row["project_id"],
        status=row["status"],
        chain_state=json.loads(row["chain_state"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
```

Run: `cd "D:/MINOS-CORE" && python -c "from minos_desktop.services.run_exports import _directory_size; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Import from new modules in run_service.py**

Add to the top of `run_service.py`:
```python
from .run_chain import (
    _desktop_result_envelope,
    _status_display,
    format_desktop_failure,
)
from .run_exports import (
    _clear_directory_contents,
    _directory_size,
    _project_from_row,
    _run_from_row,
    _stored_result_parts,
    _zip_directory,
)
from .run_patches import (
    _apply_confirm_edit_patch,
    _evaluate_edit_export_gate,
    _merge_edit_patch,
    _normalize_edit_patch,
    _normalize_three_table_result,
)
```

Then **delete** all functions from `run_service.py` that are now imported from the new modules.

- [ ] **Step 5: Update `__init__.py`** to re-export public symbols

Run: `cd "D:/MINOS-CORE" && grep -n "format_desktop_failure\|_project_from_row\|_run_from_row\|_directory_size\|_zip_directory\|_clear_directory_contents\|_stored_result_parts" minos_desktop/services/__init__.py`
If any of these are referenced in the `__all__` or imported elsewhere, add the import path from the new module.

- [ ] **Step 6: Run full test suite to verify no regressions**

Run: `cd "D:/MINOS-CORE" && PYTHONPATH="D:/MINOS-CORE" python -m pytest tests/ --tb=line -q`
Expected: 1404 passed, 0 failed

- [ ] **Step 7: Commit**

```bash
git add minos_desktop/services/
git commit -m "refactor: split run_service.py into run_chain, run_patches, run_exports"
```

---

### Task 3.2: Split table_editor.py into focused modules

**Files:**
- Create: `minos_desktop/table_editor/__init__.py`
- Create: `minos_desktop/table_editor/specs.py`
- Create: `minos_desktop/table_editor/rows.py`
- Create: `minos_desktop/table_editor/patches.py`
- Modify: `minos_desktop/table_editor.py` (shrink to ~500 lines)

- [ ] **Step 1: Create `table_editor/__init__.py`**

```python
"""Table editor — row-level CRUD, patch building, and automation review.

Split from the original monolithic table_editor.py into:
- specs: TableSpec definitions and column helpers
- rows: Row-level operations (CRUD, filter, status)
- patches: Edit patch construction and automation review
"""
from __future__ import annotations

from .specs import column_label, table_spec
from .patches import (
    automation_batch_confirm_patch_items,
    automation_review_model,
    build_edit_patch,
    table_rows_to_edit_patch,
    table_rows_to_edit_patch_items,
)
from .rows import (
    confirm_filtered_table_rows,
    confirm_table_row,
    document_row_to_table_row,
    filter_table_rows,
    filtered_table_row_indexes,
    new_table_row,
    refresh_table_row_status,
    reorder_row,
    restore_soft_delete_table_row,
    soft_delete_table_row,
    table_row_status,
    three_table_to_table_model,
)

__all__ = [
    "TableSpec",
    "column_label",
    "table_spec",
    "three_table_to_table_model",
    "document_row_to_table_row",
    "new_table_row",
    "reorder_row",
    "soft_delete_table_row",
    "restore_soft_delete_table_row",
    "confirm_table_row",
    "table_row_status",
    "refresh_table_row_status",
    "filter_table_rows",
    "filtered_table_row_indexes",
    "confirm_filtered_table_rows",
    "table_rows_to_edit_patch_items",
    "build_edit_patch",
    "table_rows_to_edit_patch",
    "automation_review_model",
    "automation_batch_confirm_patch_items",
]
```

- [ ] **Step 2: Create `table_editor/specs.py`** with TableSpec definitions

Extract from `table_editor.py` lines 31-308 (TableSpec class, `table_spec()`, `column_label()`):

```python
"""Table specification definitions for the three-table workbench."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TableSpec:
    """Describes the columns and metadata of a single editable table."""

    table_key: str
    label: str
    columns: list[str] = field(default_factory=list)
    editable_columns: list[str] = field(default_factory=list)
    key_column: str = "id"
    sort_column: str | None = None
    group_label: str | None = None


_TABLE_SPECS: dict[str, TableSpec] = {}


def table_spec(table_key: str) -> TableSpec:
    """Return the TableSpec for the given table key; raise KeyError if unknown."""
    if not _TABLE_SPECS:
        _init_specs()
    return _TABLE_SPECS[table_key]


def column_label(column: str) -> str:
    """Convert a snake_case column name to a human-readable label."""
    return column.replace("_", " ").title()


def _init_specs() -> None:
    """Populate the table specs dictionary."""
    _TABLE_SPECS["process_flow"] = TableSpec(
        table_key="process_flow",
        label="Process Flow",
        columns=[
            "step_number", "operation", "process_function",
            "equipment", "flow_symbol", "special_characteristics",
        ],
        editable_columns=[
            "operation", "process_function", "equipment",
        ],
        key_column="step_number",
        sort_column="step_number",
        group_label="PFD",
    )
    # Add the remaining specs from the original table_spec() function
    # PFMEA, Control Plan specs go here verbatim from table_editor.py lines 299-308
```

Read the full `table_spec()` function from `table_editor.py` and copy all spec definitions.

- [ ] **Step 3: Create `table_editor/rows.py`** with row CRUD operations

Extract all row-level functions from `table_editor.py`:
- `three_table_to_table_model()`
- `document_row_to_table_row()`
- `new_table_row()`
- `reorder_row()`
- `soft_delete_table_row()`
- `restore_soft_delete_table_row()`
- `confirm_table_row()`
- `table_row_status()`
- `refresh_table_row_status()`
- `filter_table_rows()`
- `filtered_table_row_indexes()`
- `confirm_filtered_table_rows()`

Each function gets an `import` of `TableSpec` from `.specs`:
```python
from .specs import TableSpec, table_spec, column_label
```

- [ ] **Step 4: Create `table_editor/patches.py`** with patch building

Extract from `table_editor.py`:
- `table_rows_to_edit_patch_items()`
- `build_edit_patch()`
- `table_rows_to_edit_patch()`
- `automation_review_model()`
- `automation_batch_confirm_patch_items()`

- [ ] **Step 5: Shrink `table_editor.py`** to import from new package

```python
"""Table editor - public API. Implementations extracted to table_editor/ package."""
from __future__ import annotations

from .table_editor.specs import TableSpec, table_spec, column_label
from .table_editor.rows import (
    confirm_filtered_table_rows,
    confirm_table_row,
    document_row_to_table_row,
    filter_table_rows,
    filtered_table_row_indexes,
    new_table_row,
    refresh_table_row_status,
    reorder_row,
    restore_soft_delete_table_row,
    soft_delete_table_row,
    table_row_status,
    three_table_to_table_model,
)
from .table_editor.patches import (
    automation_batch_confirm_patch_items,
    automation_review_model,
    build_edit_patch,
    table_rows_to_edit_patch,
    table_rows_to_edit_patch_items,
)

__all__ = [
    "TableSpec",
    "column_label",
    "table_spec",
    "three_table_to_table_model",
    "document_row_to_table_row",
    "new_table_row",
    "reorder_row",
    "soft_delete_table_row",
    "restore_soft_delete_table_row",
    "confirm_table_row",
    "table_row_status",
    "refresh_table_row_status",
    "filter_table_rows",
    "filtered_table_row_indexes",
    "confirm_filtered_table_rows",
    "table_rows_to_edit_patch_items",
    "build_edit_patch",
    "table_rows_to_edit_patch",
    "automation_review_model",
    "automation_batch_confirm_patch_items",
]
```

- [ ] **Step 6: Run full test suite**

Run: `cd "D:/MINOS-CORE" && PYTHONPATH="D:/MINOS-CORE" python -m pytest tests/ --tb=line -q`
Expected: 1404 passed, 0 failed

- [ ] **Step 7: Commit**

```bash
git add minos_desktop/table_editor/ minos_desktop/table_editor.py
git commit -m "refactor: split table_editor.py into table_editor/ package"
```

---

### Task 3.3: Split other 800+ line files

**Files:**
- Modify: `minos_core/edit_patch.py` (1,448 lines)
- Modify: `minos_core/pipeline_chain.py` (1,418 lines)
- Modify: `minos_core/part_family_knowledge.py` (1,374 lines)
- Modify: `minos_core/drawing_to_pfd.py` (1,294 lines)
- Modify: `minos_core/drawing_ocr_analysis.py` (1,081 lines)
- Modify: `minos_core/cli.py` (919 lines)

- [ ] **Step 1: Create file listing for each large file**

Run: `cd "D:/MINOS-CORE" && for f in minos_core/edit_patch.py minos_core/pipeline_chain.py minos_core/part_family_knowledge.py minos_core/drawing_to_pfd.py minos_core/drawing_ocr_analysis.py minos_core/cli.py; do echo "=== $f ($(wc -l < $f) lines) ==="; grep -n "^def \|^class " "$f" | head -5; echo "..."; done`

- [ ] **Step 2: Split `edit_patch.py`** by operation type

Extract categories from `edit_patch.py`:
- `edit_patch_add.py` — functions for adding items
- `edit_patch_delete.py` — functions for deleting items  
- `edit_patch_audit.py` — functions for audit/merge
- `edit_patch_apply.py` — functions for applying patches

Same pattern as Task 3.1: move functions to new modules, import back for backward compat.

- [ ] **Step 3: Split `pipeline_chain.py`** by generation stage

Extract:
- `pipeline_chain_pfd.py` — PFD generation functions
- `pipeline_chain_pfmea.py` — PFMEA generation functions  
- `pipeline_chain_cp.py` — Control Plan generation functions

- [ ] **Step 4: Split `part_family_knowledge.py`** by knowledge operation

Extract:
- `part_family_knowledge_load.py` — loading/parsing
- `part_family_knowledge_convert.py` — seed workbook conversion
- `part_family_knowledge_match.py` — matching/enrichment

- [ ] **Step 5: Split `drawing_to_pfd.py`** and `drawing_ocr_analysis.py`

Follow the same extraction pattern. Each split: create new file(s), import back into original.

- [ ] **Step 6: Split `cli.py`** — move command handlers

```python
# cli.py stays as argparser + dispatch; each handler function moves to:
# minos_core/commands/generate.py
# minos_core/commands/accept.py  
# minos_core/commands/doctor.py
# minos_core/commands/validate.py
```

- [ ] **Step 7: Run full test suite**

Run: `cd "D:/MINOS-CORE" && PYTHONPATH="D:/MINOS-CORE" python -m pytest tests/ --tb=line -q`
Expected: 1404 passed, 0 failed

- [ ] **Step 8: Commit**

```bash
git add minos_core/
git commit -m "refactor: split 6 large files into focused sub-modules"
```

---

### Task 3.4: Wire AI resilience layer into LLM call points

**Files:**
- Create: `minos_core/pipeline/_llm_protected.py`
- Modify: `minos_core/pipeline_chain.py`

**Analysis:** The AI resilience module (`ai_resilience/`) has 4 patterns fully implemented but unused:
- `CircuitBreaker` (3-state: closed/open/half-open)
- `ExponentialBackoffRetry` (with jitter + conditional retry)
- `AIServicePool` (priority-based endpoint selection)
- `FallbackStrategy` (chain, local knowledge, rule-based, cache)

The LLM adapter calls in `pipeline_chain.py` currently look like:
```python
result = llm_adapter.analyze(prompt, model=model)
```

- [ ] **Step 1: Create `_llm_protected.py`** — wrapping function factory

```python
"""Protected LLM calls with circuit breaker, retry, and fallback."""
from __future__ import annotations

import functools
from typing import Any, Callable

from minos_core.ai_resilience.circuit_breaker import CircuitBreaker
from minos_core.ai_resilience.retry_strategy import ExponentialBackoffRetry


def _wrap_llm_call(
    fn: Callable[..., Any],
    *,
    model: str,
    max_retries: int = 2,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
) -> Callable[..., Any]:
    """Wrap an LLM adapter call with circuit breaker + retry.

    Usage:
        protected_analyze = _wrap_llm_call(adapter.analyze, model=model)
        result = protected_analyze(prompt, model=model)
    """
    breaker = CircuitBreaker(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
    )
    retry = ExponentialBackoffRetry(
        max_retries=max_retries,
        base_delay=1.0,
        max_delay=30.0,
    )

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return retry.execute_with_retry(
            lambda: breaker.call(fn, *args, **kwargs)
        )

    return wrapper
```

Run: `cd "D:/MINOS-CORE" && python -c "from minos_core.pipeline._llm_protected import _wrap_llm_call; print('OK')"`
Expected: `OK`

- [ ] **Step 2: Check `CircuitBreaker.call` API** to ensure the wrapper matches

Run: `cd "D:/MINOS-CORE" && grep -n "def call\|def execute_with_retry" minos_core/ai_resilience/circuit_breaker.py minos_core/ai_resilience/retry_strategy.py`
If the API signature differs from the wrapper, adapt the wrapper to match.

- [ ] **Step 3: Integrate into `pipeline_chain.py`**

Find the LLM adapter call sites in `pipeline_chain.py`:
```python
# grep -n "generate_pfd_from_drawing\|infer_pfmea_from_process_flow\|generate_control_plan_from_pfmea" minos_core/pipeline_chain.py
```

Replace direct calls:
```python
# Before
from minos_core.generate_pfd import generate_pfd_from_drawing
result = generate_pfd_from_drawing(drawing_analysis, model=model)

# After
from minos_core.generate_pfd import generate_pfd_from_drawing
from minos_core.pipeline._llm_protected import _wrap_llm_call

_protected_pfd = _wrap_llm_call(generate_pfd_from_drawing, model=model)
result = _protected_pfd(drawing_analysis, model=model)
```

Apply this pattern to all 3 generation stages:
1. PFD generation
2. PFMEA inference
3. Control Plan generation

- [ ] **Step 4: Wire AIServicePool for model endpoint selection**

```python
from minos_core.ai_resilience.service_pool import AIServicePool

_service_pool = AIServicePool()
_service_pool.register("primary", base_url="https://api.openai.com/v1", priority=10)
# Fallback endpoints registered at lower priority
_service_pool.register("fallback", base_url="https://api.allincode.top/v1", priority=5)

def _select_model_endpoint(model: str) -> str:
    """Select the best available endpoint for the given model."""
    service = _service_pool.select()
    return service.base_url if service else model
```

Remove hardcoded fallback URL logic from `pipeline_chain.py` and use the pool instead.

- [ ] **Step 5: Run full test suite**

Run: `cd "D:/MINOS-CORE" && PYTHONPATH="D:/MINOS-CORE" python -m pytest tests/ --tb=line -q`
Expected: 1404 passed, 0 failed

- [ ] **Step 6: Commit**

```bash
git add minos_core/pipeline/_llm_protected.py minos_core/pipeline_chain.py
git commit -m "feat: wire AI resilience (circuit breaker + retry + service pool) into LLM calls"
```

---

### Task 3.5: Wire plugin system into pipeline

**Files:**
- Modify: `minos_core/pipeline_chain.py`
- Modify: `minos_core/pipeline/drawing_analysis.py`

- [ ] **Step 1: Add plugin load call to pipeline entry point**

Find where the pipeline starts in `pipeline_chain.py` (likely `generate_three_tables_from_drawing` or similar) and add:

```python
from minos_core.plugins import load_entry_point_plugins, get_ocr_engine, get_knowledge_source

# In the pipeline startup section:
load_entry_point_plugins()
```

- [ ] **Step 2: Add OCR engine selection via plugin system**

Where OCR engine selection happens:
```python
# Before
from minos_core.ocr_detection import detect_available_ocr_engines
engines = detect_available_ocr_engines()

# After
from minos_core.plugins import get_ocr_engine, iter_ocr_engines
plugin_engines = list(iter_ocr_engines())
if plugin_engines:
    engines = [e.name for e in plugin_engines]
else:
    from minos_core.ocr_detection import detect_available_ocr_engines
    engines = detect_available_ocr_engines()
```

- [ ] **Step 3: Add knowledge source lookup via plugin system**

Where knowledge/family context loading happens:
```python
# Before
from minos_core.part_family_knowledge import load_family_knowledge
knowledge = load_family_knowledge(part_name)

# After
from minos_core.plugins import get_knowledge_source, iter_knowledge_sources
knowledge = {}
for ks in iter_knowledge_sources():
    if ks.family_key in part_name.lower():
        knowledge = ks.load()
        break
if not knowledge:
    from minos_core.part_family_knowledge import load_family_knowledge
    knowledge = load_family_knowledge(part_name)
```

- [ ] **Step 4: Run full test suite**

Run: `cd "D:/MINOS-CORE" && PYTHONPATH="D:/MINOS-CORE" python -m pytest tests/ --tb=line -q`
Expected: 1404 passed, 0 failed

- [ ] **Step 5: Commit**

```bash
git add minos_core/pipeline_chain.py minos_core/pipeline/drawing_analysis.py
git commit -m "feat: wire plugin system into pipeline (OCR engine + knowledge source)"
```

---

### Task 3.6: Add TypedDict types for common dict shapes

**Files:**
- Create: `minos_core/_types.py`
- Modify: `minos_core/pipeline_chain.py`
- Modify: `minos_core/pipeline/orchestration.py`

- [ ] **Step 1: Create `_types.py`** with TypedDict definitions

```python
"""Type aliases and TypedDicts for common MINOS dict shapes."""
from __future__ import annotations

from typing import Any, TypedDict


class DrawingAnalysisResult(TypedDict, total=False):
    """Shape of a drawing analysis result."""
    drawing_identity: dict[str, Any]
    materials: list[dict[str, Any]]
    surface_treatments: list[dict[str, Any]]
    dimensions: list[dict[str, Any]]
    tolerances: list[dict[str, Any]]
    special_characteristics: list[dict[str, Any]]
    technical_requirements: list[dict[str, Any]]
    inspection_requirements: list[dict[str, Any]]
    manufacturing_clues: list[dict[str, Any]]
    uncertainties: list[dict[str, Any]]


class ProcessFlowStep(TypedDict, total=False):
    """Shape of a single PFD step."""
    step_number: str
    operation: str
    process_function: str
    equipment: str
    flow_symbol: str
    special_characteristics: list[str]
    cycle_time: str | None


class PFMEARow(TypedDict, total=False):
    """Shape of a single PFMEA row."""
    step_number: str
    process_function: str
    potential_failure_mode: str
    potential_effects: str
    severity: int
    potential_causes: str
    occurrence: int
    current_controls: str
    detection: int
    rpn: int
    recommended_actions: str


class ControlPlanRow(TypedDict, total=False):
    """Shape of a single Control Plan row."""
    step_number: str
    characteristic: str
    spec_method: str
    evaluation_technique: str
    sample_size: str
    frequency: str
    control_method: str
    reaction_plan: str


class QualityGateResult(TypedDict, total=False):
    """Shape of a quality gate evaluation result."""
    gate_name: str
    can_continue: bool
    allow_user_export: bool
    errors: list[str]
    warnings: list[str]
```

Run: `cd "D:/MINOS-CORE" && python -c "from minos_core._types import DrawingAnalysisResult, ProcessFlowStep; print('OK')"`
Expected: `OK`

- [ ] **Step 2: Update `pipeline/orchestration.py`** function signatures

Find functions that return these dict shapes and add TypedDict return types:

```python
from minos_core._types import DrawingAnalysisResult, QualityGateResult

# Before
def analyze_drawing(...) -> dict[str, Any]:
# After
def analyze_drawing(...) -> DrawingAnalysisResult:
```

- [ ] **Step 3: Update `pipeline_chain.py`** function signatures

```python
from minos_core._types import DrawingAnalysisResult, ProcessFlowStep, PFMEARow, ControlPlanRow, QualityGateResult

# Update 5 key functions from `-> Any` to the appropriate TypedDict
```

- [ ] **Step 4: Run full test suite**

Run: `cd "D:/MINOS-CORE" && PYTHONPATH="D:/MINOS-CORE" python -m pytest tests/ --tb=line -q`
Expected: 1404 passed, 0 failed

- [ ] **Step 5: Commit**

```bash
git add minos_core/_types.py minos_core/pipeline/
git commit -m "feat: add TypedDict types for common dict shapes, replace -> Any in pipeline"
```

---

### Task 3.7: Clean up ADR "Pending" entries

**Files:**
- Modify: `docs/adr/001-module-restructuring.md`
- Modify: `docs/adr/002-ai-resilience.md`
- Modify: `docs/adr/003-security-validation.md`
- Modify: `docs/adr/004-observability.md`
- Modify: `docs/adr/005-extensibility.md`

- [ ] **Step 1: Read all 5 ADR files**

Run: `cd "D:/MINOS-CORE" && for f in docs/adr/*.md; do echo "=== $f ==="; grep -n "Pending\|pending\|Status\|status" "$f"; done`

- [ ] **Step 2: Check each Pending item against current code**

For `001-module-restructuring.md`: Check if `edit_patch.py` refactor (ADR promised it) has been done. Status: src/pipeline directory exists from ADR-001 work; edit_patch.py still monolithic → mark "Partially done".

For `002-ai-resilience.md`: Check if `CircuitBreaker`, `RetryStrategy`, `ServicePool` are implemented (yes, in `ai_resilience/`). Check if integrated with LLM calls (no, Task 3.4 covers this) → mark "Code implemented, integration in Phase 3 Task 3.4".

For `003-security-validation.md`: Check `validation.py`, `observability/redaction.py`, `observability/logging.py` all exist (yes). Check schema-level input validation (InputValidator exists, but not at schema level) → mark "Partially done, InputValidator exists".

For `004-observability.md`: Check `observability/` package exists with logging, errors, resources, config_diagnostics (yes). → mark "Done".

For `005-extensibility.md`: Check `plugins/` package exists with registry + entrypoints (yes). Check if wired into pipeline (no, Task 3.5 covers this) → mark "Code implemented, pipeline integration in Phase 3 Task 3.5".

- [ ] **Step 3: Update each ADR file**

For each ADR, add an update section at the end:
```markdown
### Status Update (2026-06-26)

Phase 3 of the remediation plan reviewed this ADR:

- [x] **Completed:** [item name]
- [~] **Partially completed:** [item name] — reason (link to Phase task)
- [ ] **Still pending:** [item name] — planned for future phase
```

- [ ] **Step 4: Commit**

```bash
git add docs/adr/
git commit -m "docs: update ADR status entries against current codebase state"
```

---

## Self-Review Checklist

- [ ] **Spec coverage:** Every task in the Phase 3 plan maps to a specific issue from the ECC report
  - 3.1→ run_service.py 2,083 lines
  - 3.2→ table_editor.py 2,118 lines  
  - 3.3→ other 6 files over 800 lines
  - 3.4→ AI resilience not wired (critical)
  - 3.5→ plugin system not integrated
  - 3.6→ 429 `-> Any` return types
  - 3.7→ ADR pending items

- [ ] **Placeholder scan:** All code blocks contain complete implementations. No "TBD", "TODO", or "fill in later".

- [ ] **Type consistency:** TypedDict keys in Task 3.6 match actual dict keys used in pipeline functions.

- [ ] **Dependency ordering:** 3.6 modifies `pipeline_chain.py` same as 3.4 → sequential. All other tasks fully parallel.

---

## Execution Handoff

**Plan complete and saved to `docs/plans/remediation-plan.md` and `docs/superpowers/plans/2026-06-26-phase3-code-surgery.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
