# Proposal: V1.14.23 MinerU Default OCR Engine

## Why
当前 MINOS-CORE 的图纸识别主线已经是 OCR-first：PDF 渲染、文字层、RapidOCR 和 OCR evidence merge 先产出可追溯事实，后续由 MINOS 负责图纸理解、零件族判断、PFD/PFMEA/CP 推理、人工复核和导出门。

现有 PyMuPDF 文字层和 RapidOCR 路径对简单 PDF、旧环境和兼容回归仍有价值，但默认 OCR 解析层需要升级为 MinerU-first：默认 `auto` 应优先调用 MinerU 获取文本、版面、页面结构和可追溯 evidence；旧 `pdf_text` / `rapidocr` 作为显式兼容引擎保留，不再代表默认路径。

这次替换只发生在 OCR 解析层。MinerU 不替代 MINOS 的 domain extraction、证据追溯、drawing_analysis、零件族判断、PFD/PFMEA/CP 推理、质量门、人工复核或导出门。

## What
- 将 MinerU 定义为默认 OCR 解析引擎：`auto` 进入 MinerU-first 分支，再进入 OCR evidence merge。
- 保留显式兼容入口：`ocr_engine=pdf_text` 使用旧 PyMuPDF/文字层路径，`ocr_engine=rapidocr` 使用旧 RapidOCR 路径。
- 明确 `ocr_engine=mineru` 仍可作为显式 MinerU 入口，但它与 `auto` 的默认 OCR 解析层一致。
- 明确 MINOS 继续负责 domain extraction、drawing_analysis、零件族、PFD、PFMEA、CP、联动审核、质量门、人工复核和导出门。
- 同步任务计划、进度、发现和流程图，流程图把 MinerU 放入默认 OCR 分支，并把 PyMuPDF/RapidOCR 标为 compatibility fallback / explicit legacy branch。
- 写清楚应用封装风险：发布版不能依赖 Codex 私有路径定位 MinerU，必须通过 `MINOS_MINERU_COMMAND`、`MINERU_COMMAND`、系统 `PATH` 或打包配置定位。

## Non-goals
- 不把 MinerU 输出直接当成 PFD、PFMEA、CP 或最终工程结论。
- 不让 MinerU 绕过 MINOS 的证据合并、质量门、人工确认和三表业务链路。
- 不删除 `pdf_text` / `rapidocr` 兼容入口。
- 不在文档里承诺 Codex 私有安装路径可用于应用发布版。
- 不声明 MinerU 安装包、真实 MinerU CLI 或发布版 bundled MinerU 已经完成验收，除非后续有独立验证证据。

## Acceptance
- OpenSpec proposal、design、tasks 使用中文 UTF-8 可读。
- `task_plan.md`、`progress.md`、`findings.md` 记录 MinerU-first 默认、显式 legacy 兼容入口和发布封装定位风险。
- `project_flow.mmd` 把 MinerU 放在默认 OCR 分支，`pdf_text` / `rapidocr` 位于 compatibility fallback / explicit legacy branch，并连接到 `OCR evidence merge`。
- Mermaid 节点 ID 不重复，流程图语法保持 `flowchart TD` 可解析的基本结构。
- `MinerUOCRAdapter` 可把 MinerU Markdown/文本解析结果归一为 `OCRResult`。
- CLI、pipeline 和 desktop API 的 `auto` 默认进入 MinerU-first；显式 `ocr_engine=pdf_text|rapidocr|mineru` 保持可选。
- OCR 对比命令可对同一图纸输出多个 OCR 引擎的摘要 JSON。
