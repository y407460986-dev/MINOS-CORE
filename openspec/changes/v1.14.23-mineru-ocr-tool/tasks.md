# Tasks: V1.14.23 MinerU Default OCR Engine

## Define
- [x] /// 1. 意图：把 MinerU 定义为默认 OCR 解析引擎。输入：现有 OpenSpec 与流程文档。输出：`auto` 默认 MinerU-first 的产品边界。验证：文档中明确 MinerU 是默认 OCR 解析层。
- [x] /// 2. 意图：保留旧引擎但降级为兼容入口。输入：`pdf_text`、`rapidocr` 旧路径语义。输出：显式 compatibility fallback / explicit legacy branch 说明。验证：文档明确 `pdf_text` / `rapidocr` 不再是默认。
- [x] /// 3. 意图：防止 MinerU 被误解为业务推理替代品。输入：MINOS domain extraction、证据追溯、三表链路、质量门和人工复核边界。输出：MinerU 只替代 OCR 解析层的职责说明。验证：proposal/design/tasks 均写明 MINOS 继续负责三表和审核闭环。

## Specify
- [x] /// 4. 意图：更新 OpenSpec proposal。输入：用户要求的 MinerU-first 默认和应用封装风险。输出：新的 why/what/non-goals/acceptance。验证：proposal 说明默认 MinerU、legacy 显式兼容和 `MINOS_MINERU_COMMAND` / `MINERU_COMMAND` / `PATH` 定位要求。
- [x] /// 5. 意图：更新 OpenSpec design。输入：engine 选择语义、evidence merge、打包约束。输出：默认流、兼容流、runtime adapter 和 packaging risk 设计。验证：design 明确不能依赖 Codex 私有路径。
- [x] /// 6. 意图：更新 OpenSpec tasks。输入：本轮执行动作。输出：每个步骤包含意图、输入、输出、验证点的 `///` 记录。验证：tasks 中每条执行项均可追溯到用户要求。

## Implement
- [x] /// 7. 意图：记录运行时入口应改为 MinerU-first。输入：pipeline、CLI、desktop API 的 OCR engine 选择。输出：`auto` 默认 MinerU、`mineru` 显式同路、`pdf_text` / `rapidocr` 显式 legacy 的任务说明。验证：本轮文档不再把 `mineru` 写成唯一显式入口。
- [x] /// 8. 意图：记录 adapter 归一化边界。输入：MinerU Markdown/文本/页面结构输出。输出：`OCRResult / OCRPageText / OCRBlock` evidence。验证：任务说明不把 adapter 输出提升为 PFD/PFMEA/CP。
- [x] /// 9. 意图：记录发布封装定位风险。输入：打包版不能使用开发机私有路径的约束。输出：通过 `MINOS_MINERU_COMMAND`、`MINERU_COMMAND`、`PATH` 或打包配置定位 MinerU 的任务项。验证：design/findings/progress 均有同一风险表述。
- [x] /// 10. 意图：同步根流程文档。输入：`task_plan.md`、`progress.md`、`findings.md`、`project_flow.mmd`。输出：MinerU-first、legacy fallback 和封装风险记录。验证：rg 不再在 V1.14.23 小节命中旧结论。

## Verify
- [x] /// 11. 意图：检查文档编码。输入：OpenSpec 与根文档路径。输出：UTF-8 读取结果。验证：PowerShell UTF-8 读取检查通过且无乱码异常。
- [x] /// 12. 意图：检查流程图节点唯一性。输入：`project_flow.mmd`。输出：Mermaid 节点 ID 统计。验证：重复节点 ID 列表为空。
- [x] /// 13. 意图：检查默认 OCR 流向。输入：`project_flow.mmd` MinerU / legacy 节点。输出：MinerU 默认分支和 legacy 分支都接入 `OCR evidence merge`。验证：脚本断言关键边存在。
- [x] /// 14. 意图：检查文档 diff 质量。输入：本轮负责文件。输出：`git diff --check` 结果。验证：无 trailing whitespace 或 conflict marker。
