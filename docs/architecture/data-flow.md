# 数据流：图纸 → 三表 → 导出

本文件描述 MINOS-CORE 三表生成主链路上的数据流向，并给出每一步对应的真实函数。所有函数均位于 `minos_core/pipeline/` 或 `minos_core/pipeline_chain.py`。

## 一键链路

```text
Drawing PDF/PNG/JPG
        │
        ▼
analyze_drawing_for_three_table_chain   # minos_core/pipeline/drawing_analysis.py
        │   生成 drawing_analysis bundle（OCR + 多模态融合 + family context）
        ▼
generate_three_tables_from_drawing      # minos_core/pipeline/orchestration.py
        │   组装一键链路；内部依次调用 PFD / PFMEA / CP 生成
        │
        ├──► generate_pfd_from_drawing               # minos_core/pipeline_chain.py
        │       └─ LLM 推理生成过程流程图 (PFD)
        │
        ├──► generate_pfmea_from_confirmed_pfd       # minos_core/pipeline_chain.py
        │       └─ 基于已确认的 PFD 生成 PFMEA 失效模式与控制
        │
        └──► generate_cp_from_confirmed_pfmea        # minos_core/pipeline_chain.py
                └─ 基于已确认的 PFMEA 生成控制计划 (Control Plan)
        │
        ▼
assemble_generated_apqp_chain           # minos_core/pipeline/orchestration.py
        │   把 PFD / PFMEA / CP 拼成 APQPChain，并附带 metadata
        ▼
evaluate_export_gate (quality gate)     # minos_core/quality_gates/__init__.py
        │   判断 can_continue / allow_user_export
        ▼
Three-table workbooks                   # minos_core/exporters/three_table_workbooks.py
        - 过程流程图.xlsx
        - PFMEA.xlsx
        - 控制计划.xlsx
        - 统一三表工作簿
```

## 关键函数职责

| 函数 | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| `analyze_drawing_for_three_table_chain` | 图纸路径、analysis_mode、ocr_engine、context | `drawing_analysis_bundle` | 调用 OCR 引擎 + 可选多模态视觉模型，写入 OCR 结果、零件族上下文、复核标记。 |
| `generate_three_tables_from_drawing` | 图纸路径、context、output_dir | three-table envelope | 一键编排函数。先调用 `analyze_drawing_for_three_table_chain`，再串联 PFD/PFMEA/CP 三阶段。 |
| `generate_pfd_from_drawing` | drawing_analysis、model | process_flow bundle | 用 LLM 推理 PFD 步骤；融合零件族工艺路线模板。 |
| `generate_pfmea_from_confirmed_pfd` | 已确认的 PFD、context | PFMEA bundle | 在确认后的 PFD 基础上生成失效模式与原因，并打分。 |
| `generate_cp_from_confirmed_pfmea` | 已确认的 PFMEA | control_plan bundle | 根据 PFMEA 与过程步骤生成控制计划条目。 |
| `assemble_generated_apqp_chain` | 三表 bundle | `APQPChain` | 把 PFD/PFMEA/CP 装配成单一链对象，并写入 metadata。 |
| `evaluate_export_gate` | `APQPChain` | `StageQualityGate` | 计算导出门：是否允许用户导出、是否需要人工复核。 |

## 默认行为与默认值

- 默认 OCR 引擎：`minos_core.pipeline.DEFAULT_OCR_ENGINE`（当前为 MinerU 优先，详见 [ADR 002](../adr/002-ai-resilience.md)）。
- 默认 analysis_mode：`ocr_only`（仅 OCR）；`hybrid` 并行执行 OCR + 多模态视觉分析，融合结果（详见 [Hybrid 分析](#hybrid-分析ocr--多模态融合)）；`vision_only` 跳过 OCR（用于 OCR 不适用的图纸）。
- 特殊特性（SC/CC）自动发现与视觉定位，经由 `special_characteristic_*.py` 模块链路注入三表。
- AI 调用经由 `minos_core.ai_resilience` 的 `AIServicePool` 与 `CircuitBreaker`；无可用端点时由 `FallbackStrategy` 子类降级。

## 复核与导出闸门

- 一键生成默认输出 **draft**，未经过人工复核的 AI 草案不会自动作为 final release。
- `apply_review` / `apply_edit_patch` 用于注入人工复核结果。
- `evaluate_edit_export_gate` 与 `export_edited_three_tables` 把复核后的链路推送到正式导出路径。
- `require_export_gate` 在写入工作簿前再做一次校验，闸门拦截会抛出 `ExportGateError`。

## OCR 引擎对比

```text
minos-core compare-ocr-engines --input drawing.png --engines mineru,rapidocr
        │
        ▼
_compare_ocr_engines                     # minos_core/cli.py
        │   对同一图纸逐个调用各 OCR 引擎
        │
        ├──► MinerUOCRAdapter          # minos_core/adapters/mineru_ocr.py
        │       └─ 基于 MinerU 的版面分析与文本提取
        │
        ├──► analyze_drawing_with_ocr   # minos_core/drawing_ocr_analysis.py
        │       └─ RapidOCR / 通用 OCR 引擎调用
        │
        ▼
    输出对比 JSON（各引擎的逐字段结果）
        │
        ▼
    用户可选择最优引擎进入主链路
```

## Hybrid 分析（OCR + 多模态融合）

```text
analyze_drawing_for_three_table_chain   # minos_core/pipeline/drawing_analysis.py
  with analysis_mode="hybrid"
        │
        ├──► OCR 分析分支
        │       └─ 提取文字、尺寸、公差、特性标注
        │
        ├──► 多模态视觉分析分支
        │       └─ OpenAIResponsesMultimodalDrawingAnalyzer
        │           （minos_core/adapters/multimodal.py）
        │
        ▼
    hybrid_fusion.merge_analysis_results  # minos_core/pipeline/hybrid_fusion.py
        │   融合策略：
        │   - OCR 高信度字段锁定（OCR_IDENTITY_LOCK_CONFIDENCE）
        │   - 多模态补充 OCR 缺失项
        │   - 冲突时取高信度来源
        │
        ▼
    drawing_analysis bundle（含 meta.ocr_engine、meta.hybrid_sources）
```

## 特殊特性（SC/CC）发现流程

```text
drawing_analysis bundle
        │
        ▼
special_characteristic_candidates        # minos_core/special_characteristic_candidates.py
    从 OCR / 多模态结果提取 SC/CC 候选
        │
        ▼
special_characteristic_discovery         # minos_core/special_characteristic_discovery.py
    基于 OCR 文本自动标记 SC/CC 位置
        │
        ▼
special_characteristic_declarations      # minos_core/special_characteristic_declarations.py
    解析图纸上的 SC/CC 声明（如符号 STM、SC、CC、Δ 等）
        │
        ▼
special_characteristics_judge            # minos_core/special_characteristics_judge.py
    规则引擎判定：是否为正式 SC/CC，置信度评分
        │
        ▼
special_characteristics_visual_locator   # minos_core/special_characteristics_visual_locator.py
    在图纸图像上高亮标记 SC/CC 位置（供人工复核）
        │
        ▼
characteristic_registry                  # minos_core/characteristic_registry.py
    build_characteristic_registry / attach_characteristics_to_three_tables
    将 SC/CC 映射注入 PFD / PFMEA / CP 三表
```

## Edit Patch 编辑复核流程

```text
draft 三表（AI 生成）
        │
        ▼
apply_review / apply_edit_patch          # minos_core/pipeline/review_export.py
        │   注入人工复核结果或编辑 patch
        │
        ├──► build_edit_patch                   # minos_core/edit_patch.py
        │       └─ 构建行级修改 patch
        │
        ├──► evaluate_edit_export_gate          # minos_core/edit_patch.py
        │       └─ 评估编辑后的导出就绪状态
        │
        ▼
export_edited_three_tables              # minos_core/edit_patch.py
        │   生成正式 release 三表
        │
        ▼
    过程流程图_final.xlsx
    PFMEA_final.xlsx
    控制计划_final.xlsx
```

## 插件加载流程

```text
应用启动 / CLI 初始化
        │
        ▼
load_entry_point_plugins                 # minos_core/plugins/entrypoints.py
        │   扫描 pyproject.toml entry points
        │   - minos_core.ocr_engines
        │   - minos_core.knowledge_sources
        │
        ├──► register_ocr_engine(name, instance)    # plugins/registry.py
        │       └─ 注入 OCREnginePlugin 实例
        │
        ├──► register_knowledge_source(name, instance)  # plugins/registry.py
        │       └─ 注入 KnowledgeSourcePlugin 实例
        │
        ▼
get_ocr_engine / get_knowledge_source    # plugins/registry.py
        │   运行期按名称查找
        │
        ▼
    pipeline 在分析/推理阶段调用插件实例
```

## 失败处理

链路任一阶段抛出 `MinosError`（含 `ExternalServiceError` / `PipelineError` 等）时：

1. 失败被结构化日志（`minos_core.observability.logging`）捕获；
2. `format_error_for_user` 给出中文用户消息；
3. `retriable=True` 的错误会触发 `ai_resilience` 的重试与降级；
4. 桌面 API 通过 `format_desktop_failure` 把异常翻译为响应体。

详见 [ADR 004](../adr/004-observability.md)。
