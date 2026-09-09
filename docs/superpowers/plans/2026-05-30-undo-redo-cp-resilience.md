# CP Stage Resilience + Undo/Redo Architecture — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two issues: (1) make CP generation resilient to individual row failures like PFMEA already is, and (2) make undo/redo work across HTTP requests by hoisting stacks to class level.

**Architecture:** Two independent subsystems. Fix #1 is a surgical ~15-line change in pipeline_chain.py to align CP failure handling with PFMEA's proven pattern. Fix #2 is a broader change: class-level dicts + 2 new API endpoints + 2 frontend buttons.

**Tech Stack:** Python 3.11 / FastAPI / TypeScript / React

---

## Part A: CP Stage Resilience (failed_row_ids)

### Task A1: Replace `raise ValueError` with graceful failure recording

**Files:**
- Modify: `minos_core/pipeline_chain.py:1032-1041`

**Root cause:** When a single PFMEA row's CP generation fails (e.g., LLM rate limit), the current code does `raise ValueError(...)` which aborts the entire CP generation, discarding all previously successful rows. The `failed_row_ids` variable is declared but never written.

**Fix:** Align with PFMEA stage pattern: record the failure, emit `step_failed` event, and continue processing remaining rows. Only raise if absolutely zero rows were generated.

- [ ] **Step 1: Replace raise with graceful failure**

In `minos_core/pipeline_chain.py`, lines 1032-1041:

```python
# Before:
                except Exception as exc:
                    logger.error("CHAIN [Stage 3] CP generation failed for %s after retries: %s", pfmea_id, exc)
                    if on_progress:
                        on_progress({
                            "type": "error",
                            "stage": "cp",
                            "message": f"CP generation failed for {pfmea_id}: {exc}",
                        })
                    raise ValueError(f"Cannot generate Control Plan for PFMEA {pfmea_id}: {exc}") from exc

# After:
                except Exception as exc:
                    logger.error("CHAIN [Stage 3] CP generation failed for %s after retries: %s", pfmea_id, exc)
                    failed_row_ids.append(pfmea_id)
                    batch_results[idx] = (pfmea_id, process_step_id, None)
```

- [ ] **Step 2: Handle None results in the processing loop**

After the batch processing loop, the code iterates `for idx, pfmea_row in batch:` and reads `batch_results[idx]`. We already have `.get(idx)` guard from a previous fix. Now we also need to handle the `(pfmea_id, process_step_id, None)` case — skip when `cp_result is None`.

In `minos_core/pipeline_chain.py`, around line 1046:

```python
# Before (line 1045-1046):
            entry = batch_results.get(idx)
            if entry is None:
                continue
            pfmea_id, process_step_id, cp_result = entry

# After:
            entry = batch_results.get(idx)
            if entry is None:
                continue
            pfmea_id, process_step_id, cp_result = entry
            if cp_result is None:
                # This row failed — already recorded in failed_row_ids,
                # but we still need to update the progress counter
                if on_progress:
                    on_progress({
                        "type": "step_failed",
                        "stage": "cp",
                        "step_index": completed_count,
                        "total_steps": len(valid_pfmea_rows),
                        "step_id": pfmea_id,
                        "rows_so_far": len(cp_rows),
                        "message": f"CP generation failed for {pfmea_id} after retries",
                    })
                completed_count += 1
                continue
```

- [ ] **Step 3: Run the existing CP pipeline tests**

Run: `python -m pytest tests/ -k "cp or control_plan or pipeline_chain" -v`
Expected: All pass, no regressions.

- [ ] **Step 4: Commit**

```bash
git -C "D:/MINOS-CORE" add minos_core/pipeline_chain.py
git -C "D:/MINOS-CORE" commit -m "fix(pipeline): make CP stage resilient to individual row failures (align with PFMEA pattern)"
```

---

## Part B: Undo/Redo Architecture Fix

**Overview:** Three changes needed — class-level stacks, API endpoints, frontend buttons.

### Task B1: Hoist undo/redo stacks to class-level dicts

**Files:**
- Modify: `minos_desktop/services/run_service.py:49-56`

**Root cause:** `_undo_stack` and `_redo_stack` are instance variables. Every HTTP request creates a new `DesktopRunService` with empty stacks.

**Fix:** Convert to class-level dicts keyed by `run_id`.

- [ ] **Step 1: Replace instance-level stacks with class-level dicts**

In `minos_desktop/services/run_service.py`, lines 49-56:

```python
# Before:
class DesktopRunService:
    def __init__(
        self,
        db_path: str | Path = DEFAULT_DESKTOP_DB_PATH,
    ) -> None:
        self._store = DesktopSQLiteStore(db_path)
        self._undo_stack: list[dict[str, Any]] = []
        self._redo_stack: list[dict[str, Any]] = []

# After:
class DesktopRunService:
    # Class-level undo/redo stacks keyed by run_id — survive across HTTP requests
    _undo_stacks: dict[int, list[dict[str, Any]]] = {}
    _redo_stacks: dict[int, list[dict[str, Any]]] = {}

    def __init__(
        self,
        db_path: str | Path = DEFAULT_DESKTOP_DB_PATH,
    ) -> None:
        self._store = DesktopSQLiteStore(db_path)

    def _undo_stack_for(self, run_id: int) -> list[dict[str, Any]]:
        """Get or create the undo stack for a specific run."""
        if run_id not in self._undo_stacks:
            self._undo_stacks[run_id] = []
        return self._undo_stacks[run_id]

    def _redo_stack_for(self, run_id: int) -> list[dict[str, Any]]:
        """Get or create the redo stack for a specific run."""
        if run_id not in self._redo_stacks:
            self._redo_stacks[run_id] = []
        return self._redo_stacks[run_id]
```

- [ ] **Step 2: Update all methods that reference `_undo_stack` / `_redo_stack`**

Replace `self._undo_stack` → `self._undo_stack_for(run_id)` and `self._redo_stack` → `self._redo_stack_for(run_id)` in these methods:
- `save_with_undo` (~line 1117)
- `undo_run` (~line 1140)
- `redo_run` (~line 1160)

Example for `save_with_undo`:

```python
# Before:
    self._undo_stack.append(snapshot)
    self._redo_stack.clear()
    while len(self._undo_stack) > MAX_UNDO_STACK_SIZE:
        self._undo_stack.pop(0)
    total_size = sum(...)

# After:
    stack = self._undo_stack_for(run_id)
    redo = self._redo_stack_for(run_id)
    stack.append(snapshot)
    redo.clear()
    while len(stack) > MAX_UNDO_STACK_SIZE:
        stack.pop(0)
    total_size = sum(...)
```

- [ ] **Step 3: Run existing undo tests**

Run: `python -m pytest tests/test_desktop_undo.py -v`
Expected: All pass (they work within single instance, should still pass).

- [ ] **Step 4: Commit**

```bash
git -C "D:/MINOS-CORE" add minos_desktop/services/run_service.py
git -C "D:/MINOS-CORE" commit -m "fix(desktop): hoist undo/redo stacks to class-level dicts for cross-request persistence"
```

---

### Task B2: Add undo/redo API endpoints

**Files:**
- Modify: `minos_desktop/api/routes_runs.py`
- Modify: `minos_desktop/api/jobs.py` (if needed)

- [ ] **Step 1: Add undo and redo job functions**

In `minos_desktop/api/jobs.py`, add:

```python
def undo_run(db_path: str | Path, run_id: int):
    return DesktopRunService(db_path).undo_run(run_id)

def redo_run(db_path: str | Path, run_id: int):
    return DesktopRunService(db_path).redo_run(run_id)
```

- [ ] **Step 2: Add undo/redo routes**

In `minos_desktop/api/routes_runs.py`, add:

```python
@router.post("/runs/{run_id}/undo")
def undo_run(run_id: int, request: Request) -> dict[str, Any]:
    try:
        record = jobs.undo_run(request.app.state.db_path, run_id)
        if record is None:
            raise ValueError("没有可以撤销的操作。")
        return run_to_dict(record)
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc


@router.post("/runs/{run_id}/redo")
def redo_run(run_id: int, request: Request) -> dict[str, Any]:
    try:
        record = jobs.redo_run(request.app.state.db_path, run_id)
        if record is None:
            raise ValueError("没有可以重做的操作。")
        return run_to_dict(record)
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise failure_from_exception(exc) from exc
```

- [ ] **Step 3: Commit**

```bash
git -C "D:/MINOS-CORE" add minos_desktop/api/routes_runs.py minos_desktop/api/jobs.py
git -C "D:/MINOS-CORE" commit -m "feat(desktop): add undo/redo API endpoints for cross-request undo support"
```

---

### Task B3: Add frontend undo/redo API functions and toolbar buttons

**Files:**
- Modify: `apps/desktop-tauri/src/api/client.ts`
- Modify: `apps/desktop-tauri/src/pages/ThreeTableWorkbench.tsx`

- [ ] **Step 1: Add undo/redo API functions**

In `apps/desktop-tauri/src/api/client.ts`, add:

```typescript
export function undoRun(runId: number): Promise<DesktopRun> {
  return apiJson<DesktopRun>(`/api/runs/${runId}/undo`, { method: "POST" });
}

export function redoRun(runId: number): Promise<DesktopRun> {
  return apiJson<DesktopRun>(`/api/runs/${runId}/redo`, { method: "POST" });
}
```

- [ ] **Step 2: Add undo/redo buttons to workbench toolbar**

In `apps/desktop-tauri/src/pages/ThreeTableWorkbench.tsx`:
- Import `undoRun` and `redoRun` from client
- Add `Undo2` and `Redo2` icons from lucide-react (or use text buttons)
- Add two buttons in the toolbar area that call `undoRun`/`redoRun` and refresh the run

```tsx
// In the toolbar actions area, add:
<Button variant="outline" size="sm" disabled={!hasRun || isSaving} onClick={handleUndo}>
  <Undo2 size={14} /> 撤销
</Button>
<Button variant="outline" size="sm" disabled={!hasRun || isSaving} onClick={handleRedo}>
  <Redo2 size={14} /> 重做
</Button>
```

With handlers:

```tsx
async function handleUndo() {
  if (!run) return;
  setIsSaving(true);
  try {
    const updated = await undoRun(run.id);
    onRunUpdated?.(updated);
    setSaveState("已撤销。");
  } catch (caught) {
    setSaveState(caught instanceof Error ? caught.message : String(caught));
  } finally {
    setIsSaving(false);
  }
}

async function handleRedo() {
  if (!run) return;
  setIsSaving(true);
  try {
    const updated = await redoRun(run.id);
    onRunUpdated?.(updated);
    setSaveState("已重做。");
  } catch (caught) {
    setSaveState(caught instanceof Error ? caught.message : String(caught));
  } finally {
    setIsSaving(false);
  }
}
```

- [ ] **Step 4: Commit**

```bash
git -C "D:/MINOS-CORE" add apps/desktop-tauri/src/api/client.ts apps/desktop-tauri/src/pages/ThreeTableWorkbench.tsx
git -C "D:/MINOS-CORE" commit -m "feat(frontend): add undo/redo buttons to workbench toolbar"
```

---

## Summary

| Part | Task | File | Change |
|---|---|---|---|
| A | A1 | `pipeline_chain.py:1032-1041` | `raise ValueError` → `failed_row_ids.append` + continue |
| B | B1 | `run_service.py:49-56` | Instance stacks → class-level dicts |
| B | B1 | `run_service.py:1117-1160` | `self._undo_stack` → `self._undo_stack_for(run_id)` |
| B | B2 | `routes_runs.py`, `jobs.py` | New `POST /runs/{id}/undo`, `POST /runs/{id}/redo` |
| B | B3 | `client.ts`, `ThreeTableWorkbench.tsx` | API functions + 2 toolbar buttons |

**Total: 5 files, ~80 lines changed, 4 commits.**
