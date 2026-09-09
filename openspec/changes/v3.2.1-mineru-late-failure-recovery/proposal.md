# Proposal: V3.2.1 MinerU Late Failure Recovery

## Why
用户真实运行中，MinerU 日志显示图纸识别阶段已经长时间运行并进入后处理，但最终报 `All connection attempts failed`。MINOS 之前在 MinerU CLI 非零退出时直接失败，并且错误归因把日志里的 `mineru-api` 误判为“AI 配置可能缺失或不可用”。

这会造成两个问题：如果 MinerU 已经写出可用 Markdown，MINOS 没有复用；如果没有可用输出，用户看到的原因也不准确。

## What
- MinerU CLI 非零退出时，先检查输出目录是否已有可读 Markdown；有则作为 OCR 结果继续生成。
- 没有可用 Markdown 时仍按 MinerU OCR 失败处理，不伪造 OCR 结果。
- 桌面失败归因优先识别 MinerU 本地解析服务连接失败，不再把 `mineru-api` 误判为 AI 配置问题。
- 补回归测试覆盖以上行为。

## Non-goals
- 不修改 MinerU 本身的模型、运行方式或端口管理。
- 不把 OCR 失败静默降级到旧 `pdf_text` / `rapidocr` 默认路径。
- 不更改 PFD/PFMEA/CP 生成逻辑。

## Acceptance
- `tests/test_mineru_ocr_adapter.py` 覆盖非零退出但已有 Markdown 时继续返回 OCR 结果。
- `tests/desktop/test_shell.py` 覆盖 MinerU 本地连接失败的中文原因和处理建议。
- 相关桌面 OCR/API 聚焦回归通过。
