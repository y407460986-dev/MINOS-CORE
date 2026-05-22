# Proposal: V1.14.22 Quiet Focused UI Motion Refactor

## Why
当前 Tauri 桌面端已经具备图纸导入、三表编辑、阶段确认和设置能力，但工作台体验仍需要继续收口：动效应由统一 motion token 管理，体验组件应承担重复的安静反馈与页面结构，三表编辑区应保持主画布优先，操作应集中在浮动工具条和阶段区，而不是重新引入右侧 `InspectorPanel` 或让导入页在导航时丢失运行状态。

## What
- 新增静态测试契约，锁定 motion token、体验组件、三表编辑画布、浮动工具条、无 `InspectorPanel` 和导入页保活。
- 建立本变更的 OpenSpec proposal、design、tasks。
- 更新任务计划、进度、发现和流程图，记录本轮只承担文档、OpenSpec、测试与交付审核部分。

## Non-goals
- 不修改前端页面实现。
- 不修改后端、Tauri Rust 或 Python 业务逻辑。
- 不声明 UI motion 重构已经完成。
- 不把所有 OpenSpec tasks 标成完成。

## Acceptance
- `openspec/changes/v1.14.22-quiet-focused-ui-motion-refactor/` 下存在 proposal、design、tasks。
- `task_plan.md`、`progress.md`、`findings.md`、`project_flow.mmd` 记录 V1.14.22 文档流程。
- `tests/test_desktop_tauri_app_state.py` 含静态契约，覆盖 motion token、体验组件、三表编辑画布、浮动工具条、无 `InspectorPanel`、导入页保活。
- 文档为 UTF-8，可读取；`project_flow.mmd` 节点 ID 不重复。
