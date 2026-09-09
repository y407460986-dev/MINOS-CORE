# Design: V3.3.0 Release Version Sync

## Version Sources
当前产品版本由多个技术栈共同暴露，必须同步：

- Python 包：`pyproject.toml`
- npm 包：`apps/desktop-tauri/package.json` 与 `apps/desktop-tauri/package-lock.json`
- Rust 包：`apps/desktop-tauri/src-tauri/Cargo.toml` 与 `apps/desktop-tauri/src-tauri/Cargo.lock`
- Tauri 配置和安装包名：`apps/desktop-tauri/src-tauri/tauri.conf.json`
- 运行时桌面版本：`apps/desktop-tauri/src-tauri/src/lib.rs`
- 后端 API 元数据和健康检查：`minos_desktop/api/app.py`、`minos_desktop/api/routes_health.py`
- UI fallback：`apps/desktop-tauri/src/App.tsx`、`apps/desktop-tauri/src/pages/SettingsPage.tsx`

## Guardrail
`tests/test_release_version_sync.py` 只扫描当前发布源文件，不扫描历史文档、生成目录、第三方 lockfile 依赖版本。这样可以防止误改依赖版本，同时阻止旧产品版本重新成为运行时输出。

## Packaging
使用 `scripts/build_release.ps1` 作为最终发布入口。该入口先执行 `scripts/build_sidecar.ps1` 生成 PyInstaller one-folder sidecar，再执行 `tauri build --ci --no-sign --bundles nsis`。Tauri 配置中的 `version=3.3.0` 决定 NSIS 安装包文件名。

最终需要同时核对：

- `apps/desktop-tauri/src-tauri/target/release/bundle/nsis/MINOS-CORE_3.3.0_x64-setup.exe`
- `release/MINOS-CORE_3.3.0_x64-setup.exe`
- `dist/build/out/MINOS-CORE_3.3.0_x64-setup.exe`

三处文件应大小一致、SHA256 一致，并且前两个字节为 `MZ`。
