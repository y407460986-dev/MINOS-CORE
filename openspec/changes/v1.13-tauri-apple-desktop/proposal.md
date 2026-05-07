# Proposal: V1.13 Tauri Apple Desktop

## Why
MINOS-CORE 已经具备图纸识别、三表生成、三表编辑、联动检查、复核闭环和导出能力。下一步桌面端需要从 PySide6 功能拼装界面迁移到更适合长期产品化的桌面工作台：Tauri + React + Apple 风格交互。

本变更把 V1.13 的迁移目标写清楚，避免后续开发把前端依赖引入 `minos_core`，或把 `minos_platform` 误当成本次桌面主后端。

## What
V1.13 目标：
- 新桌面端采用 Tauri + React，形成 Apple 风格桌面工作台。
- PySide6 桌面端冻结为 legacy，仅保留维护和回归价值，不作为新能力主路径。
- `minos_core` 保持纯核心能力，不引入 React、Tauri、Node、WebView 或其他前端依赖。
- `minos_platform` 不作为本次桌面主后端；本次桌面闭环优先通过 Tauri command / 本地服务边界调用 core 能力。
- 桌面首屏聚焦真实工作台，不做营销式 landing page。
- 工作台必须覆盖图纸选择、三表生成、三表编辑、联动预览刷新、闭环任务处理、导出和 1280x800 可用性。

## Non-goals
- 不在本变更中重写 `minos_core` 业务模型。
- 不把 `minos_platform` 改造成桌面主后端。
- 不把 PySide6 旧界面继续扩展为 V1.13 主界面。
- 不引入多人协作、云端审批流、PLM/ERP/MES 集成。

## Acceptance
- 图纸可选择。
- PFD、PFMEA、CP 三表可生成。
- PFD、PFMEA、CP 三表可编辑。
- 联动预览可刷新。
- 复核、知识推荐、行动项等闭环任务可处理。
- 导出可用，且草案/正式边界清楚。
- 1280x800 分辨率下主要控件和文字无重叠。
