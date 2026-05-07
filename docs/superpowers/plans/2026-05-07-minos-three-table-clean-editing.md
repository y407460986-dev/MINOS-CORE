# MINOS Three Table Clean Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the three-table workbench into a large, clean editing surface with contextual actions and compact chain status.

**Architecture:** Keep the existing Tauri + React + TanStack Table stack. Move editing affordances closer to the table by making `WorkbenchTable` support editable cells, row selection, and a floating contextual toolbar, while `ThreeTableWorkbench` owns patch submission and stage polling.

**Tech Stack:** React 18, TypeScript, TanStack Table, Tailwind CSS, shadcn/radix UI, lucide-react, Python pytest static/behavior tests.

---

### Task 1: Pin UI Contract With Tests

**Files:**
- Modify: `tests/test_desktop_tauri_app_state.py`

- [ ] Add static assertions that the workbench exposes a large editing surface, editable cells, multi-row selection, floating contextual toolbar, compact chain status, and no fixed bottom bulk operation bar.
- [ ] Run `python -m pytest tests/test_desktop_tauri_app_state.py -q` and confirm the new assertions fail before implementation.

### Task 2: Implement Editable Table Surface

**Files:**
- Modify: `apps/desktop-tauri/src/components/WorkbenchTable.tsx`

- [ ] Add table-level state for editing cell, draft values, and selected rows.
- [ ] Render editable inputs for key columns directly inside table cells.
- [ ] Add row checkboxes and selected-row highlighting.
- [ ] Add a floating contextual toolbar that appears only when rows are selected or draft edits exist.
- [ ] Expose callbacks for save draft, soft delete selected rows, and mark review.

### Task 3: Wire Workbench Actions

**Files:**
- Modify: `apps/desktop-tauri/src/pages/ThreeTableWorkbench.tsx`

- [ ] Replace the fixed bottom row-editing bar with a clean workbench layout.
- [ ] Add a compact chain status strip derived from `chain_stages`.
- [ ] Wire table draft save to existing edit patch API.
- [ ] Wire multi-row soft delete to existing soft delete patch API.
- [ ] Keep PFD confirm and PFMEA background polling behavior.
- [ ] Keep `PreviewRail` / evidence summary as a secondary panel.

### Task 4: Verify

**Files:**
- No new files.

- [ ] Run `python -m pytest tests/test_desktop_tauri_app_state.py tests/test_desktop_shell.py tests/test_desktop_api_sidecar.py -q`.
- [ ] Run `npm run build` in `apps/desktop-tauri`.
- [ ] Inspect the final diff for unrelated churn.
