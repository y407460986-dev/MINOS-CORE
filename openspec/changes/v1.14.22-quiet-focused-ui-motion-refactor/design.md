# Design: V1.14.22 Quiet Focused UI Motion Refactor

## Scope
本轮只做流程文档、OpenSpec、静态测试和交付审核，不改前端或后端实现。前端实现可以由并行 worker 继续完成；本轮测试负责把目标体验固化成可检查的源码契约。

## Static Contract
静态测试采用读取源码文本的方式，避免引入浏览器或构建依赖：

- motion token：集中在全局样式中定义 `--motion-fast`、`--motion-base`、`--motion-slow`、`--motion-ease`，并提供 `prefers-reduced-motion` 兜底。
- 体验组件：要求存在可复用的安静界面组件，避免每个页面散落重复的边框、状态和动效样式。
- 三表编辑画布：工作台必须保留 `aria-label="三表编辑画布"`，表格编辑、草稿保存、批量软删除和标记评审从画布内部发起。
- 浮动工具条：多选或草稿编辑时显示 `aria-label="浮动上下文工具条"`，把高频行操作集中到上下文中。
- 无右侧检查器：`App.tsx` 和 `AppShell.tsx` 不得重新引入 `InspectorPanel`、`inspector` slot 或三列布局。
- 导入页保活：`App.tsx` 使用 `hidden={page !== "import"}` 保持导入页 mounted，避免用户切走页面后丢失链式生成状态。

## Documentation
`task_plan.md` 使用 `///` 写开发步骤；`progress.md` 只记录本轮实际完成的文档和测试工作；`findings.md` 记录体验边界和剩余实现风险；`project_flow.mmd` 新增唯一节点 ID 的 V1.14.22 流程。

## Verification
可由本轮验证的内容包括：

- OpenSpec 三件套存在且 UTF-8 可读。
- 文档文件 UTF-8 可读。
- `project_flow.mmd` 节点 ID 不重复。
- 静态测试文件已包含目标契约。

前端实现未由本轮修改，因此若静态测试因前端 motion token 或体验组件尚未落地而失败，应记录为并行实现未合入，不把 OpenSpec tasks 全部勾选。
