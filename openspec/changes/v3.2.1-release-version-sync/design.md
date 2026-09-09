# Design: V3.2.1 Release Version Sync

## Version Sources
当前产品版本由多个技术栈共同暴露，必须同步：

- Python 包：`pyproject.toml`
- npm 包：`apps/desktop-tauri/package.json` 与 root `package-lock.json`
- Rust 包：`apps/desktop-tauri/src-tauri/Cargo.toml` 与 `Cargo.lock`
- Tauri 配置和安装包名：`apps/desktop-tauri/src-tauri/tauri.conf.json`
- 运行时桌面版本：`apps/desktop-tauri/src-tauri/src/lib.rs`
- 后端 API 元数据和健康检查：`minos_desktop/api/app.py`、`minos_desktop/api/routes_health.py`
- UI fallback：`apps/desktop-tauri/src/App.tsx`、`apps/desktop-tauri/src/pages/SettingsPage.tsx`

## Guardrail
新增 `tests/test_release_version_sync.py`，只扫描当前发布源文件，不扫描历史文档、生成目录、第三方 lockfile 依赖版本。这样能防止误改依赖版本，也能防止 `1.14.0` 重新成为运行时输出。

## Packaging
使用 `scripts/build_release.ps1` 作为最终发布入口。该入口先执行 `scripts/build_sidecar.ps1` 生成 PyInstaller one-folder sidecar，再执行 `tauri build --ci --no-sign --bundles nsis`。Tauri 配置中的 `version=3.2.1` 决定 NSIS 安装包文件名。

PowerShell 的 `$ErrorActionPreference = "Stop"` 不会自动把所有 native 命令的非零退出码变成异常，所以发布脚本使用 `Invoke-Native` 显式检查 `$LASTEXITCODE`。NSIS 输出目录会保留旧版本安装包，因此发布脚本按 `productName` 和 `version` 拼出当前期望文件名，只复制 `MINOS-CORE_3.2.1_x64-setup.exe` 到 `release/` 和 `dist/build/out/`。

## Installer Upgrade Guard
用户安装时报 `Already Installed` / `Unable to uninstall!!` 的根因不是 3.2.1 payload 损坏，而是当前用户注册表里存在旧卸载记录：

- `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\MINOS-CORE`
- `InstallLocation = E:\MINOS-CORE`
- `UninstallString = "E:\MINOS-CORE\uninstall.exe"`

但 `E:\MINOS-CORE\uninstall.exe` 已不存在。Tauri 默认 NSIS 模板会在 `PageLeaveReinstall` 里读取旧 `UninstallString` 并直接 `ExecWait`，路径无效时弹出 `unableToUninstall` 并中止。

`installerHooks` 不能解决这个问题，因为 `NSIS_HOOK_PREINSTALL` 的执行点在安装 section 内，晚于重装选择页。当前修复使用 `bundle.windows.nsis.template` 接入仓库自有模板 `apps/desktop-tauri/src-tauri/nsis/installer.nsi`，只修改两处：

- 在旧 NSIS 卸载分支执行 `ExecWait` 前检查 `$4\uninstall.exe`；如果文件不存在，清掉错误状态并跳过旧卸载记录，继续安装。
- `RestorePreviousInstallLocation` 只在 `$4\uninstall.exe` 存在时恢复旧安装目录，避免把坏的 `E:\MINOS-CORE` 继续作为默认安装路径。
