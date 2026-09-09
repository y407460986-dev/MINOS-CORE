# Phase 4 — 文档重建 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring all documentation up to date with the v3.8 codebase: update architecture docs, README, add API docs, clean up root directory, and improve docstring coverage.

**Architecture:** Phase 4 has 5 independent tasks. Tasks 4.1-4.3 are documentation writing (content expertise needed), 4.4 is file relocation, 4.5 is docstring completion. All can run in parallel, with 4.2 optionally depending on 4.1 for accurate architecture descriptions.

**Tech Stack:** Markdown, Python docstrings (reStructuredText or Google-style)

---

## File Structure

### Created
| File | Responsibility |
|------|---------------|
| `docs/api-overview.md` | Route table for `minos_desktop.api` |
| `docs/plans/task_plan.md` | Moved from `task_plan.md` |
| `docs/plans/progress.md` | Moved from `progress.md` |
| `docs/plans/findings.md` | Moved from `findings.md` |

### Modified
| File | Change |
|------|--------|
| `docs/architecture/modules.md` | Add new modules: special char recognition, component drawings, hybrid analysis, edit patch |
| `docs/architecture/data-flow.md` | Add special characteristic discovery/review/location flow branches |
| `docs/architecture/README.md` | Update v3.0 references to v3.8; update component list in 4-layer diagram |
| `README.md` | Update version refs, add Tauri build steps, add new CLI commands |
| `minos_core/*.py` (multiple) | Add/improve docstrings on public functions |

### Deleted
None (files are moved, not deleted).

---

### Task 4.1: Update architecture documentation to v3.8

**Files:**
- Modify: `docs/architecture/modules.md`
- Modify: `docs/architecture/data-flow.md`
- Modify: `docs/architecture/README.md`

- [ ] **Step 1: Read all 3 architecture docs**

```bash
cd "D:/MINOS-CORE" && cat docs/architecture/README.md
cd "D:/MINOS-CORE" && cat docs/architecture/modules.md
cd "D:/MINOS-CORE" && cat docs/architecture/data-flow.md
```

- [ ] **Step 2: Update `modules.md`**

Current state: References "v3.0" modules. Needs:
- Add `minose_core/special_characteristics/` — special characteristic discovery, visual location, SC/CC candidate detection
- Add `minose_core/pipeline/` — sub-package with orchestration, drawing_analysis, family_context, hybrid_fusion, review_export, utilities
- Add `minose_core/quality_gates/` — sub-package with config_loader, core_evaluators, evidence_coverage, export_gate, report_projections
- Add `minose_core/edit_patch/` or note `edit_patch.py` refactoring into sub-modules
- Add `minose_desktop/api/` routes and authentication
- Add `minose_desktop/security/` — API key store, auth middleware, secret_str

```markdown
### New in v3.3-v3.8

| Module | Location | Responsibility |
|--------|----------|---------------|
| Special Characteristics | `minos_core/special_characteristics/` | SC/CC discovery, visual locator, judge, evidence |
| Pipeline sub-package | `minos_core/pipeline/` | Orchestrated stage execution |
| Quality Gates | `minos_core/quality_gates/` | Per-stage quality evaluation |
| Edit Patch | `minos_core/edit_patch*.py` | Review patch apply/merge/export |
| Desktop Security | `minos_desktop/security/` | API key store, Bearer auth, CORS |
| Desktop API Routes | `minos_desktop/api/routes_*.py` | REST endpoints for projects, runs, settings |
```

Verify: `cd "D:/MINOS-CORE" && head -20 docs/architecture/modules.md`

- [ ] **Step 3: Update `data-flow.md`**

Current flow (simplified):
```
drawing → OCR+Vision analysis → PFD generation → PFMEA generation → CP generation → quality gates → export
```

New flow to document:
```
drawing (single or multi-page component drawings)
  → OCR analysis (RapidOCR / MinerU / pdf_text)
  → Vision analysis (multimodal LLM)
  → Hybrid fusion (OCR + Vision merge)
  → Special characteristic discovery (visual location + LLM judge)
  → PFD generation (LLM, with family context enrichment)
  → PFMEA generation (LLM, per confirmed PFD step)
  → CP generation (LLM, per confirmed PFMEA row)
  → Quality gates (per-stage: can_continue check)
  → Edit patch review (undo/redo, batch confirm)
  → Export (draft → final, xlsx)
```

Verify: `cd "D:/MINOS-CORE" && grep -c "special\|hybrid\|edit.*patch" docs/architecture/data-flow.md`

- [ ] **Step 4: Update `architecture/README.md`**

Change:
- "v3.0 采用 4 层结构" → "v3.8 采用 4 层结构"
- Update the component list under each layer to match current modules

Verify: `cd "D:/MINOS-CORE" && grep "v3\." docs/architecture/README.md`

- [ ] **Step 5: Verify no test regressions**

```bash
cd "D:/MINOS-CORE" && PYTHONPATH="D:/MINOS-CORE" python -m pytest tests/ --tb=line -q
```
Expected: 1404 passed, 0 failed

---

### Task 4.2: Update README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Read current README**

```bash
cd "D:/MINOS-CORE" && cat README.md
```

- [ ] **Step 2: Update version references**

Change: `v3.0 采用 4 层结构` → `v3.8 采用 4 层结构`

- [ ] **Step 3: Add missing CLI commands**

Read the current CLI commands:
```bash
cd "D:/MINOS-CORE" && python -m minos_core.cli --help
```

Add documentation for:
- `compare-ocr-engines` — compare OCR engine results
- `accept-three-tables` — validate three-table generation result
- `write-demo-drawing` — generate demo drawing PNG
- `doctor` — environment diagnostics
- `apply-review` — apply review patch to APQP chain

- [ ] **Step 4: Add Tauri frontend build instructions**

Add a section covering:
```bash
cd apps/desktop-tauri
npm install
npm run build
```

Include the `cargo check` / `cargo build` step for the Rust side.

- [ ] **Step 5: Update CLAUDE.md section**

The project CLAUDE.md file at `CLAUDE.md` should also be reviewed for any out-of-date references.

Verify: `cd "D:/MINOS-CORE" && head -50 README.md`

---

### Task 4.3: Create API overview document

**Files:**
- Create: `docs/api-overview.md`

- [ ] **Step 1: Discover all API routes**

```bash
cd "D:/MINOS-CORE" && grep -rn "@router\|@app\.\|def \w\+" minos_desktop/api/routes_*.py minos_desktop/api/app.py | grep "@" | head -60
```

- [ ] **Step 2: Create `docs/api-overview.md`**

```markdown
# MINOS-CORE API 概览

**Base URL:** `http://localhost:8100/api`（默认）
**认证:** Bearer Token（除 `/health`、`/auth`、`/sse` 外）

## 健康检查

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/health` | 服务健康检查 | ❌ 否 |

## 认证

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/auth/login` | 获取 Bearer token | ❌ 否 |
| GET  | `/auth/check` | 检查 token 有效性 | ✅ 是 |

## 项目管理

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET  | `/projects` | 项目列表 | ✅ |
| POST | `/projects` | 创建项目 | ✅ |
| GET  | `/projects/{id}` | 项目详情 | ✅ |
| PUT  | `/projects/{id}` | 更新项目 | ✅ |
| DELETE | `/projects/{id}` | 删除项目 | ✅ |

## 运行管理

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/projects/{id}/chain-runs` | 启动链式生成 | ✅ |
| GET  | `/projects/{id}/runs` | 运行记录列表 | ✅ |
| GET  | `/projects/{id}/runs/{run_id}` | 运行详情 | ✅ |
| ... | ... | ... | ... |
```

Fill in ALL routes from the discovered list. Group by router file.

- [ ] **Step 3: Verify**

```bash
cd "D:/MINOS-CORE" && wc -l docs/api-overview.md
```
Expected: >= 80 lines (comprehensive route table)

---

### Task 4.4: Clean up root directory

**Files:**
- Create: `docs/plans/task_plan.md` (move from root)
- Create: `docs/plans/progress.md` (move from root)
- Create: `docs/plans/findings.md` (move from root)

- [ ] **Step 1: Ensure target directory exists**

```bash
cd "D:/MINOS-CORE" && mkdir -p docs/plans
```

- [ ] **Step 2: Move files**

```bash
cd "D:/MINOS-CORE" && git mv task_plan.md docs/plans/task_plan.md && git mv progress.md docs/plans/progress.md && git mv findings.md docs/plans/findings.md
```

- [ ] **Step 3: Update any cross-references**

```bash
cd "D:/MINOS-CORE" && grep -rn "\.\./task_plan\|\.\./progress\|\.\./findings\|\.\/task_plan\|\.\/progress\|\.\/findings" --include="*.md" . | grep -v .git | head -10
```

If any other docs reference these files by their old paths, update the links.

- [ ] **Step 4: Verify**

```bash
cd "D:/MINOS-CORE" && ls -la docs/plans/ && ls task_plan.md progress.md findings.md 2>&1
```
Expected: files exist in `docs/plans/`, gone from root

---

### Task 4.5: Improve docstring coverage (21% → 50%+)

**Files:**
- Modify: `minos_core/cli.py`
- Modify: `minos_core/cli_doctor.py`
- Modify: `minos_core/pipeline_chain.py`
- Modify: `minos_core/edit_patch.py`
- Modify: `minos_core/part_family_knowledge.py`
- Modify: `minos_core/drawing_to_pfd.py`
- Modify: Other `minos_core/*.py` files with < 20% docstring coverage

- [ ] **Step 1: Identify modules with worst docstring coverage**

```bash
cd "D:/MINOS-CORE" && for f in minos_core/*.py; do
  total=$(grep -c "^\s*def \|^\s*class " "$f" 2>/dev/null || echo 0)
  docs=$(grep -c "^\s*\"\"\"" "$f" 2>/dev/null || echo 0)
  if [ "$total" -gt 5 ] && [ "$docs" -lt "$((total / 5))" ]; then
    pct=$((docs * 100 / total))
    echo "$f: $pct% ($docs/$total)"
  fi
done | sort -t: -k2 -n | head -10
```

- [ ] **Step 2: Add docstrings to priority files — `cli.py`**

Every public function gets at minimum a one-line docstring:
```python
def _accept_three_tables(result_path: str) -> int:
    """Run acceptance checks on a three-table generation result JSON.
    
    Args:
        result_path: Path to the three_table_generation_result.json file.
    
    Returns:
        0 if all checks pass, 2 if any check fails or file cannot be read.
    """
```

Add docstrings to ALL non-private functions in `cli.py` (functions without `_` prefix or with `_` but called from argparse).

- [ ] **Step 3: Add docstrings to `pipeline_chain.py` and sub-modules**

```python
def generate_pfd_from_drawing(drawing_analysis: dict, model: str = ...) -> dict:
    """Generate Process Flow Diagram from drawing analysis.
    
    Args:
        drawing_analysis: Output from drawing analysis stage.
        model: LLM model identifier.
    
    Returns:
        Dict with 'steps' key containing list of PFD step dicts.
    """
```

Focus on public functions: `generate_pfd_from_drawing`, `generate_pfmea_from_confirmed_pfd`, `generate_cp_from_confirmed_pfmea`.

- [ ] **Step 4: Add docstrings to `edit_patch.py` and sub-modules**

Focus on public functions: `build_edit_patch`, `apply_edit_patch`, `merge_review`, etc.

- [ ] **Step 5: Add docstrings to `part_family_knowledge.py` and sub-modules**

Focus on public functions like `load_family_knowledge`, `convert_seed_workbook_to_family_knowledge`, `enrich_with_family_templates`.

- [ ] **Step 6: Add docstrings to `drawing_to_pfd.py` and sub-modules**

Focus on `infer_process_flow_from_drawing`, `normalize_process_flow_steps`.

- [ ] **Step 7: Verify**

```bash
cd "D:/MINOS-CORE" && PYTHONPATH="D:/MINOS-CORE" python -m pytest tests/ --tb=line -q
```
Expected: 1404 passed, 0 failed

---

## Task Dependency Graph

```
4.1 ── (architecture docs) ──→ independent
4.2 ── (README update) ──────→ independent (can reference 4.1 output)
4.3 ── (API overview) ───────→ independent
4.4 ── (root dir cleanup) ───→ independent
4.5 ── (docstrings) ─────────→ independent (watch for merge conflicts with other doc changes)
```

**All 5 tasks can run in parallel.**

---

## Self-Review Checklist

- [ ] **Spec coverage:** 
  - 4.1 covers architecture docs → modules.md, data-flow.md, README.md
  - 4.2 covers README updates (version, CLI, Tauri build)
  - 4.3 covers API overview (new docs/api-overview.md)
  - 4.4 covers root dir cleanup (task_plan.md → docs/plans/)
  - 4.5 covers docstring improvements (cli.py, pipeline_chain.py, etc.)

- [ ] **Placeholder scan:** No "TBD" or "TODO" in the plan. Code blocks for docstring examples are complete.

- [ ] **Type consistency:** No function references span across tasks in conflicting ways.
