# Lean Special Characteristic Locator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make MINOS special-characteristic vision recognition use the same key and URL successfully while keeping the locator fast enough to avoid the current 300 second timeout edge.

**Architecture:** Keep full drawing analysis unchanged, but turn `visual_task="special_characteristic_locator"` into a true focused locator. The focused locator sends a compact prompt, compact context, and a smaller region set; it returns only CC/SC declaration and candidate-location fields that the existing normalizer can merge into OCR or full-vision results.

**Tech Stack:** Python 3.11, `minos_core.adapters.multimodal`, `minos_core.pipeline.drawing_analysis`, existing `pytest`/`unittest` tests, OpenAI-compatible Responses API.

---

## Current Evidence

- The same Codex auth key, same `https://allincode.top`, same `responses`, same `gpt-5.5`, and same `xhigh` reasoning can handle simple image requests.
- The real drawing title-block crop returns `critical_count=2` and `significant_count=1` in about 8 seconds.
- The real drawing full page returns `critical_count=2` and `significant_count=1` in about 14 seconds.
- The exact current MINOS focused locator request succeeds but takes about 280 seconds, only about 20 seconds below the configured 300 second timeout.
- The current focused locator prompt says it only does CC/SC, but still requires broad keys such as `materials`, `dimensions`, `tolerances`, and `manufacturing_clues`.

## Success Criteria

- Focused locator prompt no longer asks for full `drawing_analysis_bundle` fields.
- Focused locator context does not dump the full OCR summary into the model prompt.
- Focused locator default request sends only broad evidence crops first: title-block special counts, key-product-characteristic table, and technical requirements.
- Focused locator uses a local default reasoning effort of `medium`, while allowing an explicit override.
- Existing hybrid fallback behavior still merges focused locator candidates into OCR fallback output.
- Existing real drawing can identify `declared_totals = {"CC": 2, "SC": 1}` and at least three visual candidates without waiting near 300 seconds.

## File Structure

- Modify: `minos_core/adapters/multimodal.py`
  - Owns Responses API multimodal payloads.
  - Add focused-locator context compaction.
  - Slim the special-characteristic locator prompt.
  - Limit focused locator crop selection by detail mode.

- Modify: `minos_core/pipeline/drawing_analysis.py`
  - Owns hybrid drawing-analysis orchestration.
  - Add focused locator reasoning-effort override without changing full-vision reasoning.
  - Optionally retry focused locator with detailed line crops only when the broad pass reports missing declared candidates.

- Modify: `tests/test_openai_multimodal_adapter.py`
  - Add prompt/payload regression tests so the focused locator stays lightweight.

- Modify: `tests/three_table_workflow/test_drawing_analysis.py`
  - Add pipeline behavior tests for focused-locator reasoning override and optional detailed retry.

- Optional after core fix: `minos_desktop` settings/API files for a UI health check.
  - This is intentionally not part of the first implementation because the production bug is in the locator request shape, not in settings display.

---

### Task 1: Lock The Focused Locator Contract With A Failing Test

**Files:**
- Modify: `tests/test_openai_multimodal_adapter.py`
- Test: `tests/test_openai_multimodal_adapter.py`

- [ ] **Step 1: Add a test proving the focused locator prompt is currently too broad**

Add this test method inside `OpenAIResponsesMultimodalDrawingAnalyzerTests`:

```python
    def test_focused_locator_prompt_uses_slim_special_characteristic_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "drawing.png"
            Image.new("RGB", (2000, 1400), color="white").save(image_path)
            pages = render_drawing_pages(load_drawing_source(image_path))
            analyzer = OpenAIResponsesMultimodalDrawingAnalyzer(
                api_key="test-key",
                model="gpt-test",
            )

            payload = analyzer._request_payload(
                pages,
                {
                    "visual_task": "special_characteristic_locator",
                    "ocr_analysis_summary": {
                        "declared_totals": {"CC": 2, "SC": 1},
                        "technical_requirements": [
                            {
                                "text": "4. (2) 转动力矩(0.5~2.5)Nm",
                                "evidence_refs": ["REQ4-TORQUE"],
                            },
                            {"text": "5. GB 15086", "evidence_refs": ["REQ5"]},
                            {"text": "6. Q/BJORV M 0102", "evidence_refs": ["REQ6"]},
                        ],
                        "materials": [{"name": "SHOULD_NOT_BE_SENT_TO_LOCATOR"}],
                        "manufacturing_clues": [
                            {"operation": "SHOULD_NOT_BE_SENT_TO_LOCATOR"}
                        ],
                    },
                    "irrelevant_large_context": "x" * 8000,
                },
            )

            prompt = payload["input"][0]["content"][0]["text"]

            self.assertIn("declared_totals", prompt)
            self.assertIn("located_occurrences", prompt)
            self.assertIn("special_characteristic_candidates", prompt)
            self.assertIn("focused_review_requests", prompt)
            self.assertNotIn("materials, surface_treatments", prompt)
            self.assertNotIn("manufacturing_clues, uncertainties", prompt)
            self.assertNotIn("SHOULD_NOT_BE_SENT_TO_LOCATOR", prompt)
            self.assertNotIn("irrelevant_large_context", prompt)
            self.assertLess(len(prompt), 3500)
```

- [ ] **Step 2: Run the targeted test and verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_openai_multimodal_adapter.py::OpenAIResponsesMultimodalDrawingAnalyzerTests::test_focused_locator_prompt_uses_slim_special_characteristic_contract -q
```

Expected result before implementation:

```text
FAILED ... AssertionError
```

The failure should show that the current prompt still contains broad drawing-analysis fields or oversized context.

---

### Task 2: Slim The Locator Prompt And Context

**Files:**
- Modify: `minos_core/adapters/multimodal.py`
- Test: `tests/test_openai_multimodal_adapter.py`

- [ ] **Step 1: Add focused-locator output and context helpers**

In `minos_core/adapters/multimodal.py`, near `_special_characteristic_locator_prompt`, add:

```python
SPECIAL_CHARACTERISTIC_LOCATOR_OUTPUT_KEYS = (
    "declared_special_characteristics",
    "declared_totals",
    "located_occurrences",
    "special_characteristic_candidates",
    "special_characteristic_locations",
    "missing_counts",
    "focused_review_requests",
)


def _special_characteristic_locator_context(context: dict[str, Any]) -> dict[str, Any]:
    summary = context.get("ocr_analysis_summary")
    summary_dict = summary if isinstance(summary, dict) else {}
    discovery = context.get("special_characteristic_discovery_request")
    discovery_dict = discovery if isinstance(discovery, dict) else {}
    visual_regions = context.get("visual_evidence_regions")
    requirements = [
        _special_locator_requirement_hint(item)
        for item in summary_dict.get("technical_requirements", [])
        if isinstance(item, dict)
    ]
    requirements = [item for item in requirements if item][:8]
    return {
        "available_drawing_page_evidence_ids": context.get(
            "available_drawing_page_evidence_ids", []
        ),
        "declared_totals": _best_special_locator_totals(
            discovery_dict.get("declared_totals"),
            summary_dict.get("declared_totals"),
        ),
        "declared_special_characteristics": [
            dict(item)
            for item in discovery_dict.get("declared_special_characteristics", [])
            if isinstance(item, dict)
        ][:8],
        "technical_requirement_hints": requirements,
        "visual_evidence_regions": visual_regions
        if isinstance(visual_regions, list)
        else [],
        "special_characteristic_locator_scope": context.get(
            "special_characteristic_locator_scope",
            "title_block,key_product_characteristic_table,technical_requirements",
        ),
    }


def _best_special_locator_totals(*values: Any) -> dict[str, int]:
    totals = {"CC": 0, "SC": 0}
    for value in values:
        if not isinstance(value, dict):
            continue
        for classification in ("CC", "SC"):
            totals[classification] = max(
                totals[classification],
                _non_negative_count(value.get(classification)),
            )
    return totals


def _special_locator_requirement_hint(item: dict[str, Any]) -> dict[str, Any]:
    text = str(item.get("text") or item.get("source_text") or "").strip()
    if not text:
        return {}
    return {
        "text": text[:240],
        "evidence_refs": [
            str(ref)
            for ref in item.get("evidence_refs", [])
            if str(ref).strip()
        ][:4]
        if isinstance(item.get("evidence_refs"), list)
        else [],
    }
```

- [ ] **Step 2: Replace `_special_characteristic_locator_prompt` with a slim contract**

Replace the body of `_special_characteristic_locator_prompt` with:

```python
def _special_characteristic_locator_prompt(context: dict[str, Any]) -> str:
    locator_context = _special_characteristic_locator_context(context)
    context_text = json.dumps(locator_context, ensure_ascii=False, sort_keys=True)
    count_clause = _special_characteristic_count_clause(context)
    keys = ", ".join(SPECIAL_CHARACTERISTIC_LOCATOR_OUTPUT_KEYS)
    return (
        "你现在只做一个任务：识别图纸中的 CC/SC 特殊特性声明和候选位置。"
        "不要生成 PFD、PFMEA、CP，不要抽取材料、尺寸、公差、工序或完整图纸分析。"
        f"{count_clause}"
        "只阅读输入中的标题栏/特殊特性数量区域、产品特殊特性表区域、技术要求区域，"
        "以及必要的技术要求行裁剪。"
        "带圈数字、普通序号、条款编号本身不是 CC/SC；只有与图例符号或明确 CC/SC 标识一致，"
        "并且能绑定到具体要求文本时，才输出候选。"
        "特别注意含转动力矩、操作力矩、torque、0.5~2.5Nm 的功能要求行；"
        "也要注意 GB15086/GB 15086、Q/BJORV M 0102 等客户/法规要求是否带 CC 标识。"
        "只返回合法 JSON，不要 Markdown。"
        f"只允许返回这些顶层键：{keys}。"
        "located_occurrences 和 special_characteristic_candidates 中每项必须包含："
        "candidate_id, candidate_type, source, symbol_text_or_shape, linked_feature, "
        "symbol_bbox, linked_feature_bbox, evidence_refs, confidence, reasoning。"
        "candidate_type 只能是 CC、SC 或 unknown；source 必须是 gpt55_visual_locator。"
        "不要把候选直接写入 special_characteristics；最终确认交给 judge 或人工。"
        "如果标题栏、图例或产品特殊特性表声明 CC/SC 数量，必须输出 declared_totals。"
        "如果没有找到足够候选，必须输出 missing_counts 和 focused_review_requests。"
        "上下文："
        f"{context_text}"
    )
```

- [ ] **Step 3: Run the focused prompt test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_openai_multimodal_adapter.py::OpenAIResponsesMultimodalDrawingAnalyzerTests::test_focused_locator_prompt_uses_slim_special_characteristic_contract -q
```

Expected result after implementation:

```text
1 passed
```

---

### Task 3: Reduce The Default Focused Locator Image Set

**Files:**
- Modify: `tests/test_openai_multimodal_adapter.py`
- Modify: `minos_core/adapters/multimodal.py`
- Test: `tests/test_openai_multimodal_adapter.py`

- [ ] **Step 1: Add a failing test for broad detail mode**

Add this test method inside `OpenAIResponsesMultimodalDrawingAnalyzerTests`:

```python
    def test_focused_locator_default_payload_uses_broad_regions_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "drawing.png"
            Image.new("RGB", (2000, 1400), color="white").save(image_path)
            pages = render_drawing_pages(load_drawing_source(image_path))
            analyzer = OpenAIResponsesMultimodalDrawingAnalyzer(
                api_key="test-key",
                model="gpt-test",
            )

            payload = analyzer._request_payload(
                pages,
                {
                    "visual_task": "special_characteristic_locator",
                    "ocr_analysis_summary": {
                        "declared_totals": {"CC": 2, "SC": 1},
                        "technical_requirements": [
                            {"text": "4. (2) 转动力矩(0.5~2.5)Nm"},
                            {"text": "5. GB 15086"},
                            {"text": "6. Q/BJORV M 0102"},
                        ],
                    },
                },
            )

            content = payload["input"][0]["content"]
            images = [item for item in content if item["type"] == "input_image"]
            text_blocks = "\n".join(
                item["text"] for item in content if item["type"] == "input_text"
            )

            self.assertEqual(len(images), 3)
            self.assertIn("drawing_page_001_title_block_special_counts", text_blocks)
            self.assertIn("drawing_page_001_key_product_characteristic_table", text_blocks)
            self.assertIn("drawing_page_001_technical_requirements", text_blocks)
            self.assertNotIn("technical_requirement_line_001", text_blocks)
            self.assertNotIn("technical_requirement_line_004", text_blocks)
```

- [ ] **Step 2: Add a detailed-mode test so line crops remain available**

Add this test method inside `OpenAIResponsesMultimodalDrawingAnalyzerTests`:

```python
    def test_focused_locator_detailed_payload_keeps_line_crops(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "drawing.png"
            Image.new("RGB", (2000, 1400), color="white").save(image_path)
            pages = render_drawing_pages(load_drawing_source(image_path))
            analyzer = OpenAIResponsesMultimodalDrawingAnalyzer(
                api_key="test-key",
                model="gpt-test",
            )

            payload = analyzer._request_payload(
                pages,
                {
                    "visual_task": "special_characteristic_locator",
                    "special_characteristic_locator_detail": "detailed",
                    "ocr_analysis_summary": {
                        "declared_totals": {"CC": 2, "SC": 1},
                        "technical_requirements": [
                            {"text": "4. (2) 转动力矩(0.5~2.5)Nm"},
                            {"text": "5. GB 15086"},
                            {"text": "6. Q/BJORV M 0102"},
                        ],
                    },
                },
            )

            content = payload["input"][0]["content"]
            images = [item for item in content if item["type"] == "input_image"]
            text_blocks = "\n".join(
                item["text"] for item in content if item["type"] == "input_text"
            )

            self.assertGreaterEqual(len(images), 6)
            self.assertLessEqual(len(images), 8)
            self.assertIn("drawing_page_001_technical_requirement_line_003", text_blocks)
            self.assertIn("drawing_page_001_technical_requirement_line_004", text_blocks)
```

- [ ] **Step 3: Run the two new tests and verify broad mode fails before implementation**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_openai_multimodal_adapter.py::OpenAIResponsesMultimodalDrawingAnalyzerTests::test_focused_locator_default_payload_uses_broad_regions_only tests/test_openai_multimodal_adapter.py::OpenAIResponsesMultimodalDrawingAnalyzerTests::test_focused_locator_detailed_payload_keeps_line_crops -q
```

Expected result before implementation:

```text
FAILED ... test_focused_locator_default_payload_uses_broad_regions_only
PASSED ... test_focused_locator_detailed_payload_keeps_line_crops
```

- [ ] **Step 4: Update `_focused_special_characteristic_regions_for_request` to honor detail mode**

In `minos_core/adapters/multimodal.py`, replace `_focused_special_characteristic_regions_for_request` with:

```python
def _focused_special_characteristic_regions_for_request(
    pages: list[DrawingPageEvidence],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    summary = context.get("ocr_analysis_summary")
    requirements = []
    if isinstance(summary, dict):
        requirements = [
            item for item in summary.get("technical_requirements", []) if isinstance(item, dict)
        ]
    detail = str(
        context.get("special_characteristic_locator_detail") or "broad"
    ).strip().lower()
    allowed_labels = {
        "title_block_special_counts",
        "key_product_characteristic_table",
        "technical_requirements",
    }
    if detail == "detailed":
        allowed_labels.update(
            {
                "technical_requirement_line_001",
                "technical_requirement_line_002",
                "technical_requirement_line_003",
                "technical_requirement_line_004",
            }
        )
    regions: list[dict[str, Any]] = []
    for page in pages:
        page_regions = build_visual_evidence_regions(
            page_image_path=page.image_path,
            page_evidence_id=page.evidence_id,
            technical_requirements=requirements,
        )
        regions.extend(
            region
            for region in page_regions
            if str(region.get("label") or "") in allowed_labels
        )
    return regions
```

- [ ] **Step 5: Run adapter tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_openai_multimodal_adapter.py -q
```

Expected result:

```text
all tests passed
```

---

### Task 4: Override Focused Locator Reasoning Without Changing Full Vision

**Files:**
- Modify: `tests/three_table_workflow/test_drawing_analysis.py`
- Modify: `minos_core/pipeline/drawing_analysis.py`
- Test: `tests/three_table_workflow/test_drawing_analysis.py`

- [ ] **Step 1: Add a test for focused locator reasoning override**

Add this test method inside `DrawingAnalysisTests`:

```python
    def test_focused_special_characteristic_locator_uses_medium_reasoning_by_default(self):
        class _Analyzer:
            def __init__(self):
                self.timeout = 0
                self.max_retries = 99
                self.reasoning_effort = "xhigh"

            def analyze_drawing_pages(self, _pages, _context=None):
                context = _context or {}
                self.seen_context = dict(context)
                payload = {
                    "declared_totals": {"CC": 2, "SC": 1},
                    "located_occurrences": [],
                    "special_characteristic_candidates": [],
                    "special_characteristic_locations": [],
                    "missing_counts": {"CC": 2, "SC": 1},
                    "focused_review_requests": [],
                }
                return MultimodalDrawingResult(
                    content=json.dumps(payload, ensure_ascii=False),
                    model="gpt-5.5",
                    metadata={"source": "gpt55_visual_locator"},
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            source = load_drawing_source(SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png"))
            pages = render_drawing_pages(source)
            analyzer = _Analyzer()

            from minos_core.pipeline.drawing_analysis import (
                _run_focused_special_characteristic_visual_locator,
            )

            _run_focused_special_characteristic_visual_locator(
                pages,
                {},
                analyzer=analyzer,
                default_analyzer_factory=lambda: analyzer,
                analyze_drawing_pages=analyze_drawing_pages,
            )

        self.assertEqual(analyzer.timeout, 300.0)
        self.assertEqual(analyzer.max_retries, 0)
        self.assertEqual(analyzer.reasoning_effort, "medium")
        self.assertEqual(analyzer.seen_context["visual_task"], "special_characteristic_locator")
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/three_table_workflow/test_drawing_analysis.py::DrawingAnalysisTests::test_focused_special_characteristic_locator_uses_medium_reasoning_by_default -q
```

Expected result before implementation:

```text
FAILED ... AssertionError: 'xhigh' != 'medium'
```

- [ ] **Step 3: Add the reasoning default and parser**

In `minos_core/pipeline/drawing_analysis.py`, near the focused constants, add:

```python
FOCUSED_SPECIAL_CHARACTERISTIC_REASONING_EFFORT = "medium"
```

Below `_apply_focused_special_characteristic_runtime_limits`, add:

```python
def _focused_special_characteristic_reasoning_effort(
    context_payload: dict[str, Any],
) -> str:
    value = context_payload.get(
        "special_characteristic_locator_reasoning_effort",
        context_payload.get("focused_special_characteristic_reasoning_effort"),
    )
    if value in (None, ""):
        return FOCUSED_SPECIAL_CHARACTERISTIC_REASONING_EFFORT
    normalized = str(value).strip().lower()
    if normalized not in {"low", "medium", "high", "xhigh"}:
        raise ValueError(
            "special_characteristic_locator_reasoning_effort must be one of "
            "low, medium, high, xhigh"
        )
    return normalized
```

- [ ] **Step 4: Apply the reasoning override in the focused locator runner**

In `_run_focused_special_characteristic_visual_locator`, after `_apply_focused_special_characteristic_runtime_limits(...)`, add:

```python
    if hasattr(active_analyzer, "reasoning_effort"):
        setattr(
            active_analyzer,
            "reasoning_effort",
            _focused_special_characteristic_reasoning_effort(context_payload),
        )
```

- [ ] **Step 5: Run the focused reasoning test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/three_table_workflow/test_drawing_analysis.py::DrawingAnalysisTests::test_focused_special_characteristic_locator_uses_medium_reasoning_by_default -q
```

Expected result:

```text
1 passed
```

---

### Task 5: Add Detailed Retry Only When Broad Locator Is Incomplete

**Files:**
- Modify: `tests/three_table_workflow/test_drawing_analysis.py`
- Modify: `minos_core/pipeline/drawing_analysis.py`
- Test: `tests/three_table_workflow/test_drawing_analysis.py`

- [ ] **Step 1: Add a test for broad-then-detailed retry**

Add this test method inside `DrawingAnalysisTests`:

```python
    def test_focused_locator_retries_detailed_when_broad_pass_misses_declared_counts(self):
        class _Analyzer:
            def __init__(self):
                self.contexts = []
                self.timeout = 0
                self.max_retries = 0
                self.reasoning_effort = "xhigh"

            def analyze_drawing_pages(self, _pages, _context=None):
                context = dict(_context or {})
                self.contexts.append(context)
                if context.get("special_characteristic_locator_detail") != "detailed":
                    payload = {
                        "declared_totals": {"CC": 2, "SC": 1},
                        "located_occurrences": [],
                        "special_characteristic_candidates": [],
                        "special_characteristic_locations": [],
                        "missing_counts": {"CC": 2, "SC": 1},
                        "focused_review_requests": [
                            {"request_id": "FRR-BROAD", "target_region": "technical_requirements"}
                        ],
                    }
                else:
                    payload = {
                        "declared_totals": {"CC": 2, "SC": 1},
                        "located_occurrences": [
                            {
                                "candidate_id": "SC-REQ4-TORQUE",
                                "candidate_type": "SC",
                                "source": "gpt55_visual_locator",
                                "symbol_text_or_shape": "SC marker",
                                "linked_feature": "转动力矩(0.5~2.5)Nm",
                                "symbol_bbox": [1, 2, 3, 4],
                                "linked_feature_bbox": [5, 6, 7, 8],
                                "evidence_refs": ["drawing_page_001"],
                                "confidence": 0.82,
                                "reasoning": "详细裁剪确认SC。",
                            }
                        ],
                        "special_characteristic_candidates": [],
                        "special_characteristic_locations": [],
                        "missing_counts": {"CC": 2},
                        "focused_review_requests": [],
                    }
                return MultimodalDrawingResult(
                    content=json.dumps(payload, ensure_ascii=False),
                    model="gpt-5.5",
                    metadata={"source": "gpt55_visual_locator"},
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            source = load_drawing_source(SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png"))
            pages = render_drawing_pages(source)
            analyzer = _Analyzer()

            from minos_core.pipeline.drawing_analysis import (
                _run_focused_special_characteristic_visual_locator,
            )

            result = _run_focused_special_characteristic_visual_locator(
                pages,
                {},
                analyzer=analyzer,
                default_analyzer_factory=lambda: analyzer,
                analyze_drawing_pages=analyze_drawing_pages,
            )

        self.assertEqual(len(analyzer.contexts), 2)
        self.assertEqual(analyzer.contexts[0]["special_characteristic_locator_detail"], "broad")
        self.assertEqual(analyzer.contexts[1]["special_characteristic_locator_detail"], "detailed")
        self.assertEqual(result["declared_totals"], {"CC": 2, "SC": 1})
        self.assertEqual(result["located_occurrences"][0]["candidate_id"], "SC-REQ4-TORQUE")
```

- [ ] **Step 2: Add a test that detailed retry does not run when broad pass is complete**

Add this test method inside `DrawingAnalysisTests`:

```python
    def test_focused_locator_does_not_retry_when_broad_pass_finds_all_declared_counts(self):
        class _Analyzer:
            def __init__(self):
                self.contexts = []
                self.timeout = 0
                self.max_retries = 0
                self.reasoning_effort = "xhigh"

            def analyze_drawing_pages(self, _pages, _context=None):
                self.contexts.append(dict(_context or {}))
                payload = {
                    "declared_totals": {"CC": 1, "SC": 0},
                    "located_occurrences": [
                        {
                            "candidate_id": "CC-REQ5",
                            "candidate_type": "CC",
                            "source": "gpt55_visual_locator",
                            "symbol_text_or_shape": "CC marker",
                            "linked_feature": "GB 15086",
                            "symbol_bbox": [1, 2, 3, 4],
                            "linked_feature_bbox": [5, 6, 7, 8],
                            "evidence_refs": ["drawing_page_001"],
                            "confidence": 0.88,
                            "reasoning": "广域裁剪已确认CC。",
                        }
                    ],
                    "special_characteristic_candidates": [],
                    "special_characteristic_locations": [],
                    "missing_counts": {},
                    "focused_review_requests": [],
                }
                return MultimodalDrawingResult(
                    content=json.dumps(payload, ensure_ascii=False),
                    model="gpt-5.5",
                    metadata={"source": "gpt55_visual_locator"},
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            source = load_drawing_source(SharedTestHelpers.write_png(Path(tmpdir) / "drawing.png"))
            pages = render_drawing_pages(source)
            analyzer = _Analyzer()

            from minos_core.pipeline.drawing_analysis import (
                _run_focused_special_characteristic_visual_locator,
            )

            result = _run_focused_special_characteristic_visual_locator(
                pages,
                {},
                analyzer=analyzer,
                default_analyzer_factory=lambda: analyzer,
                analyze_drawing_pages=analyze_drawing_pages,
            )

        self.assertEqual(len(analyzer.contexts), 1)
        self.assertEqual(analyzer.contexts[0]["special_characteristic_locator_detail"], "broad")
        self.assertEqual(result["located_occurrences"][0]["candidate_id"], "CC-REQ5")
```

- [ ] **Step 3: Add retry helper functions**

In `minos_core/pipeline/drawing_analysis.py`, add these helpers below `_merge_focused_special_characteristic_analysis`:

```python
def _focused_locator_needs_detailed_retry(result: dict[str, Any] | None) -> bool:
    if not isinstance(result, dict):
        return False
    declared = result.get("declared_totals")
    if not isinstance(declared, dict):
        return False
    expected_cc = _non_negative_count(declared.get("CC"))
    expected_sc = _non_negative_count(declared.get("SC"))
    if expected_cc <= 0 and expected_sc <= 0:
        return False
    found = {"CC": 0, "SC": 0}
    for item in result.get("located_occurrences", []):
        if not isinstance(item, dict):
            continue
        classification = str(item.get("candidate_type", "")).strip().upper()
        if classification in found:
            found[classification] += 1
    missing = result.get("missing_counts")
    if isinstance(missing, dict):
        if _non_negative_count(missing.get("CC")) > 0:
            return True
        if _non_negative_count(missing.get("SC")) > 0:
            return True
    return found["CC"] < expected_cc or found["SC"] < expected_sc
```

- [ ] **Step 4: Set broad detail in the first focused run and retry detailed only when needed**

Replace the tail of `_run_focused_special_characteristic_visual_locator` with:

```python
    focused_context = dict(context_payload)
    focused_context["visual_task"] = "special_characteristic_locator"
    focused_context["focused_special_characteristic_only"] = True
    focused_context.setdefault("special_characteristic_locator_detail", "broad")
    focused_context.setdefault(
        "special_characteristic_locator_scope",
        "title_block,key_product_characteristic_table,technical_requirements",
    )
    focused_analysis = analyze_drawing_pages(pages, active_analyzer, focused_context)
    if not _focused_locator_needs_detailed_retry(focused_analysis):
        return focused_analysis

    detailed_context = dict(focused_context)
    detailed_context["special_characteristic_locator_detail"] = "detailed"
    detailed_analysis = analyze_drawing_pages(pages, active_analyzer, detailed_context)
    _merge_focused_special_characteristic_analysis(focused_analysis, detailed_analysis)
    return focused_analysis
```

- [ ] **Step 5: Run the retry tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/three_table_workflow/test_drawing_analysis.py::DrawingAnalysisTests::test_focused_locator_retries_detailed_when_broad_pass_misses_declared_counts tests/three_table_workflow/test_drawing_analysis.py::DrawingAnalysisTests::test_focused_locator_does_not_retry_when_broad_pass_finds_all_declared_counts -q
```

Expected result:

```text
2 passed
```

---

### Task 6: Verify Existing Hybrid Fallback Tests Still Pass

**Files:**
- Test: `tests/three_table_workflow/test_drawing_analysis.py`
- Test: `tests/test_openai_multimodal_adapter.py`

- [ ] **Step 1: Run the focused adapter and drawing-analysis tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_openai_multimodal_adapter.py tests/three_table_workflow/test_drawing_analysis.py -q
```

Expected result:

```text
all tests passed
```

- [ ] **Step 2: Run the broader special-characteristic tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_special_characteristic_discovery.py tests/test_special_characteristics_evidence.py tests/test_special_characteristics_judge.py tests/test_pipeline_ocr_first.py -q
```

Expected result:

```text
all tests passed
```

---

### Task 7: Real Drawing Acceptance Check

**Files:**
- No source file modifications.
- Runtime artifact directory: `D:\MINOS-CORE\.tmp\lean-special-locator-acceptance-*`

- [ ] **Step 1: Run a one-off real focused-locator script**

Run this after the unit tests pass:

```powershell
@'
from __future__ import annotations
import json
import time
from datetime import datetime
from pathlib import Path

from minos_core.adapters.multimodal import OpenAIResponsesMultimodalDrawingAnalyzer
from minos_core.drawing_analysis import analyze_drawing_pages
from minos_core.drawing_input import load_drawing_source, render_drawing_pages
from minos_core.pipeline.hybrid_fusion import _ocr_summary_for_context

ROOT = Path(r"D:\MINOS-CORE")
DRAWING = ROOT / "release" / "diagnostic-run6-replay" / "input.pdf"
PREVIOUS = ROOT / ".tmp" / "browser-latest-run" / "out" / "manual-drawing-test-20260608-171900" / "three_table_generation_result.json"
OUT = ROOT / ".tmp" / f"lean-special-locator-acceptance-{datetime.now():%Y%m%d-%H%M%S}"
OUT.mkdir(parents=True, exist_ok=True)

previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))
ocr = previous.get("drawing_analysis", {})
source = load_drawing_source(DRAWING)
pages = render_drawing_pages(source, OUT / "pages")
context = {
    "analysis_mode": "hybrid",
    "ocr_engine": "mineru",
    "ocr_analysis_summary": _ocr_summary_for_context(ocr),
    "special_characteristic_discovery_request": {
        "declared_totals": dict(ocr.get("declared_totals", {}))
        if isinstance(ocr.get("declared_totals"), dict)
        else {},
        "declared_special_characteristics": [
            dict(item)
            for item in ocr.get("declared_special_characteristics", [])
            if isinstance(item, dict)
        ],
    },
    "visual_task": "special_characteristic_locator",
    "focused_special_characteristic_only": True,
}
analyzer = OpenAIResponsesMultimodalDrawingAnalyzer(timeout=300, max_retries=0)
analyzer.reasoning_effort = "medium"
start = time.monotonic()
bundle = analyze_drawing_pages(pages, analyzer, context)
elapsed = time.monotonic() - start
summary = {
    "elapsed_seconds": round(elapsed, 3),
    "declared_totals": bundle.get("declared_totals"),
    "located_count": len(bundle.get("located_occurrences", [])),
    "candidate_count": len(bundle.get("special_characteristic_candidates", [])),
    "location_count": len(bundle.get("special_characteristic_locations", [])),
    "focused_review_count": len(bundle.get("focused_review_requests", [])),
    "located_occurrences": bundle.get("located_occurrences", []),
}
(OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"out": str(OUT), **summary}, ensure_ascii=False, indent=2))
'@ | .\.venv\Scripts\python.exe -
```

Expected result:

```json
{
  "declared_totals": {"CC": 2, "SC": 1},
  "located_count": 3
}
```

The `elapsed_seconds` target is under 90 seconds. If the broad pass alone finds all three candidates, the expected runtime should be much closer to the earlier 8 to 20 second checks.

- [ ] **Step 2: Run the browser import again**

Use the existing local app at `http://127.0.0.1:1420/` with the same drawing:

```text
D:\MINOS-CORE\release\diagnostic-run6-replay\input.pdf
```

Expected result:

```text
PFD generates and the special-characteristic source data contains declared_totals CC=2, SC=1 plus visual candidates.
```

- [ ] **Step 3: Query the newest run through the desktop API**

Run:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/runs/<RUN_ID>' -Headers @{ Authorization = 'Bearer codex-browser-v380-token' }
```

Expected result:

```text
drawing_analysis.declared_totals.CC = 2
drawing_analysis.declared_totals.SC = 1
drawing_analysis.special_characteristic_candidates.Count >= 3
analysis_errors does not contain special_characteristic_locator timeout
```

---

## Self-Review

- Spec coverage: The plan addresses the observed root cause: the focused locator uses the right key and URL but sends an oversized task that sits near the timeout line.
- Placeholder scan: The plan contains exact files, exact tests, exact code snippets, exact commands, and expected results.
- Type consistency: The plan uses existing context keys and output keys already consumed by `analyze_drawing_pages` and `_merge_focused_special_characteristic_analysis`.
- Risk: The detailed retry can still take longer than the broad pass, but it only runs when broad evidence is incomplete. This is safer than always sending seven images plus the full broad JSON contract.
