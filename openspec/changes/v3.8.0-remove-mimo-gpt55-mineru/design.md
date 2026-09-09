# v3.8.0 GPT5.5 + MinerU 特殊特性识别设计

## Define

v3.8.0 的特殊特性识别链路只有三个正式角色：

- MinerU/OCR：提取标题栏、技术要求、图例文本、声明数量。
- GPT5.5 visual locator：查看整页和局部裁剪，定位 CC/SC 候选落点。
- GPT5.5 evidence judge：根据 evidence packet 确认或退回复核。

Mimo 不是 fallback，也不是可选 provider。历史 Mimo 设计保留为已被 v3.8.0 取代的记录。

## Specify

### 配置约束

- `load_vision_config()` 必须返回 OpenAI Responses 配置。
- `MINOS_VISION_PROVIDER=mimo`、`MINOS_MIMO_API_KEY`、`MINOS_MIMO_MODEL`、`MINOS_MIMO_BASE_URL` 不得改变视觉通道。
- `create_default_multimodal_drawing_analyzer()` 必须返回 `OpenAIResponsesMultimodalDrawingAnalyzer`。

### 视觉证据约束

系统必须从每页渲染图生成视觉证据区域：

- full page
- title block special counts
- key product characteristic table
- technical requirements area
- per-requirement focused crops
- dimension/GD&T focused crops when OCR 或 locator 提示需要复核

### 识别闭环

1. MinerU/OCR 先产生 `declared_totals`。
2. GPT5.5 visual locator 必须基于图例和局部裁剪输出 `located_occurrences`。
3. 如果 `located_occurrences` 数量少于 `declared_totals`，系统必须发起 focused review 或产生数量风险。
4. evidence judge 只能确认引用了候选证据、声明/图例证据和页面证据的项目。
5. 下游 registry 和三表只能继承 `judge_confirmed` 或 `human_confirmed` 的特殊特性。

### JLV 回归事实

- `SC-REQ4-TORQUE`: 技术要求第 4 条第(2)项，`转动力矩(0.5~2.5)Nm` 的水平圆角长框。
- `CC-REQ5-GB15086`: 技术要求第 5 条，`GB 15086`。
- `CC-REQ6-M0102`: 技术要求第 6 条，`Q/BJORV M 0102`。

## Implement

/// 1. 删除 Mimo 配置分支和 adapter。
/// 2. 重写 Mimo 相关测试为 GPT5.5/OpenAI Responses 测试。
/// 3. 新增 `drawing_visual_evidence` 裁剪模块。
/// 4. 新增 `special_characteristics_visual_locator`。
/// 5. 将 locator 输出接入 hybrid fusion 和 evidence packet。
/// 6. 清理 Mimo 命名残留。
/// 7. 增加 JLV 真实图纸回归。
/// 8. 同步版本到 3.8.0。

## Verify

/// 1. `python -m pytest tests/test_ai_config.py -q`
/// 2. `python -m pytest tests/test_openai_multimodal_adapter.py -q`
/// 3. `python -m pytest tests/test_drawing_visual_evidence.py tests/test_special_characteristics_visual_locator.py -q`
/// 4. `python -m pytest tests/test_special_characteristics_evidence.py tests/test_special_characteristics_judge.py -q`
/// 5. `python -m pytest tests/test_pipeline_ocr_first.py tests/three_table_workflow/test_drawing_analysis.py -q`
/// 6. JLV 真实图纸输出 `CC=2, SC=1` 且 SC 为第 4 条第(2)项。
/// 7. `python -m pytest tests/test_release_version_sync.py -q`
/// 8. `powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1`
