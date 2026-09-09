# Tasks: V1.14.22 Quiet Focused UI Motion Refactor

## Define
- [x] /// 1. 明确本轮只承担流程文档、OpenSpec、静态测试与交付审核，不改前端页面或后端。
- [x] /// 2. 明确目标体验契约：motion token、体验组件、三表编辑画布、浮动工具条、无 `InspectorPanel`、导入页保活。

## Specify
- [x] /// 3. 建立 OpenSpec proposal，说明为什么需要安静、聚焦、可持续编辑的 UI motion 收口。
- [x] /// 4. 建立 OpenSpec design，说明静态测试锁定方式和本轮非目标。
- [x] /// 5. 建立 OpenSpec tasks，保持未实现/未验证项不勾选。

## Implement
- [ ] /// 6. 前端实现统一 motion token 和 reduced-motion 兜底。
- [ ] /// 7. 前端实现可复用体验组件，并迁移页面重复样式。
- [ ] /// 8. 前端保持三表编辑画布和浮动上下文工具条为主操作面。
- [ ] /// 9. 前端继续删除右侧 `InspectorPanel`，保留 `PreviewRail`。
- [ ] /// 10. 前端保持图纸导入页 mounted，导航时不丢失链式生成状态。

> **⚠️ Postponed (2026-05-30):** Tasks #6–#10 are deferred to the next release cycle.
> v3.2.1 ships with stability/security fixes only. These UI motion refactor items
> remain scoped to v1.14.22 and will be picked up in the next feature window.

- [x] /// 11. 文档侧更新 `task_plan.md`、`progress.md`、`findings.md`、`project_flow.mmd`。
- [x] /// 12. 新增并跑通 Tauri 静态测试契约。

## Verify
- [x] /// 13. 运行 `python -m pytest tests/test_desktop_tauri_app_state.py -q`。
- [x] /// 14. 检查 OpenSpec 和文档 UTF-8 可读取。
- [x] /// 15. 检查 `project_flow.mmd` 节点 ID 不重复。
