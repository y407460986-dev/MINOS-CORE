# v3.8.7 Production Readiness Remediation

## Why

全仓审查确认三表核心测试通过，但桌面 sidecar 生命周期、Platform 默认鉴权、CI 依赖复现、静态检查门禁、Windows 安装包和桌面 undo/redo 仍存在可复现风险。当前这些问题分散在运行时、构建配置和服务层，继续叠加功能会扩大交付风险。

## What

- 让 Tauri 只管理自己启动的 sidecar，处理并发 bootstrap、PID 退出、readiness 超时和单次 close listener。
- 让 Platform 默认拒绝未认证请求，仅允许显式开发开关关闭鉴权。
- 让 CI 在干净环境安装 Desktop/OCR/Node/Rust 所需依赖，并将静态检查、覆盖率和构建警告变成真实门禁。
- 建立 unsigned 内测包与 Authenticode 签名正式包的 Windows 发布链路。
- 删除不可达同名 facade，建立 request-scoped Repository/Service 边界。
- 将桌面 undo/redo 持久化到 SQLite 的原子事务，并修复 edit-patch 与 API 成功路径。
- 分阶段拆分 `DesktopRunService`，保持现有三表业务行为和公共 API。

## Non-goals

- 不改变图纸 -> PFD -> PFMEA -> CP 的业务算法和输出契约。
- 不扩展 PPAP 平台业务范围或新增多租户能力。
- 不在同一个 PR 中同时修改 sidecar、数据库 schema 和三表生成逻辑。
- 不通过永久 `noqa`、降低 mypy strictness 或降低 coverage 阈值隐藏债务。
- 不在普通整改 PR 中执行 Git 历史重写或强制清理 reflog。

## Acceptance

- 连续调用 `get_bootstrap` 不会终止已托管 sidecar，也不会启动重复 child。
- sidecar 超时会让 bootstrap 失败；旧 PID 的退出事件不会清理新 PID。
- Platform 未配置 token 时默认返回 401，显式开发开关行为有测试覆盖。
- 干净 checkout 可安装完整 Python/Node 依赖并通过测试；Ruff/mypy 最终为 0 error。
- 覆盖率先建立真实基线，改动行覆盖率 >=80%，最终总覆盖率 >=80%。
- Windows unsigned 包明确标记内测；正式包在创建 release 前完成 Authenticode 签名和验证。
- undo/redo 在 service 重启后可用，edit-patch 可撤销，更新失败时 run/history 一起回滚。
- 三表链路和 Excel 可打开性回归保持通过。
