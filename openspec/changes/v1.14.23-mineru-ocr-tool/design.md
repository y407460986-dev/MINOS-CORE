# Design: V1.14.23 MinerU Default OCR Engine

## Scope
本轮把 MinerU 定义为 MINOS 默认 OCR 解析层，并同步 OpenSpec、流程文档和发布风险记录。边界是 OCR evidence 生产方式升级，不是业务推理链路替换。

## Product Boundary
MinerU 的定位是默认 OCR engine：

- `auto` 默认 MinerU-first：默认 OCR 解析优先调用 MinerU。
- `mineru` 显式选择：保留为直接选择 MinerU 的入口，语义与默认 OCR 解析层一致。
- `pdf_text` 显式兼容入口：保留旧 PyMuPDF/可选文字层路径，用于兼容、诊断或无 MinerU 环境下的显式回退。
- `rapidocr` 显式兼容入口：保留旧 RapidOCR 路径，用于兼容、诊断或专项对比，不再是默认。
- 输出职责：MinerU 只提供文字、版面、bbox、置信度、页面结构等 OCR evidence。
- 合并职责：MinerU 输出必须进入 MINOS 的 OCR evidence merge，与显式 legacy 引擎输出统一归并。
- 业务职责：domain extraction、drawing_analysis、零件族推断、工艺路线、PFMEA、CP、审核、确认、导出门仍由 MINOS 负责。

## Flow
流程图应表达为：

1. PDF 渲染或文字层产生页面证据。
2. 默认 `auto` 进入 MinerU OCR engine，产出 OCR/版面 evidence。
3. 显式 `pdf_text` / `rapidocr` 进入 compatibility fallback / explicit legacy branch。
4. MinerU 默认分支和 legacy 分支都接到现有 `OCR evidence merge`。
5. 合并后的 evidence 才进入 `OCR drawing_analysis`、MINOS domain extraction 和后续三表链路。

## Compatibility
- `auto` 的 OCR 解析层改为 MinerU-first，这是本变更的核心行为变化。
- 旧用户需要旧引擎时必须显式选择 `pdf_text` 或 `rapidocr`。
- 不删除 OCR-only、hybrid 的产品语义；它们仍表示是否启用视觉增强和三表链路形态，而不是把 MinerU 变成业务推理模块。
- 不把 MinerU 的版面理解结果直接提升为工程判断；所有业务解释仍需要 MINOS 质量门和人工确认。

## Runtime Adapter
- `MinerUOCRAdapter` 将 MinerU Markdown、文本或页面列表输出归一为现有 `OCRResult / OCRPageText / OCRBlock`。
- 第一版 bbox 和 confidence 可以为空；追溯先依赖页码、block 顺序、engine 和 source_ref。
- 如果调用方注入 parser，则 adapter 使用注入 parser，便于 MCP 或测试接入。
- 如果未注入 parser，则 adapter 必须按 `MINOS_MINERU_COMMAND`、`MINERU_COMMAND`、系统 `PATH`、打包配置的顺序定位 MinerU 命令；缺失或未产出 Markdown 时抛出清晰的 `OCRDependencyError`。

## Packaging Risk
- 发布版不能依赖 Codex、Claude、开发机虚拟环境或用户私有目录中的 MinerU 路径。
- Windows 安装包若要内置 MinerU，必须在打包配置中声明可执行文件、Python 包、模型/资源目录和运行时依赖。
- 如果安装包不内置 MinerU，则启动前检查必须能说明如何通过 `MINOS_MINERU_COMMAND`、`MINERU_COMMAND` 或 `PATH` 提供 MinerU。
- 旧 `pdf_text` / `rapidocr` 只作为显式兼容兜底；不能因为打包版找不到 MinerU 就静默改变 `auto` 默认语义。

## Verification
- 目标 OpenSpec 文件存在且 UTF-8 可读。
- 根文档 UTF-8 可读，无乱码。
- `project_flow.mmd` 中 MinerU 节点 ID 唯一。
- MinerU 默认分支连到 `PL174` OCR evidence merge，不破坏 Mermaid 基本语法。
- `project_flow.mmd` 中 PyMuPDF/RapidOCR 位于 compatibility fallback / explicit legacy branch。
- 单元测试覆盖 MinerU adapter、engine 选择、pipeline fallback、desktop API 透传和 OCR 对比 CLI。
- 默认 `auto` 进入 MinerU-first；显式 `pdf_text` / `rapidocr` 进入旧引擎兼容路径。
