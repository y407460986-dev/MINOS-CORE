# Design: V1.14.1 OCR-first Drawing Analysis

## Design Principle
V1.14.1 的设计原则是“先有可追溯 OCR 事实，再做可选 AI 增强”。OCR-first 不是不要 AI，而是把 AI 从唯一入口改成增强入口：OCR 能给出稳定、可审计、可复核的基础事实，AI 用来提高理解质量，但 AI 流式错误不能抹掉 OCR 已经拿到的证据。

## OCR Evidence Pipeline
图纸入口分成三条证据来源，最后合并为统一 OCR evidence：
- PDF 渲染：每页生成 `drawing_page` 图像证据，记录 `page_number`、`image_size`、`render_backend`、`file_hash`、`source_path`。
- PDF 文字层：抽取可选择文本，记录 `text_block_id`、`page_number`、文本内容、区域或位置线索、来源 PDF。
- RapidOCR：对渲染页或图片执行 OCR，记录 `ocr_block_id`、`page_number`、文本、置信度、bbox、OCR 引擎版本和图像 evidence ref。

三类证据合并时不能只拼文本。合并结果必须保留来源类型、页码、块 ID、置信度、区域框和父 evidence ref，后续每个 `drawing_analysis` 事实都引用这些块。

## OCR Drawing Analysis
OCR `drawing_analysis` 只基于 OCR evidence 先生成一个可独立运行的分析结果：
- 尺寸、公差、GD&T、材料、表面处理、图纸注释、引用标准、特殊特性和工艺线索都可以来自 OCR 文本块。
- 低置信、冲突、疑似误识别、跨页上下文不完整的事实进入 `review_debts`。
- 没有证据引用的事实不得进入正式 `drawing_analysis`。
- OCR-only 结果可以继续进入零件族识别和三表草案，但正式导出仍受 V1.14 闭环质量门约束。

## Hybrid AI Enhancement
AI 增强只在 OCR evidence 和 OCR `drawing_analysis` 已经存在后运行：
- 输入包含页面图像、OCR 文本块和当前 OCR 分析结果。
- 输出只能补充候选事实、纠错建议、置信度解释、零件族线索和人工复核建议。
- AI 输出必须引用 OCR evidence 或页面 evidence；不能凭空新增无来源事实。
- `stream_read_error`、超时或模型输出非法 JSON 时，记录为 `ai_enhancement_issue`，保留 OCR-first 结果继续下游。
- 如果 OCR 本身失败或证据为空，则不能用 AI 增强伪造一条“成功”的图纸事实链。

## Downstream Flow
V1.14.1 不重写下游，只调整图纸入口的事实来源：
- OCR-first `drawing_analysis` -> 零件族识别。
- 零件族上下文 -> PFD 草案。
- PFD -> PFMEA -> CP 三表。
- 三表结果进入 V1.14 闭环：知识推荐、三表联动、行动项和导出门。
- 导出门继续区分草案和正式：草案可带 OCR/AI 问题，正式导出必须关闭关键未闭环问题。

## OpenSpec Loop
- Define：目标是建立 OCR-first/hybrid 图纸分析基线，让 GPT 视觉增强失败不拖垮整条链路。
- Specify：定义 PDF 渲染、PDF 文字层、RapidOCR、OCR drawing_analysis、可选 AI 增强和追溯字段。
- Implement：先落文档与流程，再由代码子任务实现 OCR evidence、OCR 分析器、hybrid 增强和质量门记录。
- Verify：用 PDF/图片样例验证 OCR-only 可生成三表草案，AI `stream_read_error` 被记录但不整体失败，所有 OCR 事实可追溯。
