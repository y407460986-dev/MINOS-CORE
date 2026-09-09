# Tasks: V3.2.1 Release Version Sync

## Define
- [x] /// 1. 意图：确认当前不再使用 `1.14.0`。输入：用户要求和现有版本审计。输出：发布目标版本 `3.2.1`。验证：必改文件清单明确。

## Specify
- [x] /// 2. 意图：锁定所有当前产品版本出口。输入：Python、npm、Cargo、Tauri、FastAPI、UI fallback 文件。输出：`tests/test_release_version_sync.py`。验证：测试先红，显示 `3.2.0` / `1.14.0` 残留。
- [x] /// 2.1. 意图：锁定安装器坏卸载路径回归。输入：用户截图、“Already Installed / Unable to uninstall!!”、生成的 `installer.nsi`、本机注册表证据。输出：`tests/test_desktop_installer_nsis.py`。验证：测试先因未接入自定义 NSIS template 和缺少坏卸载器保护失败。

## Implement
- [x] /// 3. 意图：同步源文件版本。输入：必改文件清单。输出：源文件当前产品版本均为 `3.2.1`。验证：不修改第三方依赖版本。
- [x] /// 4. 意图：刷新 lockfile。输入：`package.json`、`Cargo.toml`。输出：`package-lock.json` 和 `Cargo.lock` root app 版本保持 `3.2.1`。验证：`npm install --package-lock-only` 和 `cargo check` 通过。
- [x] /// 5. 意图：重新封装。输入：现有 sidecar/NSIS 构建脚本。输出：`MINOS-CORE_3.2.1_x64-setup.exe`。验证：安装包存在且可读。
- [x] /// 5.1. 意图：修复坏卸载路径导致安装器中止。输入：Tauri 默认 NSIS 模板和本机坏注册表证据。输出：自定义 `apps/desktop-tauri/src-tauri/nsis/installer.nsi` 与 `tauri.conf.json` 的 `bundle.windows.nsis.template`。验证：生成脚本中 `ExecWait` 前先检查 `$4\uninstall.exe`，缺失时跳过旧卸载记录并继续安装。
- [x] /// 5.2. 意图：防止发布脚本吞掉 native 命令失败或复制旧安装包。输入：`scripts/build_sidecar.ps1`、`scripts/build_release.ps1`、混有旧包的 NSIS 输出目录。输出：`Invoke-Native` fail-fast 和按当前 product/version 精确复制安装包。验证：`tests/test_desktop_installer_nsis.py` 脚本回归先红后绿。

## Verify
- [x] /// 6. 意图：运行聚焦回归。输入：版本同步、auth token、MinerU adapter 测试。输出：测试通过证据。验证：pytest exit 0。
- [x] /// 7. 意图：交付前审核。输入：源文件、安装包、文档和 diff。输出：残留版本扫描、UTF-8 读取、`git diff --check`。验证：只剩历史文档和第三方依赖版本命中可解释。
- [x] /// 8. 意图：验证安装器修复已进入最终安装包。输入：`npm run tauri:nsis`、生成的 `target\release\nsis\x64\installer.nsi`、交付安装包。输出：新安装包与 NSIS 脚本证据。验证：构建 exit 0、PE 头有效、SHA256 已记录。
