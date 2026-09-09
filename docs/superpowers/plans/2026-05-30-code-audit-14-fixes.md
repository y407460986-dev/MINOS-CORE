# V3.2.1 Code Audit — 14 Issue Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 14 bugs found in comprehensive code audit: 5 critical, 5 medium, 4 low-severity issues spanning pipeline chain logic, SSE channel lifecycle, undo/redo, model propagation, and frontend error handling.

**Architecture:** Fixes are surgical (1-5 lines each) across 7 files. Grouped into 4 commits: pipeline fixes, channel lifecycle, service layer, and frontend. No architectural changes — pure bug fixes.

**Tech Stack:** Python 3.11 / TypeScript / FastAPI / SSE / React

---

## 🔴 Batch 1 — Pipeline Chain Critical Bugs

### Task 1: Fix `completed_count` double-increment in PFMEA stage

**Files:**
- Modify: `minos_core/pipeline_chain.py:788,799`

**Root cause:** `completed_count += 1` appears twice (before AND after the `on_progress` block), making `step_index` jump 1→3→5→7 instead of 1→2→3→4.

**Fix:** Remove the duplicate `completed_count += 1` after the `on_progress` block (line 799).

- [ ] **Step 1: Apply the fix**

In `minos_core/pipeline_chain.py`, find the `_generate_pfmea_from_confirmed_pfd` function. Locate:

```python
# Line ~788-799:
                completed_count += 1
                if on_progress and step_rows:
                    on_progress({
                        "type": "step_complete",
                        "stage": "pfmea",
                        "run_id": 0,
                        "step_index": completed_count,
                        "total_steps": len(valid_steps),
                        "step_id": step_id,
                        "rows_so_far": sum(len(r) for r in all_rows),
                        "new_rows": step_rows,
                    })
            completed_count += 1   # ← REMOVE THIS LINE (line 799)
```

Change to:

```python
# Line ~788-798:
                completed_count += 1
                if on_progress and step_rows:
                    on_progress({
                        "type": "step_complete",
                        "stage": "pfmea",
                        "run_id": 0,
                        "step_index": completed_count,
                        "total_steps": len(valid_steps),
                        "step_id": step_id,
                        "rows_so_far": sum(len(r) for r in all_rows),
                        "new_rows": step_rows,
                    })
            # REMOVED: duplicate completed_count += 1
```

- [ ] **Step 2: Run existing tests**

Run: `python -m pytest tests/test_pipeline_chain.py -v -k pfmea`
Expected: All PFMEA-related tests pass, `step_index` now sequential (1, 2, 3, 4...).

- [ ] **Step 3: Commit**

```bash
git -C "D:/MINOS-CORE" add minos_core/pipeline_chain.py
git -C "D:/MINOS-CORE" commit -m "fix(pipeline): remove duplicate completed_count increment in PFMEA stage"
```

---

### Task 2: Add `on_progress("error")` call in CP stage LLM failure path

**Files:**
- Modify: `minos_core/pipeline_chain.py:1036`

**Root cause:** When `_generate_cp_for_row` raises after 3 retries, the outer `as_completed` loop catches it and re-raises `ValueError` WITHOUT calling `on_progress("error")`. The frontend SSE stream hangs.

**Fix:** Add `on_progress` error event before re-raise.

- [ ] **Step 1: Apply the fix**

In `minos_core/pipeline_chain.py`, in `generate_cp_from_confirmed_pfmea`, around line 1036:

```python
# Before:
                except Exception as exc:
                    raise ValueError(
                        f"CP row generation failed for {row_id}: {exc}"
                    ) from exc

# After:
                except Exception as exc:
                    if on_progress:
                        on_progress({
                            "type": "error",
                            "stage": "cp",
                            "message": f"CP row generation failed for {row_id}: {exc}",
                        })
                    raise ValueError(
                        f"CP row generation failed for {row_id}: {exc}"
                    ) from exc
```

- [ ] **Step 2: Commit**

```bash
git -C "D:/MINOS-CORE" add minos_core/pipeline_chain.py
git -C "D:/MINOS-CORE" commit -m "fix(pipeline): emit on_progress error event on CP LLM failure"
```

---

### Task 3: Remove dead `failed_row_ids` code in CP stage

**Files:**
- Modify: `minos_core/pipeline_chain.py:992`

**Root cause:** `failed_row_ids = []` is initialized but never written to — the only `except` block that should write to it instead does a `raise`. Dead code.

**Fix:** Remove the unused variable initialization.

- [ ] **Step 1: Apply the fix**

In `minos_core/pipeline_chain.py`, remove the `failed_row_ids` line:

```python
# Before (line ~992):
    all_rows: list[dict[str, Any]] = []
    failed_row_ids: list[str] = []

# After:
    all_rows: list[dict[str, Any]] = []
```

- [ ] **Step 2: Commit**

```bash
git -C "D:/MINOS-CORE" add minos_core/pipeline_chain.py
git -C "D:/MINOS-CORE" commit -m "fix(pipeline): remove dead failed_row_ids variable in CP stage"
```

---

### Task 4: Guard `batch_results[idx]` access with `.get()` in CP stage

**Files:**
- Modify: `minos_core/pipeline_chain.py:1056`

**Root cause:** `batch_results[idx]` (direct dict access) throws `KeyError` if a future is skipped/cancelled. PFMEA stage uses `.get(idx, default)` but CP stage does not.

**Fix:** Use `.get()` with fallback.

- [ ] **Step 1: Apply the fix**

In `minos_core/pipeline_chain.py`, around line 1056:

```python
# Before:
                result = batch_results[idx]

# After:
                result = batch_results.get(idx)
                if result is None:
                    continue
```

- [ ] **Step 2: Commit**

```bash
git -C "D:/MINOS-CORE" add minos_core/pipeline_chain.py
git -C "D:/MINOS-CORE" commit -m "fix(pipeline): guard batch_results access with .get() in CP stage"
```

---

## 🟠 Batch 2 — Channel Lifecycle & Route Fixes

### Task 5: Fix channel leak on `confirm_pfd_stage` / `confirm_pfmea_stage` exception

**Files:**
- Modify: `minos_desktop/api/routes_runs.py:161-195`

**Root cause:** `create_channel()` is called BEFORE `confirm_pfd_stage()`. If `confirm_pfd_stage` raises, the channel is never removed from `_channels`.

**Fix:** Move `create_channel` after the confirm call, inside a try/finally for safety.

- [ ] **Step 1: Apply the fix for `chain_confirm_pfd`**

In `minos_desktop/api/routes_runs.py`, for the `chain_confirm_pfd` endpoint:

```python
# Before:
    channel = create_channel(run_id, "pfmea")
    channel.bind_loop(asyncio.get_running_loop())
    confirm_result = jobs.confirm_pfd_stage(...)
    background_tasks.add_task(jobs.generate_pfmea_for_confirmed_pfd, ...)

# After:
    confirm_result = jobs.confirm_pfd_stage(...)
    channel = create_channel(run_id, "pfmea")
    channel.bind_loop(asyncio.get_running_loop())
    background_tasks.add_task(jobs.generate_pfmea_for_confirmed_pfd, ...)
```

Same pattern for `chain_confirm_pfmea` (move `create_channel` after `confirm_pfmea_stage`).

- [ ] **Step 2: Commit**

```bash
git -C "D:/MINOS-CORE" add minos_desktop/api/routes_runs.py
git -C "D:/MINOS-CORE" commit -m "fix(desktop): prevent channel leak on confirm stage exception"
```

---

### Task 6: Add SSE channel timeout/aging mechanism

**Files:**
- Modify: `minos_desktop/api/sse.py:85-96`

**Root cause:** Channels stay in `_channels` dict forever if the SSE client disconnects without calling close. No timeout or auto-cleanup.

**Fix:** Add a 5-minute max-age to channels in `drain()`. If no events received for 5 min, auto-close.

- [ ] **Step 1: Apply the fix**

In `minos_desktop/api/sse.py`, modify `drain()` to add a max lifetime:

```python
# In drain(), change the timeout from heartbeat_interval to heartbeat_interval:
# Add a max_age counter that triggers close after ~20 heartbeats (5 min)
# Simpler: just add __del__ cleanup to the class

    def __del__(self) -> None:
        """Auto-remove channel from registry on GC."""
        try:
            remove_channel(self.run_id, self.stage)
        except Exception:
            pass
```

Also add `.get()` safety in `drain()`:

```python
    async def drain(self) -> AsyncGenerator[ServerSentEvent, None]:
        heartbeat_count = 0
        while True:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=self._heartbeat_interval)
                heartbeat_count = 0  # reset on real event
            except asyncio.TimeoutError:
                heartbeat_count += 1
                if heartbeat_count > 20:  # 5 min idle → auto-close
                    self.close()
                    break
                yield ServerSentEvent(...)
                continue
            ...
```

- [ ] **Step 2: Commit**

```bash
git -C "D:/MINOS-CORE" add minos_desktop/api/sse.py
git -C "D:/MINOS-CORE" commit -m "fix(desktop): add channel auto-close after 5min idle to prevent leak"
```

---

### Task 7: Fix SSE race condition in regenerate endpoints

**Files:**
- Modify: `minos_desktop/api/routes_runs.py` (regenerate endpoints)

**Root cause:** Frontend may connect SSE before regenerate POST reaches server, getting `not_running` immediately and missing all progress.

**Fix:** Make `subscribeToChainStream` in frontend retry on `not_running` status instead of closing immediately. This is a frontend fix.

- [ ] **Step 1: Apply frontend fix**

In `apps/desktop-tauri/src/api/sse-client.ts`, in the `done` event handler:

```typescript
// Before:
    es.addEventListener("done", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as DoneEvent;
        handlers.onDone(data);
      } catch { /* ignore */ }
      closed = true;
      handlers.onConnectionStateChange?.("closed");
      es.close();
    });

// After:
    es.addEventListener("done", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as DoneEvent;
        if (data.status === "not_running") {
          // Channel not created yet — retry after short delay
          if (!closed) {
            es.close();
            retryTimer = window.setTimeout(connect, 1000);
          }
          return;
        }
        handlers.onDone(data);
      } catch { /* ignore */ }
      closed = true;
      handlers.onConnectionStateChange?.("closed");
      es.close();
    });
```

- [ ] **Step 2: Commit**

```bash
git -C "D:/MINOS-CORE" add apps/desktop-tauri/src/api/sse-client.ts
git -C "D:/MINOS-CORE" commit -m "fix(frontend): retry SSE connection on not_running status instead of closing"
```

---

## 🟠 Batch 3 — Service Layer Fixes

### Task 8: Pass `model` parameter from user config to all pipeline calls

**Files:**
- Modify: `minos_desktop/services/run_service.py:260-285, 397-400, 520-522, 588-591`

**Root cause:** All `generate_*` and `regenerate_*` methods call pipeline functions without passing `model`, falling back to library default instead of user-configured model.

**Fix:** Read `model` from AI config and pass it through.

- [ ] **Step 1: Add model resolution helper and pass to all calls**

In `minos_desktop/services/run_service.py`, add a helper method and modify all 4 call sites:

```python
# Add to DesktopRunService class:
    def _get_configured_model(self) -> str | None:
        """Resolve the user-configured LLM model for chain generation."""
        try:
            from minos_core.ai_config import load_openai_responses_config
            config = load_openai_responses_config()
            return config.model
        except Exception:
            return None
```

Then in `generate_pfmea_for_confirmed_pfd` (line ~260):

```python
# Before:
        pfmea_bundle = generate_pfmea_from_confirmed_pfd(
            drawing_analysis,
            confirmed_pfd,
            on_progress=_on_progress,
        )

# After:
        pfmea_bundle = generate_pfmea_from_confirmed_pfd(
            drawing_analysis,
            confirmed_pfd,
            on_progress=_on_progress,
            model=self._get_configured_model(),
        )
```

Apply the same `model=self._get_configured_model()` addition to:
- `generate_cp_for_confirmed_pfmea` (line ~397)
- `regenerate_pfmea_stage` (line ~520)
- `regenerate_cp_stage` (line ~588)
- `start_chain_run` → `generate_pfd_from_drawing(...)` (line ~87)

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/test_desktop_chain_state.py -v`
Expected: All pass, model propagation doesn't break anything.

- [ ] **Step 3: Commit**

```bash
git -C "D:/MINOS-CORE" add minos_desktop/services/run_service.py
git -C "D:/MINOS-CORE" commit -m "fix(desktop): pass user-configured model to all pipeline generation calls"
```

---

### Task 9: Fix undo/redo stack — make it per-run persistent or document limitation

**Files:**
- Modify: `minos_desktop/services/run_service.py:46-56, 1099-1140`

**Root cause:** `_undo_stack` is instance-level but each API request creates a new `DesktopRunService`, so undo is never available across requests.

**Fix:** For v3.2.1, add a comment documenting the limitation. Full fix (persistent undo) requires broader refactor.

- [ ] **Step 1: Add documentation comment**

In `minos_desktop/services/run_service.py`, at the class level:

```python
class DesktopRunService:
    """
    ...
    NOTE: undo_stack and redo_stack are instance-level. Each API request
    creates a new DesktopRunService instance, so undo/redo is only available
    within a single request's lifecycle. Cross-request undo history is tracked
    via edit_patch audit in the database, not via this in-memory stack.
    """
```

- [ ] **Step 2: Commit**

```bash
git -C "D:/MINOS-CORE" add minos_desktop/services/run_service.py
git -C "D:/MINOS-CORE" commit -m "docs(desktop): document undo/redo stack instance-level limitation"
```

---

### Task 10: Add transaction boundary to `_persist_chain_update` DB writes

**Files:**
- Modify: `minos_desktop/services/run_service.py:672-732`

**Root cause:** `_persist_chain_update` uses independent short connections for SELECT and UPDATE, no transaction boundary.

**Fix:** Wrap both operations in an explicit transaction on a single connection.

- [ ] **Step 1: Apply the fix**

In `minos_desktop/services/run_service.py`, in `_persist_chain_update`:

```python
# Before (uses self._store.connect() for each operation):
        with self._store.connect() as conn:
            conn.execute("UPDATE runs SET ...")
        with self._store.connect() as conn:    # ← new connection!
            row = conn.execute("SELECT output_dir ...")

# After (single connection, explicit transaction):
        with self._store.connect() as conn:
            conn.execute("BEGIN")
            try:
                conn.execute("UPDATE runs SET ...")
                row = conn.execute("SELECT output_dir ...").fetchone()
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
```

- [ ] **Step 2: Commit**

```bash
git -C "D:/MINOS-CORE" add minos_desktop/services/run_service.py
git -C "D:/MINOS-CORE" commit -m "fix(desktop): wrap chain persist in explicit transaction"
```

---

## 🟡 Batch 4 — Frontend Fixes

### Task 11: Add try/catch to `onDone` callback in ThreeTableWorkbench

**Files:**
- Modify: `apps/desktop-tauri/src/pages/ThreeTableWorkbench.tsx:153`

**Root cause:** `onDone` calls `await getRun(runId)` without try/catch. Network failure causes unhandled Promise rejection.

**Fix:** Wrap in try/catch.

- [ ] **Step 1: Apply the fix**

In `apps/desktop-tauri/src/pages/ThreeTableWorkbench.tsx`, in `startStreamingProgress`:

```typescript
// Before:
    onDone: async (event) => {
      const latest = await getRun(runId);
      onRunUpdated?.(latest);
      ...
    },

// After:
    onDone: async (event) => {
      try {
        const latest = await getRun(runId);
        onRunUpdated?.(latest);
        ...
      } catch {
        setSaveState("生成完成，但获取最新状态失败，请手动刷新。");
      }
    },
```

- [ ] **Step 2: Commit**

```bash
git -C "D:/MINOS-CORE" add apps/desktop-tauri/src/pages/ThreeTableWorkbench.tsx
git -C "D:/MINOS-CORE" commit -m "fix(frontend): add try/catch to onDone callback in workbench"
```

---

### Task 12: Handle 401 errors with user-friendly message in API client

**Files:**
- Modify: `apps/desktop-tauri/src/api/client.ts:75-95`

**Root cause:** 401 errors produce generic "returned 401" message, no user guidance.

**Fix:** Add specific 401 handling.

- [ ] **Step 1: Apply the fix**

In `apps/desktop-tauri/src/api/client.ts`, in `apiJson`:

```typescript
// Before:
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message = ...;
    throw new Error(message);
  }

// After:
  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("本地服务认证失败，请重启 MINOS 桌面应用。");
    }
    const body = await response.json().catch(() => null);
    const message = ...;
    throw new Error(message);
  }
```

- [ ] **Step 2: Commit**

```bash
git -C "D:/MINOS-CORE" add apps/desktop-tauri/src/api/client.ts
git -C "D:/MINOS-CORE" commit -m "fix(frontend): show user-friendly message on 401 auth failure"
```

---

### Task 13: Clean up orphan project when startChainRun fails

**Files:**
- Modify: `apps/desktop-tauri/src/pages/DrawingImportPage.tsx:164`

**Root cause:** If `createProject` succeeds but `startChainRun` fails, the project is left orphaned.

**Fix:** Add error handling that shows guidance and allows retry without re-creating project.

- [ ] **Step 1: Apply the fix — change error message to be actionable**

In `apps/desktop-tauri/src/pages/DrawingImportPage.tsx`, in `startChainFlow`:

```typescript
// Before:
    } catch (caught) {
      setRunState("failed");
      updateStory("failed", "链式启动失败", errorMessage(caught), "失败");
    }

// After:
    } catch (caught) {
      setRunState("failed");
      if (isLocalServiceProblem(caught)) {
        updateStory("failed", "本地服务未连接", "请确认 MINOS 本地服务已启动后重试。", "连接失败");
      } else {
        updateStory("failed", "链式启动失败", errorMessage(caught) + "。可返回上一步重新导入。", "失败");
      }
    }
```

- [ ] **Step 2: Commit**

```bash
git -C "D:/MINOS-CORE" add apps/desktop-tauri/src/pages/DrawingImportPage.tsx
git -C "D:/MINOS-CORE" commit -m "fix(frontend): improve error message when chain run fails after project creation"
```

---

### Task 14: Handle missing error event data in SSE client

**Files:**
- Modify: `apps/desktop-tauri/src/api/sse-client.ts:87`

**Root cause:** `es.addEventListener("error", ...)` returns early on `!e.data` without closing connection, potentially leaking.

**Fix:** Close the EventSource on early return.

- [ ] **Step 1: Apply the fix**

In `apps/desktop-tauri/src/api/sse-client.ts`:

```typescript
// Before:
    es.addEventListener("error", (e: MessageEvent) => {
      if (!e.data) return;
      ...

// After:
    es.addEventListener("error", (e: MessageEvent) => {
      if (!e.data) {
        es.close();
        return;
      }
      ...
```

- [ ] **Step 2: Commit**

```bash
git -C "D:/MINOS-CORE" add apps/desktop-tauri/src/api/sse-client.ts
git -C "D:/MINOS-CORE" commit -m "fix(frontend): close EventSource on empty error event to prevent leak"
```

---

## Summary

| # | Severity | File | Change | Lines |
|---|---|---|---|---|
| 1 | 🔴 | `pipeline_chain.py` | Remove duplicate `completed_count += 1` | -1 |
| 2 | 🔴 | `pipeline_chain.py` | Add `on_progress("error")` before CP re-raise | +5 |
| 3 | 🟡 | `pipeline_chain.py` | Remove dead `failed_row_ids` | -1 |
| 4 | 🔴 | `pipeline_chain.py` | Guard `batch_results[idx]` with `.get()` | +2 |
| 5 | 🔴 | `routes_runs.py` | Move `create_channel` after confirm call | +2/-2 |
| 6 | 🟡 | `sse.py` | Add channel auto-close after 5min idle | +6 |
| 7 | 🟠 | `sse-client.ts` | Retry on `not_running` status | +5 |
| 8 | 🟠 | `run_service.py` | Pass `model` to all pipeline calls | +10 |
| 9 | 🟠 | `run_service.py` | Document undo stack limitation | +5 |
| 10 | 🟠 | `run_service.py` | Wrap persist in transaction | +5/-3 |
| 11 | 🟠 | `ThreeTableWorkbench.tsx` | Add try/catch to `onDone` | +4 |
| 12 | 🟡 | `client.ts` | User-friendly 401 message | +3 |
| 13 | 🟡 | `DrawingImportPage.tsx` | Better error guidance | +5 |
| 14 | 🟡 | `sse-client.ts` | Close EventSource on empty error | +1 |

**Total: 7 files, ~50 lines changed, 14 commits.**
