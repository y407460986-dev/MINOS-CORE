# Tasks: V3.3.0 Release Version Sync

## Define
- [x] /// 1. 意图：确认发布目标版本。输入：用户要求版本号为 `3.3.0`。输出：发布目标版本 `3.3.0`。验证：必改文件清单明确。

## Specify
- [x] /// 2. 意图：先写红灯测试。输入：当前发布源文件仍为 `3.2.1`。输出：`tests/test_release_version_sync.py` 目标版本改为 `3.3.0`，旧版本扫描增加 `3.2.1`。验证：测试先因旧版本残留失败。

## Implement
- [x] /// 3. 意图：同步源文件版本。输入：Python、npm、Cargo、Tauri、FastAPI、UI fallback 文件。输出：当前产品版本出口统一为 `3.3.0`。验证：`tests/test_release_version_sync.py` 通过。
- [x] /// 4. 意图：重新封装安装包。输入：`scripts/build_release.ps1`。输出：`MINOS-CORE_3.3.0_x64-setup.exe`。验证：构建 exit 0，产物复制到 target、release 和 dist/build/out。

## Verify
- [x] /// 5. 意图：聚焦回归。输入：版本同步、安装器、桌面 API、正式质量门测试。输出：pytest 通过记录。验证：`110 passed, 7 subtests passed`。
- [x] /// 6. 意图：产物可打开性检查。输入：三处安装包。输出：大小、SHA256、PE 头检查记录。验证：三处 SHA256 一致且 PE 头为 `MZ`。
- [x] /// 7. 意图：运行时版本烟测。输入：打包后的 sidecar。输出：`/api/health` 返回 `version=3.3.0`。验证：HTTP health 响应正确。
