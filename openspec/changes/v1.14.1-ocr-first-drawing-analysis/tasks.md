# Tasks: V1.14.1 OCR-first Drawing Analysis

## Define
- [x] /// 1. 明确 V1.14.1 目标：以 OCR-first 建立稳定图纸事实入口，AI 作为 hybrid 增强层。
- [x] /// 2. 明确关键问题：GPT 视觉 `stream_read_error` 不能导致 OCR 已成功的三表链路整体失败。
- [x] /// 3. 明确非目标：不重写 V1.14 闭环，不做 CAD 原生解析，不绕过人工复核和正式导出门。

## Specify
- [x] /// 4. 定义 PDF 渲染 evidence：页码、图像、文件 hash、渲染状态和页面 evidence ref。
- [x] /// 5. 定义 PDF 文字层 evidence：文本块、页码、位置线索和来源 PDF ref。
- [x] /// 6. 定义 RapidOCR evidence：OCR 文本、bbox、置信度、OCR 引擎版本和父页面 ref。
- [x] /// 7. 定义 OCR `drawing_analysis`：尺寸、公差、材料、注释、标准、特殊特性和工艺线索都必须引用 OCR evidence。
- [x] /// 8. 定义 hybrid AI 增强：AI 只能补充和解释，失败进入 `ai_enhancement_issue`，不得覆盖 OCR-first 基线。
- [x] /// 9. 定义下游衔接：OCR `drawing_analysis` -> 零件族 -> PFD -> PFMEA/CP 三表 -> 闭环 -> 导出门。

## Implement
- [x] /// 10. 实现 PDF 渲染证据生成，并把渲染失败记录为明确错误。
- [x] /// 11. 实现 PDF 文字层抽取，把可选择文本转成可引用 text block。
- [x] /// 12. 接入 RapidOCR，把图片/PDF 页面 OCR 输出转成带 bbox 和 confidence 的 evidence。
- [x] /// 13. 实现 OCR-only `drawing_analysis`，不依赖 GPT 视觉也能产出可复核图纸事实。
- [x] /// 14. 接入可选 AI 增强，把 GPT 视觉/文本结果合并为候选增强，不允许无证据事实进入主结果。
- [x] /// 15. 捕获并记录 GPT 视觉 `stream_read_error`，确保 OCR-first 成功时下游仍可继续生成草案。
- [x] /// 16. 把 OCR-first 结果接到零件族、PFD、三表、闭环任务和导出门。

## Verify
- [x] /// 17. 用含文字层 PDF 验证 PDF 文字层和 OCR 证据都能追溯到页码/块 ID。
- [x] /// 18. 用扫描 PDF 或图片验证 RapidOCR 能生成 bbox、confidence 和 OCR evidence ref。
- [x] /// 19. 模拟 GPT 视觉 `stream_read_error`，验证 OCR-only 链路不整体失败，并记录 AI 增强问题。
- [x] /// 20. 验证 OCR `drawing_analysis` 事实没有 evidence ref 时会被质量门或复核项拦住。
- [x] /// 21. 验证 OCR-first/hybrid 结果能进入零件族、PFD、PFMEA、CP、闭环和导出门。
- [x] /// 22. 验证草案导出会标记 OCR/AI 待复核问题，正式导出仍被关键未闭环问题阻断。
