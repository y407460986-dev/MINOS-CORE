# Proposal: V3.2.1 Release Version Sync

## Why
当前 MINOS-CORE 已经进入 `3.2.x` 发布线，不再使用 `1.14.0` 作为当前产品版本。但源文件中仍有多个运行时出口返回或显示 `1.14.0`，同时部分发布元数据仍停在 `3.2.0`。

这会导致安装包名称、桌面关于信息、Tauri bootstrap、FastAPI OpenAPI 元数据和 `/api/health` 版本不一致。用户本轮明确要求当前版本升级到 `3.2.1`，并重新封装 Windows 安装包。

## What
- 将 Python 包元数据、Tauri package、Tauri lock、Rust package、Cargo lock、Tauri 配置统一到 `3.2.1`。
- 将 Tauri bootstrap、工具栏/设置页 fallback、FastAPI app version、`/api/health` 返回值统一到 `3.2.1`。
- 新增回归测试锁定当前产品版本出口，防止 `1.14.0` 或 `3.2.0` 再次出现在发布源文件中。
- 重新构建 PyInstaller sidecar 和 Tauri NSIS 安装包，生成 `MINOS-CORE_3.2.1_x64-setup.exe`。

## Non-goals
- 不修改第三方依赖版本，例如 npm 依赖里的 `3.2.0` 或 Cargo 依赖里的 `1.14.0`。
- 不重写业务逻辑、OCR 逻辑、三表链路或 AI 配置。
- 不改历史文档中记录旧版本的章节，除非本轮 3.2.1 交付记录需要追加说明。

## Acceptance
- `tests/test_release_version_sync.py` 通过。
- Tauri 前端构建和 NSIS 封装通过。
- `release/MINOS-CORE_3.2.1_x64-setup.exe` 存在且大小合理。
- 源文件中的当前产品版本出口不再暴露 `1.14.0` 或 `3.2.0`。
