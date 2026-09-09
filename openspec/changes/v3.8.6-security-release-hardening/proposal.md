# v3.8.6 安全加固与发布整改 proposal

## Why

MINOS-CORE 当前三表主链路已形成，但本地 sidecar、桌面路径边界、发布制品、CI 与桌面 SQLite migration 仍不足以支撑安全内测和小范围交付。

## What

- 为链式生成 SSE 增加短期 stream token 鉴权。
- 统一桌面 API 的图纸文件和输出目录校验。
- 收紧 Tauri 打开路径命令，只允许打开用户选择过或应用管理范围内的路径。
- 为 Platform API 增加交付环境强制鉴权模式。
- 修复 `SecretStr` Pydantic 序列化明文回显。
- 补齐 CI 前端/Rust/仓库卫生质量门。
- 清理 Git 中的 release 安装包和诊断 PDF。
- 为桌面 SQLite 增加显式 schema version 与幂等 migration 骨架。
- 新增发布前验收清单。

## Non-goals

- 不拆分 `DesktopRunService`。
- 不接入 `ai_resilience` 到主链路。
- 不改插件主链路消费方式。
- 不扩展 PPAP 平台业务功能。

## Acceptance

- 未授权请求不能订阅 SSE。
- 不存在、伪装或非法扩展图纸不能创建桌面项目。
- 输出目录不能指向文件、系统根、用户 home 根或仓库根等高风险目录。
- Tauri `open_output_dir`、`open_path`、`reveal_file` 都经过白名单校验。
- `MINOS_PLATFORM_AUTH_REQUIRED=1` 时 Platform API 没有 token 会拒绝请求。
- `SecretStr` 的 `model_dump()` 和 `model_dump_json()` 不输出明文。
- CI 定义包含 Python、前端 build、Rust check 和仓库卫生检查。
- release 安装包和诊断 PDF 不再被 Git 追踪。
- 桌面 SQLite 空库和旧库初始化后都有 `schema_version=1`。
- `docs/release-checklist.md` 可作为发布前执行清单。
