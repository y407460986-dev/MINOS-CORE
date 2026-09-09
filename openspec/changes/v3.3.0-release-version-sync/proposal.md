# Proposal: V3.3.0 Release Version Sync

## Why
用户要求把当前 MINOS-CORE 发布版本提升到 `3.3.0`，并重新封装最新 Windows 安装包。当前发布源文件仍停在 `3.2.1`，如果不统一同步，安装包文件名、桌面版本角标、FastAPI metadata 和 `/api/health` 会继续暴露旧版本。

## What
- 将 Python 包元数据、Tauri package、Tauri lock、Rust package、Cargo lock、Tauri 配置统一到 `3.3.0`。
- 将 Tauri bootstrap、工具栏/设置页 fallback、FastAPI app version、`/api/health` 返回值统一到 `3.3.0`。
- 扩展版本同步回归测试，禁止当前发布源文件继续暴露 `1.14.0`、`3.2.0` 或 `3.2.1`。
- 重新构建 PyInstaller sidecar 和 Tauri NSIS 安装包，生成 `MINOS-CORE_3.3.0_x64-setup.exe`。

## Non-goals
- 不修改第三方依赖版本，例如 npm lockfile 依赖里的 `3.2.0` 或 Cargo 依赖里的 `1.14.0`。
- 不改历史文档中记录旧版本的事实。
- 不修改三表业务逻辑、OCR 逻辑或 AI 配置。

## Acceptance
- `tests/test_release_version_sync.py` 先红后绿。
- 发布相关和正式质量门聚焦 pytest 通过。
- `scripts/build_release.ps1` 生成 `release/MINOS-CORE_3.3.0_x64-setup.exe`。
- 目标、release、dist 三处安装包 SHA256 一致，PE 头为 `MZ`。
- 打包后的 sidecar `/api/health` 返回 `version=3.3.0`。
