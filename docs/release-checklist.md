# MINOS-CORE 发布验收清单

本清单用于 v3.8.6 之后的内测包和小范围交付包。所有命令默认在仓库根目录执行。

状态说明：`[x]` 表示 2026-07-16 已取得本机或自动化证据；`[ ]` 表示仍需真实输入、Windows 发布 runner、正式证书或人工 Office 验收。

## 1. 代码与依赖检查

- [x] `python -m pytest tests -q -m "not real_api"`：1590 passed，8 skipped，101 subtests；coverage 82.85%。
- [x] `python -m unittest discover -s tests -v`：1004 tests OK，7 skipped。
- [x] `python -m pip check`
- [x] `python scripts/check_repo_hygiene.py`
- [x] `git diff --check`
- [x] `diff-cover coverage.xml --compare-branch=origin/main --fail-under=80`：84%。

## 2. 桌面端构建检查

- [x] `cd apps\desktop-tauri && npm ci`
- [x] `cd apps\desktop-tauri && npm audit --audit-level=high`：退出码 0，剩余 5 个中危传递依赖。
- [x] `cd apps\desktop-tauri && npm run build`
- [x] `cd apps\desktop-tauri\src-tauri && cargo check --locked`：Visual Studio Build Tools 17.14.36、MSVC 14.44.35207、Windows SDK 10.0.26100.0；退出码 0。

本机已安装最小 C++ Build Tools workload，`link.exe` 由 `VsDevCmd.bat` 开发者环境加载。

## 3. 主链路冒烟

本地 fixture、合成图纸、三表导出、OpenXML 和质量门回归已通过 104 项测试；以下条目仍要求真实脱敏图纸与真实模型调用。

- [ ] 生成或准备脱敏图纸输入样本。
- [ ] 跑通图纸识别到 PFD。
- [ ] 确认 PFD 后生成 PFMEA。
- [ ] 确认 PFMEA 后生成 CP。
- [ ] 质量门结果可读，失败项有明确人工处理建议。

## 4. 发布包生成

- [ ] 内测包：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_release.ps1 -Channel Internal`
- [ ] 内测包文件名包含 `internal-unsigned`，且只上传到内部 artifact，不创建正式 Release。
- [ ] 正式包由受保护的 `windows-release-signing` Environment 运行 `.github/workflows/windows-release.yml`。
- [ ] 正式构建缺少 `WINDOWS_CERT_PFX_BASE64` 或 `WINDOWS_CERT_PASSWORD` 时立即失败。
- [ ] 正式包：`Get-AuthenticodeSignature <installer>` 的 `Status` 必须为 `Valid`。
- [ ] 正式包使用 SHA256 digest 和 RFC3161 timestamp，记录 `Get-FileHash -Algorithm SHA256` 输出。
- [ ] 安装包只输出到 `dist\build\out`。
- [ ] `git ls-files release` 不列出 `.exe`、`.pdf` 或真实输入样本。
- [ ] 记录安装包文件名、大小和 SHA256。
- [ ] 签名、安装冒烟和卸载清理全部通过后，tag workflow 才创建 draft release。

## 5. 自动安装验收

- [ ] 内测包：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_installer.ps1 -Installer "dist/build/out/*internal-unsigned*.exe"`
- [ ] 正式包：同一命令增加 `-RequireSignature`。
- [ ] 安装包 glob 恰好匹配一个绝对路径；零个或多个均失败。
- [ ] NSIS `/S` 和 `/D=` 静默安装成功，主程序与 packaged sidecar 均存在。
- [ ] 已知测试 token 请求 `/api/health` 返回 200；无 token 请求返回 401。
- [ ] 按启动 PID 关闭进程，静默卸载后安装目录被清理。

## 6. 人工验收

- [ ] Windows 安装包可安装、启动、关闭、卸载。
- [ ] 桌面应用能启动 sidecar，健康检查返回正常。
- [ ] 未授权请求不能访问桌面 REST API。
- [ ] 未授权请求不能订阅 SSE 进度流。
- [ ] Tauri 打开路径只能打开 app 数据目录或用户选择过的路径。
- [ ] 导出的 Excel/xlsx 文件能用 Office 打开，无修复提示。
- [ ] 设置页 API Key 保存后不在响应、日志或界面回显明文。

## 7. 当前未关闭项

- Windows runner 生成正式包，并保留 Authenticode `Valid`、RFC3161 时间戳、SHA256、安装与卸载日志。
- 使用 Microsoft Office 打开真实导出 xlsx，确认没有修复提示。
- 运行受保护的真实 API acceptance；真实 JLV 第 4 条第(2)项 SC 已得到置信度 `0.82`、非零符号/文本框和有效裁剪引用，但修复引用契约后的三次 judge-only 仅有后两次 `judge_confirmed`，未达到连续三次 verifier 接受的稳定门槛，也没有 human confirmed，因此仍不关闭。
