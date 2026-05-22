# Proposal: V1.14.21 Generated Output Audit Fixes

## Why
当前工作区已经生成了安装包、sidecar、设置页和本地数据管理能力，但审查发现测试、文档和打包生成物存在不一致：API 回归仍按旧流程断言，SQLite 备份可能漏 WAL，Tauri build script 会污染真实 sidecar 目录，README 和流程图仍引用过期模型、测试和 Codex base URL 语义。

## What
- 修正 API 回归测试，使其符合当前链式 PFMEA `on_progress` 和 CP 确认后批量确认规则。
- 将本地数据备份改成 SQLite 在线备份，覆盖 WAL 数据。
- 修复 Tauri `build.rs`，已有真实 `_internal` 时不写 `.placeholder`。
- 让 `release:nsis` 先重建 sidecar；发布脚本复制安装包到 `dist/build/out`。
- 更新 README、OpenSpec V1.13 和 Mermaid 流程图的过期记录。

## Non-goals
- 不改三表生成算法。
- 不重新打包安装包。
- 不做全量 UI 视觉重设计。

## Acceptance
- 相关 Python API/服务测试通过。
- Tauri 静态测试覆盖打包脚本行为。
- `cargo check` 不再污染真实 sidecar `_internal` 目录。
- README、OpenSpec 和流程图不再指向不存在测试或过期 AI URL 语义。
