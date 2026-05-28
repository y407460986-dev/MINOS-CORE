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
- 默认 analysis_mode：`ocr_only`，`hybrid` 在 OCR 失败时回退到 vision；`vision_only` 跳过 OCR。
- AI 调用经由 `minos_core.ai_resilience` 的 `AIServicePool` 与 `CircuitBreaker`；无可用端点时由 `FallbackStrategy` 子类降级。

## 复核与导出闸门

- 一键生成默认输出 **draft**，未经过人工复核的 AI 草案不会自动作为 final release。
- `apply_review` / `apply_edit_patch` 用于注入人工复核结果。
- `evaluate_edit_export_gate` 与 `export_edited_three_tables` 把复核后的链路推送到正式导出路径。
- `require_export_gate` 在写入工作簿前再做一次校验，闸门拦截会抛出 `ExportGateError`。

## 失败处理

链路任一阶段抛出 `MinosError`（含 `ExternalServiceError` / `PipelineError` 等）时：

1. 失败被结构化日志（`minos_core.observability.logging`）捕获；
2. `format_error_for_user` 给出中文用户消息；
3. `retriable=True` 的错误会触发 `ai_resilience` 的重试与降级；
4. 桌面 API 通过 `format_desktop_failure` 把异常翻译为响应体。

详见 [ADR 004](../adr/004-observability.md)。
