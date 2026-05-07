# Proposal: V1.14.1 OCR-first Drawing Analysis

## Why
V1.14 已经把图纸事实、零件族知识、三表联动、行动闭环和导出门连成一条工程链路。当前需要补一层更稳的图纸入口：真实 GPT 视觉调用可能出现 `stream_read_error`，但这类可选视觉增强失败不能让整条三表生成链路直接失败。

V1.14.1 的目标是把 OCR 作为图纸分析的第一事实来源，先用 PDF 渲染、PDF 文字层和 RapidOCR 建立可追溯文本/区域证据，再生成 `drawing_analysis`。GPT 视觉只作为 hybrid 增强层，用来补充、解释和纠错；它失败时必须被记录为可审计问题，但不能吞掉已经可用的 OCR 事实。

## What
V1.14.1 建立 OCR-first / hybrid 图纸分析基线：
- PDF 渲染：把每一页图纸渲染成页面图像证据，保留页码、尺寸、文件 hash 和渲染状态。
- PDF 文字层：优先抽取可选择文本，保留文本块、页码、坐标或区域线索。
- RapidOCR：对 PDF 渲染页和图片输入执行 OCR，输出文本、置信度、区域框和来源页。
- OCR `drawing_analysis`：先只基于 OCR 证据抽取尺寸、公差、材料、注释、工艺线索、特殊特性和引用标准。
- 可选 AI 增强：在 OCR 结果可用后，再调用 GPT 视觉/文本增强补充结构化字段；`stream_read_error` 进入运行记录和人工复核，不覆盖 OCR 基线。
- 零件族与三表：OCR-first `drawing_analysis` 继续进入零件族识别、PFD、PFMEA、CP、闭环任务和导出门。
- 追溯要求：每个 OCR 派生事实必须能追溯到页码、文本块或区域框、置信度和原始 evidence ref。

## Non-goals
- 不在 V1.14.1 重写 V1.14 的知识复用、三表联动、行动项或导出质量门。
- 不把 GPT 视觉输出作为唯一图纸事实来源。
- 不做 DWG/DXF 原生 CAD 解析，不承诺手写体或极低质量扫描图纸的完整识别。
- 不静默隐藏 AI 增强失败；失败必须进入运行记录、质量门或人工复核。
- 不绕过人工复核、知识推荐处理、行动闭环和正式导出门。

## Acceptance
- OpenSpec proposal/design/tasks 覆盖 OCR-first/hybrid 的目标、非目标、执行步骤和验收标准。
- `task_plan.md` 增加 V1.14.1 OCR-first 可执行计划，步骤全部以 `///` 开头。
- `progress.md` 记录当前进入 V1.14.1，并说明基于 V1.14 已有状态继续推进。
- `findings.md` 记录关键原因：GPT 视觉 `stream_read_error` 不能导致整体失败，OCR 结果必须可追溯。
- `project_flow.mmd` 增加 PDF 渲染、PDF 文字层、RapidOCR、OCR `drawing_analysis`、可选 AI 增强、零件族、PFD、三表、闭环、导出门节点。
- 文档可用 `Get-Content` 正常打开，中文无乱码。
