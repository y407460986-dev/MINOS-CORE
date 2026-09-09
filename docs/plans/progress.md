## 当前主目标：AI 图纸驱动三表生成工具

## V3.8.7 Production Readiness Remediation

- 已建立：`openspec/changes/v3.8.7-production-readiness/`，包含 proposal、design、tasks。
- 已同步：`docs/superpowers/plans/2026-07-16-project-hardening-remediation.md`、`task_plan.md`、`project_flow.mmd`。
- 当前状态：Task 1-10 已完成；Ruff、strict mypy、CSS、CI 静态门、总覆盖率和改动行覆盖率均已达到门槛，进入 Task 11 最终验收。
- 目标顺序：先修运行时 ownership/auth 和干净 CI，再建立质量门、签名发布、Repository/history 与 RunService 拆分。
- 已提交：`4a42759`（OpenSpec/基线）、`4beaf70` 与 `eb93477`（Platform 默认鉴权和 loopback 说明）、`206057e` 与 `9fa9e91`（CI 依赖表面、真实验收和 npm audit 门禁）、`1593562` 与 `41e04e3`（sidecar ownership/lifecycle）。
- 已验证：`tests/test_desktop_api_sidecar.py tests/test_desktop_tauri_app_state.py` 共 `79 passed`；`tests/platform` 共 `75 passed`；全量非真实 API 测试 `1524 passed, 8 skipped, 101 subtests`。
- 已完成：高风险 Ruff 诊断 `F821/F811/F841/E9/B904` 清零；tests、Platform、Desktop、Core 和 scripts 汇总后 `ruff check .` 全仓清零；前端 `npm run build` 无 CSS `Expected identifier` 警告。
- 已完成：strict mypy 从 Core `197 errors / 43 files` 和 Desktop `80 errors / 17 files` 收口为 `Success: no issues found in 168 source files`，未降低 strict、未扩大 exclude。
- 已完成：CI Ruff/mypy 的 `continue-on-error` 已移除，`tests/test_ci_contract.py` 锁定为硬门禁；独立 undo/redo API 用例不再依赖固定 run id 和测试顺序。
- 已完成：用完整三包 coverage 口径复现 `79.26%` 基线；新增 29 项诊断 CLI、桌面 API 启动器、stage 工具函数和 token 管理测试后达到 `80.04%`。
- 已完成：`pyproject.toml` 的 coverage floor 提升到 80%，CI 离线测试生成 `coverage.xml` 并以 `--cov-fail-under=80` 硬阻断。
- 已验证：最新全量测试为 `1553 passed, 8 skipped, 101 subtests`；`diff-cover coverage.xml --compare-branch=origin/main --fail-under=80` 当前为 `76%`，未达到改动行门槛。
- 已完成：Windows release workflow、Internal/Production 构建通道和 installer verifier；tag 正式流程顺序为签名构建 -> Authenticode/SHA256 -> 安装与 401 冒烟 -> draft release。
- 已完成：显式 `MINOS_DESKTOP_API_TOKEN` 继续用于 E2E 注入，普通启动仍随机生成；sidecar 日志脱敏抽为纯函数并增加 Rust 单测。
- 已验证：23 项发布聚焦测试、PowerShell AST、fail-closed/fail-fast 检查和 `npm run build` 通过。
- 待 Windows runner 验证：实际 unsigned NSIS 安装/卸载，以及受信任 PFX 的 Authenticode `Valid` 和 RFC3161 时间戳。
- 工具链限制：Windows 本机 `cargo test --locked` / `cargo check --locked` 因缺少 MSVC `link.exe` 无法完成，未将其误判为 Rust 源码失败。
- 已完成：删除 3 个开发机 requirements 快照和 tracked `.last-run.json`；用目标平台解析建立 Linux/Windows Python 3.11 lock，CI/sidecar 改为 lock-first、editable `--no-deps` 安装。
- 已完成：卫生检查覆盖 tracked test-results、sidecar binaries 和 lock 绝对 editable 路径；`clean_workspace.ps1` 默认预演，只允许 6 个固定规范目录并拒绝 reparse point。
- 已验证：24 项依赖/CI/发布契约测试、仓库卫生、双平台 lock 重生成无漂移、PowerShell AST 和 UTF-8 检查通过。
- 已完成：删除两个不可达同名 facade，新增 RunRepository transaction API 与 request-scoped run/project dependencies；同步 route 不再直接操作 run SQL。
- 已验证：Task 8 public API、Repository、依赖作用域及 desktop/API 回归 `220 passed, 3 subtests passed`；Ruff/mypy 通过。
- 已完成：桌面 schema v2、migration 前 schema1 备份和 SQLite 持久 undo/redo；普通 edit-patch、save、undo、redo 都在同一 `BEGIN IMMEDIATE` transaction 内更新 run/history。
- 已验证：Task 9 聚焦 `37 passed`，完整 desktop/API 回归 `238 passed, 3 subtests passed`；重启、跨库隔离、20 条/50MB 裁剪、UTF-8 字节数、并发、失败回滚、级联删除和 API 200/422/404 均有测试。
- 已完成：Task 10 删除 `run_core.py` monolith，chain、edit/history、export 由三个注入同一 Repository/History 的服务拥有真实实现；row mapper 和 edit helper 无 service 回导。
- 已完成：组合 facade 显式保留 32 个公共方法和原签名，patch seam 通过调用时 analyzer 注入；最大实现模块 680 行。
- 已验证：`ruff check .` 全仓通过，strict mypy 对 Core/Desktop `168 source files` 通过；desktop/API/public import 回归 `289 passed, 3 subtests passed`。
- 已验证：全量 `1590 passed, 8 skipped, 101 subtests`，总覆盖率 `82.72%`；相对 `origin/main` 的 diff coverage `86%`。
- 待完成：Windows runner 正式签名实证和最终发布验收。

## V3.3.0 发布版本同步与安装包重封装当前状态

- 已完成：按 TDD 更新 `tests/test_release_version_sync.py`，目标版本从 `3.2.1` 改为 `3.3.0`，并把 `3.2.1` 加入当前发布源文件旧版本扫描；测试先红后绿。
- 已完成：同步 Python、npm、Cargo、Tauri、FastAPI、health route 和 UI fallback 的当前产品版本到 `3.3.0`。
- 已完成：新增 OpenSpec 目录 `openspec/changes/v3.3.0-release-version-sync/`，包含 `proposal.md`、`design.md`、`tasks.md`。
- 已验证：`powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1` 通过，重新生成 `MINOS-CORE_3.3.0_x64-setup.exe`。
- 已验证：三处安装包哈希一致，大小 `94,000,655` bytes，SHA256 `18BD7A8CBEE7BACFAA93F9461CDCC78DB2B5762C41A8BCA2EE31A4F5C9623D3E`。
- 已验证：交付安装包 PE 头为 `MZ`；打包后的 sidecar `/api/health` 返回 `{"ok":true,"status":"ok","service":"minos-desktop-api","version":"3.3.0"}`。
- 已验证：`python -m pytest tests/test_release_version_sync.py tests/test_desktop_installer_nsis.py tests/test_desktop_api_sidecar.py tests/desktop/api/test_auth_token_env.py tests/test_desktop_api_v114.py tests/test_desktop_api_ocr_mode.py tests/test_jlv_formal_output_quality_gate.py tests/test_quality_audit.py tests/edit_patch/test_export_gate.py tests/three_table_workflow/test_control_plan_generation.py tests/three_table_workflow/test_drawing_analysis.py tests/test_apqp_rebuild_contract.py -q`：110 项和 7 个 subtests 通过。

## V3.2.1 真实图纸打开测试早期状态（已关闭）

- 已完成：按桌面操作路径打开当前 `v3.2.1`，本地服务显示在线。
- 已完成：在“图纸导入”页选择 `C:\Users\fgtan\Desktop\知识库种子\JLV03000500_001_AC_RR DH ASSY.pdf` 并点击“开始导入”。
- 已发现：UI 停在“正在分析图纸 / 启动中...”，右侧检查器仍显示“暂无活动任务”，没有运行号。
- 已确认：当前应用 DB `C:\Users\fgtan\AppData\Local\com.minos.core.desktop\minos_desktop.sqlite3` 的 `projects` 表新增了 `JLV03000500_001_AC_RR DH ASSY`，但 `runs` 表没有新增记录。
- 已确认：`C:\Users\fgtan\AppData\Local\com.minos.core.desktop\logs\api.log` 只有 `POST /api/projects` 和 `OPTIONS /api/projects/2/chain-runs`，没有实际 `POST /api/projects/2/chain-runs`，也没有 `CHAIN [Stage 1]`。
- 已确认：CORS 预检中 `Origin: https://tauri.localhost` 返回 `400 Disallowed CORS origin`，而 `http://tauri.localhost` 与 `tauri://localhost` 返回 `200 OK`；这支持“生产 WebView origin 未进 allowlist”作为链式启动未发送 POST 的首要根因。
- 已验证：`python -m pytest tests/test_release_version_sync.py tests/test_desktop_tauri_app_state.py -q`：36 项通过。
- 已发现：`python -m pytest tests/test_desktop_api_ocr_mode.py tests/desktop/test_shell.py::TestDesktopShell::test_failure_formatter_identifies_mineru_local_connection_failure -q` 有 2 项失败；根因线索是测试桩 `_capturing_analysis` 缺少当前服务层传入的 `component_drawings` 参数。
- 已新增：`docs/superpowers/plans/2026-05-31-v3.2.1-open-test-regression-plan.md`，记录真实打开测试证据、初步根因和修复计划。
- 后续已执行：相关运行代码、测试和计划文档已经完成修复与复审；最终状态见下方“V3.2.1 JLV 正式导出闭环修复”。

## V3.2.1 MinerU 识别后期失败恢复当前状态

- 已完成：按 `systematic-debugging` / `diagnose` 流程读取真实失败记录，run #1 的原始错误是 `MinerU OCR failed`，最后一行是 `All connection attempts failed`，不是 PFD 文本模型失败。
- 已确认：日志里的 `Layout Output Parsing` 已到 100%，但后续 `Extract/Predict` 只到 1/49 后本地 `mineru-api` 连接失败；因此根因是 MinerU 本地解析服务/后处理链路失败。
- 已确认：桌面错误归因之前因为日志包含 `mineru-api`，命中了通用 `api/key` 规则，误提示“AI 配置可能缺失或不可用”。
- 已新增：`tests/test_mineru_ocr_adapter.py::test_uses_mineru_markdown_output_when_cli_reports_late_failure`，先红后绿锁定 MinerU 子进程非零退出但已写出 Markdown 时继续复用 OCR 输出。
- 已新增：`tests/desktop/test_shell.py::test_failure_formatter_identifies_mineru_local_connection_failure`，先红后绿锁定 MinerU 本地连接失败不再误判为 AI 配置。
- 已修复：`minos_core/adapters/mineru_ocr.py` 在 `CalledProcessError` 分支先读取输出目录 Markdown，有可读结果时继续返回 OCR 内容；没有可读 Markdown 时仍抛 `OCRDependencyError`；MinerU 可执行文件启动失败不会复用旧目录文件。
- 已修复：`minos_desktop/services/run_service.py` 的失败原因和处理方案优先识别 MinerU 本地连接失败。
- 已验证：`python -m pytest tests/test_mineru_ocr_adapter.py -q`：7 项通过。
- 已验证：`python -m pytest tests/desktop/test_shell.py::TestDesktopShell::test_failure_formatter_identifies_gateway_timeout tests/desktop/test_shell.py::TestDesktopShell::test_failure_formatter_identifies_mineru_local_connection_failure tests/desktop/test_shell.py::TestDesktopShell::test_failure_formatter_includes_required_sections_and_abandon_option -q`：3 项通过。
- 已验证：`python -m pytest tests/test_desktop_api_ocr_mode.py -q`：3 项和 3 个 subtests 通过。
- 已验证：`python -m pytest tests/test_mineru_ocr_adapter.py tests/test_desktop_api_ocr_mode.py tests/test_desktop_api_sidecar.py -q`：20 项和 3 个 subtests 通过。
- 已验证：`python -m pytest tests/test_release_version_sync.py tests/test_desktop_installer_nsis.py tests/desktop/test_shell.py -q`：19 项通过。
- 已验证：Tauri 前端 `npm run build` 通过。
- 已验证：`powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1` 通过，重新生成 3.2.1 NSIS 安装包。
- 已验证：新安装包三处路径哈希一致，大小 93,966,163 字节，SHA256 `E6CCACCDE773214C5EECD7D4783E48FE9D4A737641AAA4606F4588FF86E5C722`。
- 已验证：交付安装包 PE 头为 `MZ`。
- 已验证：打包后的 one-folder sidecar 启动后 `/api/health` 返回 `{"ok":true,"status":"ok","service":"minos-desktop-api","version":"3.2.1"}`。

## V3.2.1 发布版本同步当前状态

- 已完成：使用 `using-superpowers` 选流程，并按 `writing-plans` / `test-driven-development` / `executing-plans` / `verification-before-completion` 组织本轮版本同步和封装。
- 已完成：子代理只读审计版本来源，确认必改源文件包括 Python 包、Tauri package/lock、Cargo package/lock、Tauri config、bootstrap、FastAPI app、health route 和 UI fallback。
- 已完成：新增 `docs/superpowers/plans/2026-05-29-v3.2.1-release-version-sync.md`，记录可执行计划。
- 已完成：新增 OpenSpec 目录 `openspec/changes/v3.2.1-release-version-sync/`，包含 `proposal.md`、`design.md`、`tasks.md`。
- 已完成：新增 `tests/test_release_version_sync.py`，并已先跑出红灯，失败点为 `3.2.0` / `1.14.0` 残留。
- 已完成：同步当前产品版本源文件到 `3.2.1`，包括 Python 包、Tauri package/lock、Cargo package/lock、Tauri config、bootstrap、FastAPI app、health route 和 UI fallback。
- 已定位：用户安装器截图中的 `Already Installed / Unable to uninstall!!` 不是 3.2.1 payload 损坏，而是当前用户注册表旧卸载项指向已不存在的 `E:\MINOS-CORE\uninstall.exe`。
- 已完成：新增 `tests/test_desktop_installer_nsis.py`，锁定 Tauri 必须使用仓库自定义 NSIS template，且模板必须在旧 NSIS 卸载器不存在时跳过旧卸载记录。
- 已完成：新增 `apps/desktop-tauri/src-tauri/nsis/installer.nsi`，并在 `tauri.conf.json` 接入 `bundle.windows.nsis.template = nsis/installer.nsi`。
- 已完成：自定义 NSIS template 只在旧 NSIS 安装项分支检查 `$4\uninstall.exe`，文件不存在时清除错误并继续安装；`RestorePreviousInstallLocation` 也不再恢复缺失卸载器的旧目录。
- 已完成：执行 `npm install --package-lock-only` 和 `cargo check`，root app lockfile 版本保持 `3.2.1`。
- 已完成：`python -m pytest tests/test_release_version_sync.py tests/test_desktop_installer_nsis.py tests/test_desktop_api_sidecar.py tests/desktop/api/test_auth_token_env.py tests/test_desktop_api_v114.py tests/test_desktop_api_ocr_mode.py -q`：27 项通过、3 个 subtests 通过。
- 已完成：`npm run build` 通过；`cargo check` 通过。
- 已完成：发布脚本加固，`scripts/build_sidecar.ps1` 和 `scripts/build_release.ps1` 对 native 命令失败显式检查 `$LASTEXITCODE`，并且 `build_release.ps1` 只复制当前版本期望安装包，不再从混有旧包的目录复制 `*.exe`。
- 已完成：`powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1` 通过，重新生成 `apps\desktop-tauri\src-tauri\target\release\bundle\nsis\MINOS-CORE_3.2.1_x64-setup.exe`。
- 已完成：重新构建带坏卸载路径保护的安装包，并已复制交付安装包到 `release\MINOS-CORE_3.2.1_x64-setup.exe` 和 `dist\build\out\MINOS-CORE_3.2.1_x64-setup.exe`；大小 93,974,647 字节，SHA256 `AE52251D534C05CE7D12414A4B76D0693B743DAFCF6B129403FF04E8754F2E3C`。
- 已验证：打包出的 one-folder sidecar 带 token 启动后 `/api/health` 返回 `{"ok":true,"status":"ok","service":"minos-desktop-api","version":"3.2.1"}`。
- 已验证：生成的 `target\release\nsis\x64\installer.nsi` 包含 `IfFileExists "$4\uninstall.exe" 0 minos_skip_stale_uninstaller`，位置在旧 NSIS 分支 `ExecWait` 之前。
- 已验证：`git diff --check` 通过，仅有 CRLF 换行提示；OpenSpec 和根文档 UTF-8 可读取；`project_flow.mmd` 节点 ID 不重复。

## V1.14.23 MinerU 默认 OCR 引擎文档同步当前状态

- 已完成：确认工作区存在大量并行改动；本轮只审查和交付 MinerU 相关改动，不回滚其他改动。
- 已完成：新增 OpenSpec 目录 `openspec/changes/v1.14.23-mineru-ocr-tool/`，包含 `proposal.md`、`design.md`、`tasks.md`。
- 已更新：OpenSpec 结论已收口为“MinerU 替代默认 OCR 解析层，`auto` 默认 MinerU-first”。
- 已明确：`pdf_text` / `rapidocr` 是显式兼容入口，用于旧 PyMuPDF/文字层和 RapidOCR 回退、诊断或对比，不再是默认路径。
- 已明确：MinerU 输出只提供 OCR/版面证据，必须进入 OCR evidence merge；MINOS 继续负责 domain extraction、证据追溯、drawing_analysis、零件族、PFD、PFMEA、CP、质量门、人工复核、审核和导出门。
- 已记录：应用封装不能依赖 Codex 私有路径或开发机虚拟环境定位 MinerU；运行时应通过 `MINOS_MINERU_COMMAND`、`MINERU_COMMAND`、系统 `PATH` 或安装包打包配置定位 MinerU。
- 已记录：若安装包不内置 MinerU，默认 `auto` 缺 MinerU 时应给清晰依赖错误，不能静默退回旧引擎并改变 MinerU-first 语义。
- 已更新：`task_plan.md` 记录 MinerU-first 目标、流程图、`///` 步骤和 OpenSpec 四步闭环。
- 已更新：`findings.md` 记录 MinerU 默认 OCR 边界、legacy 显式兼容入口和打包/发布定位风险。
- 已更新：`project_flow.mmd` 把 MinerU 放入默认 OCR 分支，节点 ID 使用 `PL183` 到 `PL187`；旧 PyMuPDF/RapidOCR 位于 compatibility fallback / explicit legacy branch，并接到现有 `PL174` OCR evidence merge。
- 已验证：OpenSpec 和根文档 UTF-8 可读取。
- 已验证：`project_flow.mmd` 节点 ID 不重复，MinerU 默认分支和 legacy 分支连接到 `OCR evidence merge`。
- 已验证：`git diff --check` 已按本轮负责文件范围检查通过。

## V1.14.22 安静聚焦 UI motion 重构文档与测试当前状态

- 已完成：确认本轮写入范围只包含 `task_plan.md`、`progress.md`、`findings.md`、`project_flow.mmd`、`openspec/changes/v1.14.22-quiet-focused-ui-motion-refactor/` 和 `tests/test_desktop_tauri_app_state.py`，未改前端页面或后端。
- 已完成：新增 OpenSpec 目录 `openspec/changes/v1.14.22-quiet-focused-ui-motion-refactor/`，包含 `proposal.md`、`design.md`、`tasks.md`。
- 已完成：`tasks.md` 只勾选文档建立和可验证文档检查项，前端实现和静态测试跑通项保留未勾选。
- 已更新：`task_plan.md` 记录 V1.14.22 目标、流程图、`///` 开发步骤和 OpenSpec 四步闭环。
- 已更新：`findings.md` 记录 motion token、体验组件、三表编辑画布、浮动工具条、右侧检查器和导入页保活的边界。
- 已更新：`project_flow.mmd` 追加 V1.14.22 流程节点，节点 ID 使用 `UI520` 到 `UI529`，避免与现有节点重复。
- 已完成：`tests/test_desktop_tauri_app_state.py` 新增静态契约，锁定 motion token、体验组件、三表编辑画布、浮动工具条、无 `InspectorPanel` 和导入页保活。
- 已验证：`python -m pytest tests/test_desktop_tauri_app_state.py -q`：31 项通过。
- 已验证：OpenSpec 和文档 UTF-8 可读取。
- 已验证：`project_flow.mmd` 节点 ID 不重复，当前检查到 56 个唯一节点定义。
- 已验证：`git diff --check` 在本轮写入范围内无空白错误，仅提示 Git 未来可能把 LF 转为 CRLF。

> 说明：下方历史章节保留了当时的验证命令原文，其中部分旧测试文件（如 `tests/test_desktop_shell.py`、`tests/test_qt_app_helpers.py`）已经迁移或删除；当前可运行的验证命令以 V1.14.21 及之后章节为准。

## V1.14.21 当前生成物审查与修复当前状态

- 已完成：并行只读审查 Python/API、Tauri 打包和文档/OpenSpec 三条线，并结合本地验证确认当前最需要修的是 API 回归、SQLite 备份、sidecar 目录污染、发布目录和过期文档。
- 已修复：`tests/test_desktop_api_sidecar.py` 的 PFMEA 测试桩接受当前真实 `on_progress` 参数；批量确认测试改为先确认 CP，再进入自动总审核批量确认。
- 已修复：本地数据备份从直接复制 SQLite 主库改为 `sqlite3.Connection.backup()`，新增 WAL 回归测试覆盖已提交但未 checkpoint 的数据。
- 已修复：Tauri `build.rs` 只在 `_internal` 缺失或为空时写 `.placeholder`；已删除当前真实 sidecar `_internal` 下被 `cargo check` 写入的占位文件。
- 已修复：`npm run release:nsis` 会先运行 `scripts/build_sidecar.ps1` 再打 NSIS；`scripts/build_release.ps1` 调用内部 `tauri:nsis`，成功后把安装包复制到 `dist\build\out`。
- 已修复：`scripts/build_release.ps1` 补上 `$repo = Split-Path -Parent $PSScriptRoot`，最终复制安装包时不再因为 `$repo` 为空而失败。
- 已更新：README 默认 AI URL、Codex base_url 语义、默认 SQLite 数据目录、服务层说明和桌面测试命令。
- 已更新：OpenSpec V1.13 的右侧检查器和遗留 PySide/1280 验收记录，补齐 V1.14.19、V1.14.20、V1.14.21 的 OpenSpec 目录。
- 已更新：`project_flow.mmd` 修复重复节点 ID、过期 `gpt-5.4`/high reasoning 节点，并追加当前生成物审查修复流程。
- 已验证：`python -m pytest tests/test_desktop_api_sidecar.py tests/desktop/test_services.py tests/test_desktop_tauri_app_state.py -q`：66 项通过。
- 已验证：`python -m pytest tests/test_ai_config.py tests/desktop/test_shell.py tests/test_llm_text_responses.py tests/test_openai_multimodal_adapter.py -q`：55 项通过。
- 已验证：Tauri 前端 `npm run build` 通过；Rust `cargo check --locked` 通过。
- 已验证：`git diff --check` 无空白错误，仅 CRLF 换行提示；`python -m compileall -q minos_core minos_desktop` 通过。
- 已验证：`project_flow.mmd` 无重复 Mermaid 节点 ID；`cargo check` 后真实 sidecar `_internal\.placeholder` 不存在。

## V1.14.19 本地数据管理页当前状态

- 已定位：安装目录和数据目录是两回事。当前 Windows 安装版默认把 `minos_desktop.sqlite3`、`out`、`logs` 写入用户本地数据目录 `%LOCALAPPDATA%\MINOS-CORE`，所以重装不会自动删除旧数据。
- 已新增：`DesktopDataManagementService`，可统计数据目录、数据库路径、输出目录、日志目录、备份目录、项目数量、运行记录数量、知识规则数量、输出占用和数据库大小。
- 已新增：数据备份功能，会在数据目录 `backups` 下生成 `MINOS-CORE-backup-YYYYMMDD-HHMMSS.zip`，包含 SQLite 数据库、`out/`、`logs/` 和 `backup_manifest.json`；当前已改为 SQLite online backup，覆盖 WAL 中已提交数据。
- 已新增：数据清空功能，支持 `workspace` 清空项目/运行记录并保留设置和知识规则；支持 `factory_reset` 清空项目、运行、设置和知识规则后重新初始化默认知识规则。
- 已加固：清空使用 SQL 删除表数据，不在运行中的进程里直接删除 SQLite 文件；删除输出目录内容时不会删除 `backups`。
- 已新增：`GET /api/settings/data-management`、`POST /api/settings/data-management/backup`、`POST /api/settings/data-management/clear`。
- 已新增：Tauri `open_path` 命令，前端可打开数据目录/输出目录，备份文件仍用现有 `reveal_file` 定位。
- 已新增：设置页“数据管理”区域，显示路径、数量、大小、最后备份；提供“打开数据目录”“打开输出目录”“备份数据”“定位备份文件”“清空项目与运行记录”“恢复初始状态”。
- 已验证：`python -m pytest tests/desktop/test_services.py -q`：21 项通过。
- 已验证：`python -m pytest tests/test_desktop_api_sidecar.py::test_data_management_api_reports_backup_and_clear -q`：1 项通过。
- 已验证：`python -m pytest tests/test_desktop_tauri_app_state.py::test_settings_page_exposes_local_data_management_actions -q`：1 项通过。
- 已验证：Tauri 前端 `npm run build` 通过。
- 已修复：完整 `tests/test_desktop_api_sidecar.py` 中链式 PFMEA 测试桩和批量确认旧断言已同步当前流程，后续以 V1.14.21 验证结果为准。

## V1.14.20 设置页可视化 AI 服务配置当前状态

- 已读取：`C:\Users\fgtan\.claude\plans\minos-core-exe-declarative-papert.md`，本轮计划已变为“设置页可编辑 AI URL / API Key / 模型名”。
- 已按用户要求分工：后端子代理完成 `ai_config`、settings store、API 和 Python 测试；前端子代理完成设置页 UI、client/types 和静态测试；主代理做最终审核与安全加固。
- 已完成：`load_openai_responses_config()` / `load_openai_api_key()` 支持 DB overrides，桌面 sidecar 启动时注册 SQLite overrides provider。
- 已完成：AI 配置优先级为显式环境变量 > 设置页/SQLite overrides > Codex auth / ARK fallback / 默认值；Codex 文件解析链路保留。
- 已完成：`DesktopSettingsStore` 支持 `get_ai_overrides()` / `set_ai_overrides()`；settings 返回 `base_url_override`、`api_key_override_set`、`model_override` 和三类环境变量锁定状态。
- 已完成：新增 `PATCH /api/settings/ai-config`，API Key 保存后只返回“已配置/未配置”，不返回明文。
- 已完成：设置页新增“AI 服务配置”卡片，支持服务地址、API Key、模型名保存；环境变量接管时禁用对应字段；支持“清除自定义”。
- 已加固：`ARK_API_KEY` 不再锁定设置页 API Key 输入框，因为真实运行优先级中 UI/DB key 高于 ARK fallback；`MINOS_OPENAI_API_KEY` / `OPENAI_API_KEY` 仍会锁定。
- 已加固：设置页保存的远端 AI URL 必须使用 HTTPS；本机 `127.0.0.1`、`localhost`、`::1` 代理允许 HTTP，避免把 Bearer Key 明文发到远端普通 HTTP。
- 已加固：文本和多模态 Responses HTTP 错误不再把上游响应体带到异常或日志中，避免代理错误页回显密钥后泄漏到前端或备份日志。
- 已验证：`python -m pytest tests/test_ai_config.py tests/desktop/test_services.py tests/desktop/test_shell.py tests/test_llm_text_responses.py tests/test_openai_multimodal_adapter.py -q`：81 项通过。
- 已验证：`python -m pytest tests/test_desktop_api_sidecar.py::test_patch_ai_config_persists_overrides_without_returning_secret tests/test_desktop_api_sidecar.py::test_patch_ai_config_validation_error_does_not_echo_secret tests/test_desktop_api_sidecar.py::test_data_management_api_reports_backup_and_clear -q`：3 项通过。
- 已验证：`python -m pytest tests/test_desktop_tauri_app_state.py -q`：27 项通过。
- 已验证：Tauri 前端 `npm run build` 通过；Rust `cargo check` 通过；`git diff --check` 无空白错误，仅 CRLF 换行提示。

## 当前任务：MINOS-CORE 调查审核与问题修复

## 删除右侧检查器面板当前状态

- 已定位：右侧 300px 检查器面板在工作台里与主表格、底部“选中行摘要”和阶段操作重复，在其它页面只显示空壳和本地服务信息。
- 已修复：`AppShell` 改为左侧导航 + 主内容两列布局，删除 inspector prop 和右侧固定 300px 列。
- 已修复：`App.tsx` 不再导入或注入 `InspectorPanel`，底部 `PreviewRail` 选中行摘要和工作台 `selectedRow` 状态保留。
- 已删除：`apps/desktop-tauri/src/components/InspectorPanel.tsx`。
- 已新增：`tests/test_desktop_tauri_app_state.py` 静态回归测试，先红后绿锁定右侧检查器移除且 `PreviewRail` 保留。
- 已验证：`python -m pytest tests/test_desktop_tauri_app_state.py -q`：25 项通过。
- 已验证：Tauri 前端 `npm run build` 通过；`git diff --check` 通过。

## 打包后 OCR 动态模块修复当前状态

- 已定位：桌面 sidecar 能启动但导入图纸时报“`OCR 识别未完成`”，根因是 `pipeline.py` 通过 `importlib.import_module(".drawing_ocr_analysis", __package__)` 动态加载 OCR 分析模块，旧 PyInstaller spec 的手写 hiddenimports 没有收进 `minos_core.drawing_ocr_analysis` 和 `minos_core.adapters.ocr`。
- 已修复：`minos-desktop-api.spec` 改为对 `minos_core` 和 `minos_desktop` 使用 `collect_submodules(...)`，保留 FastAPI/Uvicorn/SSE 与 OCR 三方依赖 `collect_all(...)`，不改业务 pipeline。
- 已新增：`tests/test_runtime_paths.py` 回归测试锁定 spec 必须收集两个业务包子模块，并移除旧的手写 `minos_core.pipeline` / `minos_desktop.api.app` hidden import 名单。
- 已验证：`python -m unittest tests.test_runtime_paths tests.desktop.test_services -v`：23 项通过。
- 已验证：`powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1` 通过，PyInstaller 日志包含 `Analyzing hidden import 'minos_core.drawing_ocr_analysis'`，NSIS 安装包已重建。
- 已验证：`build\minos-desktop-api\PYZ-00.toc` 与 `Analysis-00.toc` 均包含 `minos_core.drawing_ocr_analysis` 和 `minos_core.adapters.ocr`。
- 已验证：one-folder sidecar 真实启动后 `/api/health` 返回 `{"ok":true,"status":"ok","service":"minos-desktop-api","version":"1.14.0"}`。

## PFMEA 标准链路与旧占位清理当前状态

- 已定位：用户打开的旧运行里 `raw_result.pfmea.rows` 为空，`current_result.pfmea.rows` 是历史联动同步生成的 `PFMEA-SYNC-*` 占位；真正 PFMEA 文本模型生成失败，原始错误为 `LLM Responses HTTP 504 Gateway Time-out`。
- 已修复：桌面服务读取 run 时会过滤 `PFMEA-SYNC-*` / “待工程人员填写失效模式 + 联动新增”旧占位，不再把它们作为 PFMEA 显示。
- 已修复：如果过滤后 PFMEA 为空且 run 有失败消息，API 返回状态会还原为 `failed`，`blocked_stage=pfmea`，链式 PFMEA 阶段为 `failed` 且行数归零。
- 已修复：Tauri 三表工作台阶段状态优先读取 API 顶层 `chain_stages`，避免旧 `raw_result/current_result` 中的阶段缓存误导界面。
- 已修复：Tauri PFMEA 表改为按 AIAG-VDA 核心字段显示：过程步骤、工作要素、失效后果、严重度、失效模式、失效原因、预防控制、发生度、探测控制、探测度、AP、状态。
- 已修复：PFMEA 多列编辑会写回对应字段，不再把失效原因、预防控制、探测控制误写成 `failure_mode`。
- 已验证：`python -m pytest tests/test_desktop_shell.py::DesktopShellTests::test_legacy_pfmea_sync_placeholders_are_hidden_when_generation_failed tests/test_desktop_shell.py::DesktopShellTests::test_background_pfmea_generation_failure_is_persisted tests/test_ai_drawing_three_table_workflow.py::AIDrawingThreeTableWorkflowTests::test_chain_pfmea_inherits_confirmed_pfd_process_fields tests/test_ai_drawing_three_table_workflow.py::AIDrawingThreeTableWorkflowTests::test_chain_pfmea_rejects_rows_not_from_confirmed_pfd tests/test_desktop_tauri_app_state.py -q`：19 项通过。
- 已验证：Tauri 前端 `npm run build` 通过。

## 架构深挖问题修复当前状态

- 已确认：GitHub issue #1 到 #5 已记录架构深挖问题，并已按 triage 规则标记为 `enhancement` + `ready-for-agent`。
- 已启动：按用户要求直接按推荐顺序修复，先处理 pipeline 三表结果封装 seam，再处理桌面链式状态迁移，之后处理 edit patch 和 three_table_linkage 的报告装配分离。
- 已完成：`minos_core/three_table_result.py` 抽出三表结果 envelope、manual review 和 status_display，`pipeline.py` 只保留委托入口。
- 已完成：`minos_desktop/chain_state.py` 抽出桌面链式状态迁移，`minos_desktop/services.py` 仅做薄委托。
- 已完成：`minos_core/edit_patch_reports.py` 抽出 review dashboard 和 manual review payload 装配，`edit_patch.py` 保留补丁内核。
- 已完成：`minos_core/three_table_linkage_reports.py` 抽出 sync_snapshot / sync_issues / sync_suggestions 投影，`three_table_linkage.py` 保留 gap 检测。
- 已验证：`python -m pytest tests/test_architecture_seams.py tests/test_edit_patch.py tests/test_three_table_linkage.py tests/test_ai_drawing_three_table_workflow.py -q`，100 passed, 12 subtests passed。
- 进行中：继续补任务记录、问题发现和流程图，然后再看是否还有下一处值得深挖的 seam。

## 发布前完整验收当前状态

- 已完成：发布前验收主线自动化检查已收口，当前未发现新的 core/platform/desktop API 代码缺陷。
- 已修复：Windows 发布版启动软件时弹出命令行窗口；主 Tauri exe 已切换为 release GUI 子系统，Python sidecar 已使用 `CREATE_NO_WINDOW` 隐藏控制台。
- 已验证：新增桌面窗口回归检查先红后绿；`python -m pytest tests/test_desktop_tauri_app_state.py tests/test_desktop_shell.py tests/test_desktop_api_sidecar.py tests/test_desktop_table_editor.py tests/test_live_linkage.py -q`：82 项通过。
- 已验证：`npm run build` 通过；`npm run release:nsis` 通过，并重新生成 `apps\desktop-tauri\src-tauri\target\release\bundle\nsis\MINOS-CORE_1.14.0_x64-setup.exe`。
- 已验证：重新启动 `minos-core-desktop.exe` 后，只看到主窗口 `MINOS-CORE Workbench`；未再出现标题指向 `minos-core-desktop.exe` 的 Windows Terminal 窗口，sidecar 监听 `127.0.0.1:8000`。
- 已修复：Tauri 三表工作台残留英文状态和标签，`medium/approved` 改为 `中风险/已确认`，右侧 `Inspector/Sidecar` 改为 `检查器/本地后端`，流程图符号 `OP/INSP` 改为中文符号。
- 已新增：过程流程图一键确认全部行入口，不再要求先选中单行；阶段操作区显示 `已确认 / 待确认` 数量，表格和流程图节点都显示行级确认状态。
- 已验证：`python -m pytest tests/test_desktop_tauri_app_state.py tests/test_desktop_table_editor.py tests/test_desktop_shell.py tests/test_desktop_api_sidecar.py -q`：68 项通过；Tauri `npm run build` 通过。
- 已定位：当前 run #17 失效模式分析不是本地计算慢，而是文本 Responses 请求多次返回 `504 Gateway Time-out`；后端已将 run 写成 `失败`，但图纸导入页没有持续刷新后台阶段状态。
- 已修复：图纸导入页在确认过程流程图后持续轮询 run 状态，后台失败时显示“失效模式分析生成失败”和原始错误；文本模型默认推理强度保持 `medium`，未降到 `low`。
- 已优化：文本 Responses 对 `504 Gateway Time-out` 已纳入临时上游错误重试；后续 PFMEA 超时主因通过按 PFD 工序拆分请求和流式输出继续收口。
- 已验证：`python -m pytest tests/test_llm_text_responses.py tests/test_desktop_tauri_app_state.py tests/test_desktop_shell.py tests/test_desktop_api_sidecar.py -q`：49 项通过；Tauri `npm run build` 通过。
- 已验证：`python -m pytest tests -q -m "not real_api"`：778 项通过、2 项跳过、61 个 subtests 通过。
- 已验证：`python -m unittest discover -s tests -v`：719 项通过、1 项跳过。
- 已验证：`python -m unittest discover -s tests\acceptance -v`：真实 API 验收入口正常，因 `MINOS_RUN_REAL_ACCEPTANCE` 未设置为 `1` 跳过 1 项。
- 已验证：核心 CLI help、平台 CLI help、桌面 API CLI help 均正常退出。
- 已验证：合成图纸验收闭环通过：`write-demo-drawing` 生成安全演示 PNG，`generate-three-tables --mode ocr_only` 生成三表草案，`accept-three-tables` 检查四个 xlsx OpenXML 结构均正常。
- 已验证：桌面 API 聚焦回归 `python -m pytest tests/test_desktop_tauri_app_state.py tests/test_desktop_api_sidecar.py tests/test_desktop_api_v114.py tests/test_desktop_api_ocr_mode.py -q`：16 项通过。
- 已验证：桌面 sidecar 真实启动 smoke 通过，`/api/health` 返回 `status=ok`，进程已关闭。
- 已验证：Tauri 前端 `npm run build` 通过；Rust `cargo check` 通过。
- 已验证：Python 依赖检查 `python -m pip check` 通过；`python -m pip wheel . --no-deps -w dist` 已生成 `dist/minos_core-0.0.0-py3-none-any.whl`。
- 已发现并修复：Tauri 默认 `bundle.targets = "all"` 在发布打包验收中会拖住流程，长时间不生成安装包；已收口为 `nsis`，并新增 `npm run release:nsis`。
- 已验证：`npm run release:nsis` 通过，生成安装包 `apps\desktop-tauri\src-tauri\target\release\bundle\nsis\MINOS-CORE_1.14.0_x64-setup.exe`。
- 剩余发布风险：本轮没有运行真实图纸真实 API 验收，因为 `MINOS_RUN_REAL_ACCEPTANCE` 和 `MINOS_REAL_DRAWING_PATH` 均未设置；NSIS 安装包使用 `--no-sign`，未做代码签名；未做人工安装/卸载和真实 Excel 打开验收。

## 桌面真实运行 PFD 502 修复

- 已定位：用户在桌面端使用 `JLV03000500_001_AC_RR DH ASSY.pdf` 时，图纸 OCR/身份识别已经成功，失败点是链式 PFD 阶段的文本 Responses 调用，原始错误为 `LLM Responses HTTP 502: {"error":{"message":"Upstream request failed","type":"upstream_error"}}`。
- 已对照：同一张图纸历史 run #13/#14 曾成功生成 PFD；本次失败不是图纸路径、输出目录或 OCR 渲染问题。
- 已复现验证：用失败 run 保存的 `drawing_analysis` 单独调用 `generate_pfd_from_drawing(...)`，设置 `MINOS_TEXT_LLM_REASONING_EFFORT=medium` 时可在约 51 秒内生成 PFD。
- 已修复：文本 LLM 默认推理强度从 `high` 收口为 `medium`，保留 `MINOS_TEXT_LLM_REASONING_EFFORT` / `MINOS_OPENAI_TEXT_REASONING_EFFORT` 环境变量覆盖。
- 已验证：不设置环境变量时，使用同一份 `drawing_analysis` 重新生成 PFD 成功，得到 12 行 PFD。
- 已验证：`python -m pytest tests/test_llm_text_responses.py -q`：4 项通过。
- 已验证：`python -m pytest tests/test_desktop_shell.py::DesktopShellTests::test_chain_start_records_pfd_generation_failure_without_batch_fallback tests/test_ai_drawing_three_table_workflow.py::AIDrawingThreeTableWorkflowTests::test_llm_pfd_generation_normalizes_standard_process_flow_fields -q`：2 项通过。

- 已完成：定位真实代码库为 `D:\MINOS-CORE`，当前工作区已有大量并行改动，未回滚任何既有修改。
- 已完成：只读审核 `minos_core.stage` 与 `minos_core.quality_gates` 包化兼容层，旧公开导入仍可用；`minos_core`、`minos_core.stage`、`minos_core.quality_gates`、`minos_core.pipeline`、`minos_platform.errors` 导入 smoke 通过。
- 已完成：运行聚焦测试 `python -m pytest tests/test_stage_result.py tests/test_quality_audit.py -q`，结果为 31 项和 4 个 subtests 通过。
- 已完成：运行生成阶段聚焦测试 `python -m pytest tests/test_analyze_stage.py tests/test_ingest_stage.py tests/test_generate_pfd_stage.py tests/test_generate_pfmea_stage.py tests/test_generate_control_plan_stage.py tests/test_generated_chain_stage.py -q`，结果为 89 项和 6 个 subtests 通过。
- 已完成：运行扩展聚焦测试 `python -m pytest tests/test_stage_result.py tests/test_quality_audit.py tests/test_export_modes.py tests/test_analyze_stage.py tests/test_ingest_stage.py tests/test_generate_pfd_stage.py tests/test_generate_pfmea_stage.py tests/test_generate_control_plan_stage.py tests/test_generated_chain_stage.py tests/test_pipeline_ocr_first.py tests/test_pipeline_part_family_context.py -q`，结果为 139 项和 10 个 subtests 通过。
- 已完成：运行非真实 API 全量 pytest `python -m pytest tests -q -m "not real_api"`，修复前基线为 775 项通过、2 项跳过、61 个 subtests 通过；修复后为 778 项通过、2 项跳过、61 个 subtests 通过。
- 已发现并修复：`python -m minos_platform.cli --help` 会继续进入 `subprocess.run(...)`，且默认 `--port` 以整数 `8000` 传入命令数组，在 Windows 上触发 `TypeError: expected str, bytes or os.PathLike object, not int`。
- 已新增：`tests/platform/test_cli.py`，覆盖 platform CLI 的 help 不启动服务、默认端口按字符串传参、自定义 host/port 正确传参。
- 已修改：`minos_platform/cli.py` 改用 `argparse` 解析 `--host`/`--port`，捕获 help 的 `SystemExit` 并返回退出码，传给 uvicorn 子进程的参数全部保持字符串；复核后保留旧默认 host `0.0.0.0`，避免无意收窄平台服务监听范围。
- 已验证：`python -m pytest tests/platform/test_cli.py -q`：3 项通过。
- 已验证：`python -m pytest tests/platform -q`：33 项通过。
- 已验证：`python -m unittest discover -s tests -v`：719 项通过，1 项跳过。
- 已验证：`python -m minos_platform.cli --help`、`python -m minos_core.cli --help`、`python -m minos_desktop.api.cli --help` 均可正常显示帮助信息。
- 已同步：按用户最新说明，全局 AGENTS 已取消“失败透明规则”作为硬停止要求；本轮记录改为失败时保留原始现象和影响判断，但不因非关键读取/命令写法错误中断主线。

## Hybrid 图纸识别超时修复当前进度

- 已定位：`hybrid` 模式当前是 OCR 先跑，随后等待视觉 Responses 流式识别；视觉阶段没有 pipeline 级总预算，真实图纸可能一直等到外层命令超时。
- 进行中：给 `hybrid` 默认视觉 analyzer 设置短预算，超时后保留 OCR 草案并进入人工复核。
- 进行中：给 Responses SSE 流式读取增加总时限，避免服务端长时间吊住连接。
- 待验证：补充超时回落测试，并重新运行 `JLV03000500`。

## MINOS v1.8.1 子任务 D 当前进度

- 已完成：读取 `stage.py`、`quality_gates.py` 和相关测试，确认本次只做低风险内部拆分。
- 已完成：`stage.run_stage` 已拆为私有阶段 helper，主函数保留阶段路由。
- 已完成：新增 `_stage_result_from_gate`、`_blocked_result_from_stage`、`_evidence_from_bundle`，统一重复的结果组装与上游阻塞转发。
- 已完成：`quality_gates.evaluate_stage_gate` 已拆出输入规整、质量债务、严格门债务、继续/导出判定、人工复核项组装 helper。
- 已完成：新增回归测试覆盖 `generate_pfmea` 转发 blocked PFD 结果，以及 review confirmation 继续抑制质量债务。
- 已验证：`python -m pytest tests/test_stage_result.py tests/test_quality_audit.py -q`：26 项和 4 个 subtests 通过。

- 已完成：将产品目标从“完整 PPAP 平台”收口为“AI 图纸驱动 PFD/PFMEA/CP 三表生成工具”，第一版不做完整 PPAP 18 项、不做客户门户、不做审批流。
- 已完成：新增 `minos_core/drawing_input.py`，支持 PDF/PNG/JPG 输入识别；PNG/JPG 可生成 `drawing_page_001` 证据，PDF 在未安装 PyMuPDF 时明确失败，不做假渲染。
- 已完成：新增 `minos_core/adapters/multimodal.py`，定义云端多模态图纸识别 adapter 边界和 fake adapter。
- 已完成：新增 `minos_core/ai_config.py`，MINOS 可复用 Codex 的 Responses 模型、中转地址和 auth 配置；密钥只在运行时读取，不写入仓库、不输出。
- 已修复：当 Codex provider 配置 `requires_openai_auth = true` 时，MINOS 不再误用当前环境中的 `ARK_API_KEY`，会优先使用 Codex auth；Responses endpoint 也按 Codex 的 `responses` 路径调用，避免中转 URL 被拼成不一致的 `/v1/responses`。
- 已完成：`python -m minos_core.cli ai-config` 可显示 AI 配置状态；当前默认模型已按项目要求收口为 `gpt-5.5`，并继续使用 Codex 配置的中转地址完成 Responses 调用。
- 已完成：新增 `analyze-drawing` CLI，支持用当前 OpenAI/Codex Responses 配置调用云端多模态 AI，输出 `drawing_analysis_bundle` JSON。
- 已完成：新增 `minos_core/drawing_analysis.py`，定义 `drawing_analysis_bundle`、AI JSON 解析、证据引用校验和图纸识别质量门。
- 已完成：新增 `minos_core/drawing_to_pfd.py`，从图纸识别的 manufacturing clues 推理 PFD 草案。
- 已完成：新增 `minos_core/pfd_to_pfmea_ai.py`，从 PFD 为每道工序生成 PFMEA 草案并保留 AI/复核标记。
- 已完成：增强 `generate_control_plan_from_pfmea`，CP 行保留 confidence、ai_inferred、ai_reasoning。
- 已完成：新增 `minos_core/exporters/three_table_workbooks.py`，支持统一三表工作簿和三份独立 Excel 导出。
- 已完成：新增 `generate_three_tables_from_drawing(...)` 后端闭环入口，串联图纸证据化、AI 图纸识别、PFD、PFMEA、CP、质量门、三表导出和 run manifest。
- 已完成：新增 `generate-three-tables` CLI，默认导出 draft 三表包；final export 在未复核 AI 草案时被质量门阻断。
- 已完成：新增 `minos_desktop` Windows 桌面业务闭环 MVP，PySide6 作为可选依赖，包含项目、图纸导入、AI 识别结果、PFD、PFMEA、CP、人工复核、导出、设置页面。
- 已完成：新增 `minos_desktop/services.py`，通过服务层管理桌面项目、设置、运行状态和 core pipeline 调用。
- 已完成：桌面端默认使用 SQLite `%LOCALAPPDATA%\MINOS-CORE\minos_desktop.sqlite3`，保存项目、run 记录和导出记录。
- 已完成：新增 `DesktopSettingsStore`、`DesktopProjectStore`、`DesktopRunService`，以及 `DesktopRunState`、`DesktopRunRecord`、`DesktopExportRecord`。
- 已完成：Qt UI 已通过服务层创建/更新项目，后台运行 `generate_three_tables_from_drawing(...)`，并刷新 AI/PFD/PFMEA/CP/复核/导出页。
- 已完成：设置页显示 AI 配置状态和默认输出目录，不显示、不保存明文 API key。
- 已完成：桌面失败报告包含原始错误、原因判断和三种处理方案，且包含“放弃任务”。
- 已完成：新增 `minos-desktop` 启动入口；未安装 PySide6 时会明确提示安装 `.[desktop]`，不破坏 core/platform 测试。
- 已完成：桌面端用户可见语言已收口为中文：三表表头、文件选择器、设置摘要、人工复核摘要、导出摘要、导出完成提示均使用中文显示；内部字段名仍保持英文以兼容 edit_patch 和服务层。
- 已完成：三表独立 Excel 中用户可见的 `PFMEA ID`、`CP ID` 已改为中文编号表头。
- 已完成：AI 识别 prompt 已要求模型返回中文业务内容；本地 PFD 工艺库、PFMEA 风险模板、CP 控制计划模板已改为中文，桌面表格中的草案工序、过程功能、失效模式、控制方法等不再默认生成英文。
- 已完成：新增中文工序归一化，AI 返回“落料/冲孔/注塑/装配”等中文工序时仍可识别工艺族并补齐三表。
- 已完成：第一层三表核心联动已收口：PFD 主数据字段扩展，PFMEA 继承 PFD 工序上下文，CP 保留 PFMEA 来源、风险与检具信息；严格三表一致性硬门仅对 MINOS 新生成/人工编辑链路启用，旧 fixture 和弱链接审计样本继续保持兼容。
- 已验证：`python -m unittest tests.test_desktop_shell tests.test_qt_app_helpers -v` 通过。
- 已验证：`python -m pytest tests/test_desktop_table_editor.py tests/test_qt_app_helpers.py tests/test_desktop_shell.py -q`：19 项通过。
- 已验证：`python -m pytest tests/test_ai_drawing_three_table_workflow.py tests/test_openai_multimodal_adapter.py tests/test_generate_control_plan_stage.py -q`：35 项通过。
- 已验证：`python -m pytest tests/test_desktop_table_editor.py tests/test_generate_control_plan_stage.py tests/test_ai_drawing_three_table_workflow.py -q`：35 项通过。
- 已验证：`python -m unittest discover -s tests -v`：284 项通过。
- 已验证：`python -m pytest tests/platform -q`：27 项通过。

## 桌面业务闭环 MVP 当前状态
桌面业务闭环 MVP 已落地。当前桌面端定位仍是 AI 图纸驱动 PFD/PFMEA/CP 三表生成工具的本地操作壳，不是完整 PPAP 平台。

## 桌面业务闭环 MVP 已完成
- `minos_desktop/services.py` 已承接桌面项目、设置、运行记录、导出记录和后台 run 服务。
- 默认数据库为 `%LOCALAPPDATA%\MINOS-CORE\minos_desktop.sqlite3`。
- Qt UI 已从直接界面骨架升级为通过服务层驱动 core pipeline，并把结果同步到 AI 识别、PFD、PFMEA、CP、人工复核和导出页面。
- AI 配置只展示状态和来源，不显示或持久化明文 key。
- PySide6 仍为可选依赖和懒加载，不影响无桌面依赖环境。

## 桌面业务闭环 MVP 验证结果
/// 1. `python -m unittest tests.test_desktop_shell tests.test_qt_app_helpers -v`：通过。
/// 2. 后续仍建议在完整回归中覆盖 `python -m unittest discover -s tests -v`，并手工打开桌面 UI 检查真实文件导入和导出路径。

## 真实桌面试跑与交付验收当前状态
桌面/CLI 自检脚本已落地。默认验收只做本机 preflight，不调用真实 AI 网络，也不要求 PySide6 必须安装。

## 真实桌面试跑与交付验收已完成
- 已新增 `minos_desktop/preflight.py`，输出结构化 JSON 风格报告：`status`、`checks`、`warnings`、`recommendations`。
- 已检查 PySide6 安装状态；未安装时记录 warning，不破坏无 Qt 测试。
- 已检查 AI 配置状态，只显示 `api_key_configured`、`api_key_source`、`api_key_env_name` 等来源信息，不输出明文 API key。
- 已检查默认输出目录和 SQLite DB 写入能力。
- 已检查 `minos_desktop.cli` 和 `minos_desktop.qt_app` 桌面入口可导入。
- 已在 `minos_desktop/cli.py` 增加 `--smoke`、`--output-dir`、`--db-path`、`--require-ai-config`。
- 已新增 `tests/test_desktop_preflight.py`，覆盖缺 PySide6、SQLite 可写、AI key 脱敏、失败格式包含“放弃任务”、CLI smoke JSON 输出。
- 已新增 `minos_core/demo_acceptance.py`，可生成合成 safe demo drawing，并检查 `three_table_generation_result`、manifest、exports、AI evidence refs、PFD/PFMEA/CP 内容和 xlsx zip 可打开性。
- 已在 `minos_core.cli` 增加 `write-demo-drawing` 和 `accept-three-tables`，用于交付验收命令行闭环。
- 已新增 `tests/test_demo_acceptance.py`，覆盖 demo PNG、fake AI 三表输出验收、缺 workbook/manifest 失败和 CLI 命令。

## 真实桌面试跑与交付验收验证结果
/// 1. 首次运行 `python -m unittest tests.test_desktop_preflight tests.test_desktop_shell tests.test_qt_app_helpers -v` 失败，原因为 Windows 上 SQLite 连接释放不够明确，以及旧测试直接调用 `main()` 时被 unittest 参数污染。
/// 2. 已修复：显式关闭 SQLite 连接；`main(argv)` 改为标准显式参数解析，测试不再依赖隐式 unittest 兼容分支。
/// 3. 再次运行 `python -m unittest tests.test_desktop_preflight tests.test_desktop_shell tests.test_qt_app_helpers -v`：16 项通过。
/// 4. `python -m unittest tests.test_demo_acceptance tests.test_ai_drawing_three_table_workflow -v`：14 项通过。

## 真实桌面试跑与交付验收待手工执行
/// 1. `python -m minos_core.cli ai-config`
/// 2. `python -m minos_core.cli write-demo-drawing --output out\desktop_acceptance\safe_demo_drawing.png`
/// 3. `python -m minos_core.cli generate-three-tables --input out\desktop_acceptance\safe_demo_drawing.png --output-dir out\desktop_acceptance\cli_smoke`
/// 4. `python -m minos_core.cli accept-three-tables --result out\desktop_acceptance\cli_smoke\three_table_generation_result.json`
/// 5. `python -m minos_desktop.cli --smoke --output-dir out\desktop_acceptance\preflight --db-path out\desktop_acceptance\preflight\minos_desktop.sqlite3`
/// 6. 安装 `.[desktop]` 后运行 `minos-desktop`，人工检查空路径提示、选择图纸、运行生成、页面刷新、打开输出目录和 Excel 打开性。

## 任务 5 当前状态
工程化基础设施已补齐：项目现在包含最小 `pyproject.toml`、仓库级 `.gitignore`，并已同步 README / progress / rebuild_manifest 中的当前状态说明。

## 任务 5 已完成
- 已新增 `.gitignore`，忽略 `__pycache__/`、`*.pyc`、`.claude/settings.local.json`、虚拟环境、构建目录、测试缓存和常见临时/输出目录。
- 已新增最小 `pyproject.toml`，声明 `minos-core` 包、Python `>=3.9`、空第三方依赖、`minos-core` CLI 入口和 unittest 发现信息。
- 已更新 `README.md`，明确当前 workbook 为 7 张 sheet、测试数量不再固化、draft 入口不是正式导出。
- 已更新 `progress.md` 和 `rebuild_manifest.md`，避免继续把旧的 89 项测试或 5 sheet 说法当作当前状态。
- 未修改、未提交本地 `.claude` 配置。

## 任务 5 验证结果
/// 1. 待运行：`python -m py_compile minos_core/*.py minos_core/adapters/*.py minos_core/exporters/*.py`。
/// 2. 待运行：使用 Python 基本文本检查解析 `pyproject.toml` 必要字段；若当前 Python 提供 `tomllib`，同时做 TOML 解析。
/// 3. 待运行：检查 `.gitignore` 是否包含 `.claude/settings.local.json`、`__pycache__/` 和 `*.pyc`。

## 任务 2 当前状态
`generate-draft` CLI/API 入口已完成，用于从 Evidence/fixture 输入运行 generated pipeline 并输出 APQPChain draft JSON。该入口只生成草案结果，不等同正式导出。

## 任务 2 已完成
- 已在 `minos_core/pipeline.py` 新增 `generate_draft(evidence, output_path=None)` API。
- 已新增 draft envelope 语义：`apqp_chain_draft_result`、`draft_notice`、`draft_is_formal_export=False`、`draft`、`quality_gate`、`manual_review`、`stage_results`。
- 已在 `minos_core/cli.py` 新增 `generate-draft` 子命令，并提供 `run-pipeline` 别名。
- 已在 `minos_core/stage.py` 增加 `generate_draft` / `run_pipeline` stage 外壳入口。
- 已补 `tests/test_generated_chain_stage.py` 针对 API、保存文件、stage wrapper、CLI 子命令和别名的测试。
- 已更新 `tests/test_apqp_rebuild_contract.py` 的固定 stage 顺序契约。
- 已更新 `project_flow.mmd`，补入 assemble draft 与 generate draft 草案入口。

## 任务 2 验证结果
/// 1. `PYTHONPATH="D:/MINOS-CORE" python "D:/MINOS-CORE/tests/test_generated_chain_stage.py" -v`：6 项通过。
/// 2. `PYTHONPATH="D:/MINOS-CORE" python "D:/MINOS-CORE/tests/test_apqp_rebuild_contract.py" -v`：13 项通过。
/// 3. 旧 CLI smoke：`list`、`validate`、`audit --json` 均返回 0。
/// 4. `generate-draft` CLI smoke 返回 0，stdout 与保存 JSON 一致，`draft_is_formal_export=False`，`allow_user_export=False`，`manual_review.required=True`。
/// 5. 额外运行完整 unittest 时，`test_legacy_excel_adapter` 的 limiter export 因 export gate 阻断失败；该失败与任务 2 的 targeted 测试无关，需后续决定是补 limiter 规格字段还是调整 legacy 测试预期。

## 第十二阶段当前状态
AI analyze 增强已接入 FakeLLM 契约，默认 keyword-only 路径保持不变。

## 第十二阶段已完成
- 已新增 `analyze_evidence_bundle_with_ai(source, llm_adapter)`，先运行规则分析，再合并 LLM 结构化候选。
- 已限制 AI 输出块为 `drawings`、`characteristics`、`process_clues`、`pending_fields`、`risksAndUncertainties`。
- 已强制 AI 输出引用已有 evidence，并统一标记 `ai_inferred=True`、`needs_confirmation=True`。
- 已实现非法 JSON、未知输出块、缺失 source_ref、引用不存在 evidence 时直接失败，不做 fallback。
- 已更新 analyze gate，AI process clue 不计入“可进入 generate_pfd”的有效 Pxx route clue。
- 已新增 `tests/test_analyze_stage.py` 中 AI analyze 相关测试，覆盖 FakeLLM、非法 JSON、source_ref、AI-only route 和 keyword-only 不退化。

## 第十一阶段当前状态
PFMEA 与控制计划生成闭环已接通，未搬目录，未接入 LLM。

## 第十一阶段已完成
- 已新增 `minos_core/generate_pfmea.py`，从 `failure_mode_candidates` 生成 `pfmea` bundle，保留证据引用并用明确的工程确认占位字段。
- 已新增 `minos_core/generate_control_plan.py`，从 `pfmea` bundle 生成 `control_plan` bundle，按 AP/严重度/频度做薄规则默认控制项。
- 已更新 `minos_core/stage.py`，接入 `generate_pfmea` 和 `generate_control_plan` 阶段，保持 `validate/export` 路径不变。
- 已更新 `minos_core/quality_gates.py`，新增 PFMEA 与控制计划 bundle gate，并把上游 pending 与本阶段 blocking pending 分开。
- 已修正 brainstorm 预检语义，空 `operation` 在 brainstorm preflight 中只作为 review，真正无候选项仍由候选质量门阻断。
- 已新增 `tests/test_generate_pfmea_stage.py` 和 `tests/test_generate_control_plan_stage.py`，覆盖正常生成、证据引用、AI-only 阻断、缺证据阻断和旧链路不退化。
- 已新增 `README.md`，记录当前 pipeline、运行命令、测试命令和核心边界。
- 已更新 `project_flow.mmd`，补入 failure mode candidates、PFMEA bundle、control plan bundle 与新测试门。
- 第十一阶段完成时完整回归曾显示 114 项全部通过；当前测试数量已继续变化，不再把 114 项作为当前状态。
- 已运行 CLI smoke：`validate`、`audit`、`export` 均通过。

## 当前状态
第二阶段已开始：真实样本迁移的测试与文档已按允许范围更新。adapter 实现由另一个 worker 负责，本轮只约束公开契约并保留验收入口。

## 已完成
- 已确认当前工作树存在并行改动风险，未回退、未覆盖允许范围外文件。
- 已新增 `tests/test_legacy_excel_adapter.py`，覆盖三个真实 Excel 源：
  - 门铰链：`JLH01000300-门铰链.xlsx`
  - 冲压件：`1004258-冲压件.xlsx`
  - 限位器：`XWQ01000100-限位器.xlsx`
- 测试会对每个样本执行：`convert_legacy_workbook` 转 tempfile fixture、JSON 解析、`load_apqp_chain`、`validate_chain`、`export_fixture`、xlsx zip 结构检查和 workbook sheet 顺序检查。历史第二阶段契约当时要求 5 张 sheet；当前交付已扩展为 7 张 sheet。
- 已更新 `task_plan.md`，明确第二阶段目标：真实样本转标准 fixture，OCR/LLM 仍保持 adapter 外挂。
- 已更新 `findings.md`，补充真实样本 workbook 迁移风险和验收重点。
- 已更新 `rebuild_manifest.md`，记录新增测试和第二阶段文档变更。

## 当前待验证
/// 1. adapter worker 暴露 `minos_core.adapters.legacy_excel.convert_legacy_workbook` 或 `minos_core.adapters.legacy.convert_legacy_workbook`。
/// 2. 运行 `python -m unittest tests.test_legacy_excel_adapter -v`。
/// 3. 如果测试失败，按原始错误判断是源文件缺失、adapter 接口缺失、转换字段缺失、validation 不通过还是 xlsx 打开性问题。
/// 4. 用 git status 审核修改范围是否仅限本轮允许的 5 个文件。

## 风险
- 本轮没有写 adapter，因此在 adapter worker 完成前，真实样本测试会因 `convert_legacy_workbook` 缺失而失败。
- 三个真实 workbook 都存在大量合并单元格和向下继承语义，adapter 若只读显式单元格值，可能丢失工序编号、PFMEA 行归属或控制计划归属。
- validation 是硬门槛：mandatory/high-risk PFMEA 必须进入控制计划，否则不能把转换结果视为成功。

## 下一步
- 等 adapter worker 完成后，优先跑新增真实样本测试。
- 若三个样本中某个 validation 不通过，先修 adapter 的映射和继承规则，不把失败隐藏在 core 或 exporter 里。
- 真实样本通过后，再考虑把转换出的 fixture 固化为回归样本；当前测试仍保持 tempfile 输出。

## 第三阶段当前状态
第三阶段已开始：质量审计的测试与文档已按允许范围更新。audit/CLI 实现由另一个 worker 负责，本轮只约束公开契约并保留验收入口。

## 第三阶段已完成
- 已新增 `tests/test_quality_audit.py`。
- 测试覆盖四套标准 fixture：
  - `tests/fixtures/apqp_chain`
  - `tests/fixtures/door_hinge`
  - `tests/fixtures/stamping`
  - `tests/fixtures/limiter`
- 测试要求 `audit_chain` 对每套 fixture 能运行，并且报告包含 `counts` 与 `manual_review_items`。
- 已构造最小弱链接样本：PFD/PFMEA/CP 结构仍闭环，但控制计划规格、测量方法、抽样频次和反应计划明显偏弱。
- 已验证测试意图：弱链接样本应通过 `validate_chain`，同时由 `audit_chain` 识别 mechanical / weak / manual review 风险。
- 已更新 `task_plan.md`，明确第三阶段是质量审计，不是硬校验。
- 已更新 `findings.md`，记录“结构闭环”和“内容可靠”的边界。
- 已更新 `rebuild_manifest.md`，记录新增测试和第三阶段文档变更。

## 第三阶段当前待验证
/// 1. audit worker 暴露 `minos_core.audit.audit_chain`，或兼容别名 `audit_apqp_chain` / `run_quality_audit`。
/// 2. audit report 暴露 `counts`。
/// 3. audit report 暴露 `manual_review_items`。
/// 4. 运行 `python -m unittest tests.test_quality_audit -v`。
/// 5. 用 git status 审核修改范围是否仅限本轮允许的 5 个文件。

## 第三阶段风险
- 当前只负责测试和文档；在 audit worker 完成前，`tests/test_quality_audit.py` 会因为 audit 模块缺失而失败。
- 如果 audit 把弱链接直接变成 validate 失败，就会混淆第三阶段边界：validate 管结构闭环，audit 管内容可靠。
- 按工作范围限制，本轮未更新 `project_flow.mmd`，避免触碰用户未授权写入的文件。

## 第四阶段当前状态
第四阶段已完成：只针对 `limiter` 样本收口 legacy PFMEA/CP 链接质量，并补上审计回归门槛。

## 第四阶段已完成
- 已读取 `tests/fixtures/limiter/pfmea.json` 和 `tests/fixtures/limiter/control_plan.json`，并对照 `audit --input tests\fixtures\limiter` 输出定位问题。
- 已确认原始问题主要是：多个 PFMEA 被机械挂到同一个 CP、CP 反向 `pfmea_id` 错挂、文本 overlap 不理解“压力/位置/力矩/禁用物质”等质量工程词。
- 已改进 `minos_core/adapters/legacy_excel.py`：加入质量工程业务词、特殊特性分类优先、同工序全局匹配、必要的一对多派生控制行。
- 已改进 `minos_core/audit.py`：audit 的文本重合判定同步使用质量工程业务词，减少同义不同字面的误判。
- 已只重新生成 `tests/fixtures/limiter`，未重建 `door_hinge` 和 `stamping`。
- 已在 `tests/test_quality_audit.py` 增加 limiter 第四阶段回归门槛。

## 第四阶段指标结果
- `mechanical_links`：10 -> 0，目标 `<= 3`，已达成。
- `weak_links`：22 -> 1，目标 `<= 10`，已达成。
- `manual_review_items`：35 -> 4，目标 `<= 18`，已达成。

## 第四阶段待验证
/// 1. 运行 `python -m minos_core.cli validate --input tests\fixtures\limiter`。
/// 2. 运行 `python -m minos_core.cli audit --input tests\fixtures\limiter`。
/// 3. 运行 `python -m unittest discover -s tests -v`。
/// 4. 审核 git diff，确认改动聚焦 limiter 链接质量和回归门槛。

## 第五阶段当前状态
第五阶段已完成代码落地：MINOS-CORE 已按 Domain Core、Pipeline、Adapters、Quality Gates 四层拆清依赖方向。

## 第五阶段已完成
- Domain Core 已补齐业务对象：`Drawing`、`Characteristic`、`Evidence`，并保留原有 `Product`、`ProcessStep`、`FailureMode`、`ControlItem`、`TraceLink`。
- Domain Core 不再拥有 `_read_json` 文件读取；旧的 `load_apqp_chain` 仅作为兼容 wrapper 转发到 Adapter。
- 新增 `minos_core/adapters/fixture_json.py`，统一负责标准 fixture JSON / 目录读取。
- `pipeline.py` 新增固定 `PIPELINE_STAGES`，并统一调用 fixture adapter。
- `cli.py` 删除重复 fixture loader，改用 fixture adapter。
- 新增 `minos_core/quality_matching.py`，让 legacy adapter 与 audit 共用同一套质量工程文本匹配规则。
- 新增 `minos_core/quality_gates.py`，暴露阶段质量门 `evaluate_stage_gate` 和 `StageQualityGate`。
- 已补测试锁住：Domain Core 无文件 IO、fixture adapter 负责读取、Pipeline 阶段顺序、Quality Gate 阶段准入。

## 第五阶段待验证
/// 1. 运行 `python -m unittest discover -s tests -v`。
/// 2. 运行 CLI validate/export/audit smoke，确认旧入口仍可用。
/// 3. 审核 git diff，确认没有把 OCR/LLM 接进 Domain Core。

## 第六阶段当前状态
第六阶段已完成代码落地：阶段流转、证据引用、导出质量门 sheet、OCR/LLM adapter 占位接口均已实现。

## 第六阶段已完成
- 新增 `minos_core/stage.py`，提供 `StageContext`、`StageResult`、`build_stage_context`、`build_stage_result`、`run_stage`。
- `StageResult` 已包含 `stage/status/output/evidence/pending_fields/ai_inferred_items/quality_gate`。
- `ProcessStep`、`FailureMode`、`ControlItem`、`TraceLink` 已新增 `evidence_refs`，旧 fixture 默认 `[]`。
- APQP workbook 已从 5 张 sheet 扩展为 7 张：新增 `质量门状态` 与 `人工复核清单`。
- 新增 `minos_core/adapters/ocr.py` 和 `minos_core/adapters/llm.py`，只定义协议、结果对象、fake adapter 和 not-configured adapter。
- 已新增 `tests/test_stage_result.py` 和 `tests/test_ocr_llm_adapters.py`。
- 完整 unittest 已扩展到 26 项并全部通过。

## 第六阶段待验证
/// 1. 运行 CLI validate/audit/export smoke。
/// 2. 审核 git diff。
/// 3. 提交第六阶段改动。

## 第七阶段当前状态
第七阶段已完成代码落地：Evidence 已文件化，apqp_chain fixture 已补证据引用，Quality Gate 已能检查证据覆盖。

## 第七阶段已完成
- `fixture_json` 已支持目录下可选 `evidence.json`。
- `tests/fixtures/apqp_chain/evidence.json` 已新增 6 条证据。
- `process_flow.json`、`pfmea.json`、`control_plan.json` 已写入 `evidence_refs`。
- `StageQualityGate` 已新增 evidence coverage 输出：覆盖率、缺失引用、未覆盖对象、待确认证据。
- 有 evidence 池时，质量门会阻断未覆盖对象、缺失 evidence id、被引用 AI 推断证据和待确认证据。
- 无 evidence 池的旧 fixture 保持兼容，仍按三表结构存在判断证据充分。
- Excel `质量门状态` sheet 已显示证据覆盖率和证据问题数量。
- 完整 unittest 已扩展到 29 项并全部通过。

## 第七阶段待验证
/// 1. 运行 CLI validate/audit/export smoke。
/// 2. 审核 git diff。
/// 3. 提交第七阶段改动。

## 第八阶段当前状态
第八阶段已完成代码落地：`ingest` 已从阶段名变成可运行入口，能把多种输入统一转成 Evidence bundle。

## 第八阶段已完成
- 新增 `minos_core/ingest.py`。
- `run_stage(..., stage="ingest")` 已支持 evidence-only 输入，不再强制构造完整 APQPChain。
- 已支持输入类型：`evidence_bundle` JSON、manual `content/text` JSON、fixture 目录、只有 `evidence.json` 的目录、OCR text、FakeOCRAdapter。
- `quality_gates.py` 已做 stage-aware 分流：`ingest/analyze` 使用轻量 Evidence 入口门；`validate/export` 继续使用三表 evidence_refs 覆盖门。
- ingest 阶段规则：至少一条可用且非 AI 推断的 Evidence 才允许进入 analyze；部分 AI 推断或待确认证据只提示不阻断；全部 AI 推断会阻断。
- 已新增 `tests/test_ingest_stage.py`，完整 unittest 已扩展到 40 项并全部通过。

## 第八阶段待验证
/// 1. 运行 CLI validate/audit/export smoke。
/// 2. 审核 git diff。
/// 3. 提交第八阶段改动。

## 第九阶段当前状态
第九阶段已完成代码落地：`analyze` 已能把 Evidence bundle 转成结构化 analysis bundle。

## 第九阶段已完成
- 新增 `minos_core/analyze.py`。
- `run_stage(..., stage="analyze")` 已支持 fixture dir、evidence bundle、manual JSON、OCR text。
- analysis bundle 输出包含：`evidence`、`drawings`、`characteristics`、`process_clues`、`pending_fields`、`ai_inferred_items`、`metadata`。
- 已实现关键词规则：drawing/revision 线索、material thickness、rivet height、push-out force、barcode、pack quantity、P10/P20/P30 工序线索等。
- 新增 `evaluate_analysis_bundle_gate`，判断 analysis bundle 是否可进入 `generate_pfd`。
- analyze 阶段 `allow_user_export=False`，只允许进入下一阶段，不允许直接导出给用户。
- 已新增 `tests/test_analyze_stage.py`，完整 unittest 已扩展到 51 项并全部通过。

## 第九阶段待验证
/// 1. 运行 CLI validate/audit/export smoke。
/// 2. 审核 git diff。
/// 3. 提交第九阶段改动。

## 第十阶段当前状态
第十阶段已完成代码落地：`generate_pfd` 已能从 analysis bundle 生成正式 `process_flow`。

## 第十阶段已完成
- 新增 `minos_core/generate_pfd.py`。
- `run_stage(..., stage="generate_pfd")` 已支持 fixture、analysis bundle、evidence bundle、manual JSON、OCR text。
- PFD 生成规则：只接收明确 `Pxx` 工序线索；无 step id 的 process clue 进入 pending，不猜编号。
- 已生成 `ProcessStep` 和 `TraceLink`，并保留 step/link 的 `evidence_refs`。
- PFD 输出不包含 PFMEA、Control Plan、failure_modes 或 controls。
- 新增 `evaluate_pfd_bundle_gate`，判断 PFD 是否可进入 `brainstorm_failure_modes`。
- AI-only 路线会阻断；OCR 待确认证据可生成 PFD，但保留人工复核提示，且不允许导出。
- 完整 unittest 已扩展到 67 项并全部通过。

## 第十阶段待验证
/// 1. 运行 CLI validate/audit/export smoke。
/// 2. 审核 git diff。
/// 3. 提交第十阶段改动。

## 第十阶段下阶段前筛查修复
进入第十一阶段前已完成一次前向筛查，并修复 PFD 到 `brainstorm_failure_modes` 的衔接风险。

## 已修复问题
- PFD gate 已校验 step/link 的 `evidence_refs` 是否存在且引用顶层 evidence。
- PFD gate 已在 missing evidence refs、AI-only evidence refs 时设置 `evidence_sufficient=False`。
- link 缺少 `evidence_refs` 或引用不存在 evidence 时会阻断。
- `process_function` / `special_characteristics` 为空只作为 review 项，不阻断进入下一阶段。
- 新增 `brainstorm_failure_modes` 前置分支：只接收 `process_flow`，复用 PFD gate，不再误走完整 APQPChain validate/export 路径。
- 完整 unittest 已扩展到 75 项并全部通过。

## 第十阶段二次前向筛查修复
- analyze gate 已收紧为至少 2 个合法 `Pxx` route clue 才允许进入 `generate_pfd`。
- analyze 已避免同一 evidence 中 Pxx 命中的 operation 再输出重复 phrase-only clue。
- `needs_confirmation` 不再被误归入 `ai_inferred_items`。
- analyze gate 已检查 `process_clues.source_ref` 是否引用顶层 evidence。
- PFD/brainstorm gate 已支持字符串形式 `pending_fields`。
- PFD/brainstorm gate 已检查 `link_type`，缺失、空值或非法值会阻断。
- brainstorm preflight 的报告语义已修正为 `stage_mode=brainstorm_failure_modes_preflight`。
- 第十阶段二次前向筛查时完整 unittest 曾扩展到 89 项并全部通过；当前测试数量已继续变化，不再把 89 项作为当前状态。

## Phase 6 pilot 当前状态
Phase 6 真实项目试运行已完成代码落地：input_package 接入 generate_draft，`review-template` 和 `apply-review` 人工复核链路已接通，`run_manifest` schema 收紧。

## Phase 6 pilot 已完成
- 新增 `tests/fixtures/real_project_input_package_template/`：脱敏真实项目 input_package 模板 fixture，包含 input_package.json、evidence.json、review_patch.json（模板态）、source_index.json。
- 新增 `tests/test_phase6_pilot_workflow.py`：覆盖 `input_package -> generate_draft -> review-template -> 人工填写 review_patch -> apply-review -> export` 完整链路。
- 新增 `minos_core/review_patch.py`：`build_review_patch_template` 从 draft envelope 生成待人工填写模板；`apply_review_patch` 应用复核 patch 并记录 confirmations。
- `review_patch_template` 必须携带 `template_status: "requires_human_review_before_apply_review"`；`apply_review_patch` 发现此字段则抛出 `ReviewPatchError`，模板不能被误当成已批准 patch。
- 在 `minos_core/cli.py` 新增 `review-template` 和 `apply-review` 子命令。
- 在 `minos_core/__init__.py` 导出 `build_review_patch_template`，原有 `brainstorm_failure_modes_from_pfd` 等导出保持不变。
- `run_manifest` 的 `inputs`/`outputs` 字段收紧为固定 object 格式（`_dump_json_object`），非 dict 值包装为 `{"value": ...}`；所有 manifest 测试通过。
- 补 `tests/test_review_patch.py` 覆盖 7 个测试场景。
- 新增 `tests/test_input_package.py` 中 real_project_template 和 realistic_input_package 回归测试。
- 完整 unittest 已扩展到 195 项并全部通过。

## Phase 6 pilot 待验证
/// 1. 运行 `python -m unittest discover -s tests -v`，确认 195 项全部通过。
/// 2. 审核 git diff，确认改动聚焦 Phase 6 pilot 链路和文档。
/// 3. 提交 Phase 6 pilot 改动。

## Phase 6 pilot 下一步
准备一个已脱敏、非客户敏感的 filled input_package 示例，跑通 `generate-draft -> review-template -> 人工填写 review_patch -> apply-review -> export` 全链路，并记录哪些字段仍需人工补齐、哪些质量门提示最影响工程人员使用。

## 真实样本闭环验收与最小修复
本阶段已完成三类真实图纸样本的后端闭环验收，并补上了桌面依赖与 preflight 健壮性修复。

## 已完成
- 修复 `load_openai_responses_config()` 的模型漂移：MINOS 不再默认继承 Codex 主模型，未显式配置时固定回落到项目默认 `gpt-5.5`，但继续复用 Codex `auth.json` 和中转 `base_url`。
- 同步修正桌面设置状态来源：`model_source` 现在只显示环境变量来源或 `default`，不再误报 `codex_config`。
- 新增 `tests/test_ai_config.py` 回归场景，锁住“Codex 代理 + Codex 鉴权 + MINOS 默认模型为 `gpt-5.5`，显式环境变量仍可覆盖”。
- 跑通第三类真实样本：`C:\Users\fgtan\Desktop\知识库种子\限位器\XWQ01000100-限位器.pdf`。
- `accept-three-tables` 已验证限位器统一工作簿和三份独立 Excel 结构正常，可打开性检查通过。
- 三类真实样本当前结果：
  - `stamping_1004258_fix1`：`needs_review`，PFD 8 步，PFMEA 8 行，CP 8 行，人工复核 122 项。
  - `hinge_JLH01000300`：`needs_review`，PFD 10 步，PFMEA 10 行，CP 10 行，人工复核 203 项。
  - `limiter_XWQ01000100`：`needs_review`，PFD 8 步，PFMEA 8 行，CP 8 行，人工复核 112 项。
- 已安装 `PySide6 6.11.0`，`python -m minos_desktop.cli --smoke --require-ai-config` 现已返回 `status=ready`。
- 已验证桌面启动路径：`python -m minos_desktop.cli` 可拉起进程且不会立即退出。
- 修复 `minos_desktop.preflight`：当 `PySide6` 已安装但当前环境导入异常时，preflight 现在返回失败检查而不是直接崩溃。
- 新增 `tests/test_desktop_preflight.py` 回归场景，覆盖“已安装但导入失败”的 `PySide6` 检查。
- 当前完整回归结果：
  - `python -m unittest discover -s tests -v`：250 项全部通过。
  - `python -m pytest tests/platform -q`：27 项全部通过。

## 本阶段遗留
- 三类真实样本都还是 `needs_review`，说明当前产物已达到工程草案级别，但距离“低复核负担”还有差距。
- 桌面 UI 进程已能启动，但这轮没有做人工点击级验收，尚未逐页确认“选择图纸 -> 运行 -> 自动刷新 -> 打开输出目录”。

## 下一步
/// 1. 用已跑通的真实样本优先压缩 `manual_review.items` 数量，先清理最明显的可自动化字段缺失。
/// 2. 增加一个桌面侧的真实运行记录回归，覆盖 `DesktopRunService` 对真实 PDF 的保存与读取。
/// 3. 做一次人工桌面点击验收，记录是否存在页面刷新、提示文本或打开输出目录的实际交互问题。

## 复核负担压缩阶段
本阶段已完成最值得先做的复核清单压缩：不放宽质量门，只减少重复和低价值噪音。

## 已完成
- 三表结果 envelope 的 `manual_review.items` 已增加统一去重：同一 `item_id`、同一字符串、以及 `PFMEA-xxx` / `failure_mode:PFMEA-xxx`、`CP-xxx` / `control_item:CP-xxx` 等同一目标不会重复展示。
- 去重时优先保留结构化复核项，再保留无法结构化的字符串项，避免丢失复核原因。
- PFD 质量门不再把普通工序 `special_characteristics=[]` 作为每步复核噪音；只有该工序自身 `needs_confirmation=True` 时才提示空特殊特性复核。
- PFD 质量门新增“顶层特殊特性未分配到工序”的聚合复核项：存在未映射的特殊特性时只提示 `process_flow.characteristics.unmapped` 一项，并在 gate report 中保留 `unmapped_special_characteristics` 明细。
- 新增/调整测试：
  - 三表端到端测试断言 `manual_review.items` 不重复，同时 `status` 仍为 `needs_review`。
  - PFD gate 测试断言普通空特殊特性不刷复核，待确认步骤仍保留复核。
  - PFD gate 测试断言未分配特殊特性只聚合提示一次，已分配特殊特性不误报。
- 使用三类既有真实结果离线重算压缩效果：
  - `stamping_1004258_fix1`：122 -> 40，减少 82 项。
  - `hinge_JLH01000300`：203 -> 70，减少 133 项。
  - `limiter_XWQ01000100`：112 -> 35，减少 77 项。
- 压缩后 `allow_user_export` 仍为 `False`，正式导出质量门没有被放宽。

## 验证
- `python -m unittest tests.test_generate_pfd_stage -v`：35 项全部通过。
- `python -m unittest discover -s tests -v`：251 项全部通过。
- `python -m pytest tests/platform -q`：27 项全部通过。

## 受阻记录
- 真实 AI 重跑限位器压缩版时，上游返回 `503 Service temporarily unavailable`：
  - 命令：`python -m minos_core.cli generate-three-tables --input "C:\Users\fgtan\Desktop\知识库种子\限位器\XWQ01000100-限位器.pdf" --output-dir out\real_run\limiter_XWQ01000100_compressed --result-output out\real_run\limiter_XWQ01000100_compressed\three_table_generation_result.json`
  - 原始错误：`generate-three-tables failed: OpenAI Responses API failed after 3 attempt(s): 503: {"error":{"message":"Service temporarily unavailable","type":"api_error"}}`
  - 判断：更像当前中转或上游服务临时不可用，不是本次压缩逻辑错误。

## AI 风险推理增强阶段
本阶段把 PFMEA/CP 从“占位式草案”推进到“AI 先推理完整工程草案”，人工复核从补空白改为审核高风险和不确定项。

## 已完成
- PFMEA 推理增强：
  - 每道 PFD 工序生成多条 PFMEA 风险，不再硬限制最多 5 条；只要求风险行有效、去重、可追溯。
  - 每条 PFMEA 行补齐失效模式、后果、原因、S/O/D/AP、预防控制、探测控制、建议措施、AI 推理理由、confidence、evidence refs。
  - 普通 AI 推理行不再全部 `needs_confirmation=True`。
  - 高严重度、AP 高、特殊特性、低 confidence 仍标记待人工确认。
- CP 生成增强：
  - 根据 PFMEA 风险反推控制计划草案。
  - 缺直接规格/测量/频次时自动生成 draft control intent 和风险控制建议，并保留 `inferred_fields`。
  - CP 行保留 `ai_inferred`、`ai_reasoning`、confidence、PFMEA 风险来源字段和 evidence refs。
- 质量门口径调整：
  - 普通行级 AI 草案保留在 `ai_inferred_items` 中，继续阻断 final export。
  - 普通行级 AI 草案不再逐条生成 manual review 噪音。
  - 高风险、特殊特性、低 confidence、证据不足或 AI 明确不确定的行仍进入人工复核。
- 已由子代理分别完成 PFMEA 与 CP/质量门子任务，主代理完成整合审核。

## 验证
- `python -m pytest tests/test_ai_drawing_three_table_workflow.py tests/test_generate_pfmea_stage.py tests/test_generate_control_plan_stage.py -q`：30 项通过。
- `python -m unittest tests.test_quality_audit tests.test_review_patch tests.test_export_modes tests.test_generated_chain_stage -v`：26 项通过。
- 首次完整回归发现人工复核后 final export 仍被 CP 行级 `ai_inferred_items` 阻断；已修复 `apply-review`，确认 PFMEA/CP 行后会同步清理对应 AI 推断标记。
- `python -m unittest tests.test_review_patch tests.test_input_package tests.test_phase6_pilot_workflow -v`：20 项通过。
- `python -m pytest tests/platform/test_apply_review.py tests/platform/test_exports.py -q`：5 项通过。
- `python -m unittest discover -s tests -v`：256 项全部通过。
- `python -m pytest tests/platform -q`：27 项全部通过。

## 三类真实样本离线重算
未重新调用真实 AI，只用已存在的三类真实结果 JSON 套用新的 PFMEA/CP 推理逻辑：
- `stamping_1004258_fix1`：PFMEA 8 -> 23，CP 8 -> 23，manual review 122 -> 49，final export 仍阻断。
- `hinge_JLH01000300`：PFMEA 10 -> 29，CP 10 -> 29，manual review 203 -> 71，final export 仍阻断。
- `limiter_XWQ01000100`：PFMEA 8 -> 21，CP 8 -> 21，manual review 112 -> 47，final export 仍阻断。

## AI 风险条数规则修正
- 已完成：去掉 `infer_pfmea_from_process_flow` 中的 5 条风险截断，保留去重但不再裁剪有效风险。
- 已完成：把三表端到端和 PFMEA 推理测试中的“最多 5 条”断言改为“同一工序 failure_mode 不重复”。
- 待验证：重新运行 AI 三表工作流测试、完整 unittest 和 platform pytest。

## Responses 流式与图纸预处理修正
- 已完成：确认 `allinai7.cloud` 的关键差异不是 URL/key，而是 Codex 请求里带了 `store:false`、`reasoning.effort=high` 和 Codex 风格 User-Agent。
- 已完成：`AIProviderConfig` 已增加 `store`、`reasoning_effort`、`user_agent`，`ai-config` 会显示这些非敏感字段。
- 已完成：`OpenAIResponsesMultimodalDrawingAnalyzer` 现在默认发送 `stream:true`，并解析 Responses SSE 事件。
- 已完成：新增 streaming parser 单测，覆盖 delta 拼接和 failed event 报错。
- 已验证：`python -m unittest tests.test_ai_config tests.test_openai_multimodal_adapter -v` 通过。

## 中文交付与复核清单聚合
- 已完成：将三表草案 warning 改为中文。
- 已完成：`manual_review.items` 改为中文分组摘要，并新增 `raw_items`、`raw_count`、`summary` 保存完整明细。
- 已完成：限位器真实结果离线重算后，用户可见复核项从 107 条合并为 5 类中文摘要，完整 107 条明细仍保留。
- 已完成：三表结果 envelope 增加 `status_display`，CLI 输出、桌面完成状态、桌面导出摘要和人工复核页默认展示中文摘要，不再把 `raw_items` 直接铺给用户。
- 已完成：统一三表工作簿导出时，“人工复核清单”可接收中文聚合摘要；质量门页保留“明细复核项数”作为内部审计指标。
- 已验证：`python -m pytest tests/test_ai_drawing_three_table_workflow.py tests/test_demo_acceptance.py tests/test_schemas.py -q` 通过。

## 人机协同三表编辑器第一版
- 已完成：新增 `edit_patch` core 能力，支持三表行 add/update/soft_delete/confirm。
- 已完成：编辑后的正式导出增加逐行确认门禁；未软删除行未确认时阻断 final export。
- 已完成：软删除行继续保留在结果 JSON 和 edit_history 中，但导出工作簿时过滤。
- 已完成：桌面 PFD/PFMEA/CP 页面改为 QTableWidget，可添加行、软删除、确认行并保存为 edit_patch。
- 已完成：桌面服务层保存 original/current/edit_patch，支持回读运行记录后继续编辑。
- 已完成：桌面导出页增加草案/正式导出入口，并展示质量门结果。
- 已完成：桌面 PFD 表格补齐工序目的/过程功能、产品特性、过程特性、设备、工装、检具、文件、流程类型、证据、待确认等关键列。
- 已完成：桌面 PFMEA 表格显示继承自 PFD 的工序名称、过程功能、产品/过程特性，方便逐行审核风险来源。
- 已完成：桌面 CP 表格显示 PFMEA 来源、失效模式、特性、规格、测量方法、频次、反应计划、检具等控制字段。
- 已完成：未发生新增、修改、软删除或确认时，保存按钮提示“无需保存”，不提交空 `edit_patch`。
- 已验证：`python -m pytest tests/test_edit_patch.py tests/test_desktop_table_editor.py tests/test_desktop_shell.py tests/test_qt_app_helpers.py tests/test_schemas.py -q` 通过。

## Core 三表联动实现
- 已完成：`ProcessStep` 增加工序目的、产品特性、过程特性、设备、工装、检具、文件、流程类型等字段，并兼容旧 fixture。
- 已完成：PFD 生成保留上述字段；图纸推理 PFD 也同步传递这些字段。
- 已完成：PFMEA 从 PFD/候选包继承工序编号、名称、功能、产品/过程/特殊特性，并丢弃不属于 PFD 的孤儿候选。
- 已完成：CP 生成保留 `source_pfmea_id`、PFMEA 失效原因、预防/探测控制、特殊特性和高风险来源。
- 已完成：质量门/validate 增加三表一致性检查，覆盖 PFD 工序无 PFMEA 风险、高风险 PFMEA 无有效 CP、特殊特性未贯穿、CP 工序不在 PFD、检具/频率/反应计划缺失。
- 已验证：`python -m unittest tests.test_generate_pfd_stage tests.test_generate_pfmea_stage tests.test_generate_control_plan_stage tests.test_stage_result -v`：68 项通过。

## MINOS-CORE v1.5 AIAG-VDA PFMEA 专业化增强
- 已完成：新增 `aiag_vda_pfmea`，支持 AIAG-VDA PFMEA 字段归一化、AP 计算和 RPN 辅助计算。
- 已完成：PFMEA 生成链路输出 AIAG-VDA 风格字段，包括过程项、过程步骤、过程工作要素、功能/要求、推荐措施、责任人、目标日期、措施状态、措施后 S/O/D/AP 等。
- 已完成：新增 `action_closure`，检查高 AP 推荐措施、中高 AP 责任人/目标日期、逾期状态和措施后评价完整性。
- 已完成：新增 `change_management`，支持字段级 diff、PFD/PFMEA/CP 变更影响分析和未处理影响阻断。
- 已完成：新增 `knowledge_recommendation`，提供轻量本地知识库规则推荐；推荐项必须人工采纳或填写忽略原因，不能自动成为正式结论。
- 已完成：扩展 `edit_patch`，支持 `accept_recommendation`、`ignore_recommendation`、`resolve_change_impact`，并记录字段级 before/after 审计历史。
- 已完成：扩展质量门，v1.5 正式导出会检查 AP 措施闭环、变更影响和知识库推荐处理。
- 已完成：拆分严格门范围，`strict_three_table_linkage` 只管三表一致性，`strict_aiag_vda_pfmea_gate` 才启用 v1.5 专业严格门，避免旧 fixture 和 legacy 导出被误伤。
- 已完成：桌面 PFMEA 表格和三表 Excel 导出补齐 AIAG-VDA 关键字段，表头和用户可见说明保持中文。
- 已完成：知识库推荐在用户可见 `manual_review.items` 中归并到 PFMEA 复核摘要，完整明细仍保留在 `raw_items`。
- 已验证：`python -m pytest tests/test_aiag_vda_v15.py tests/test_desktop_table_editor.py tests/test_edit_patch.py -q`：19 项通过。
- 已验证：`python -m pytest tests/test_ai_drawing_three_table_workflow.py tests/test_generate_pfmea_stage.py tests/test_generate_control_plan_stage.py tests/test_desktop_table_editor.py -q`：42 项通过。
- 已验证：`python -m pytest tests/test_aiag_vda_v15.py tests/test_edit_patch.py tests/test_quality_audit.py tests/test_review_patch.py tests/test_stage_result.py tests/test_apqp_rebuild_contract.py tests/test_export_modes.py tests/test_legacy_excel_adapter.py -q`：60 项和 7 个 subtests 通过。
- 已验证：`python -m unittest discover -s tests -v`：290 项全部通过。

## MINOS v1.6 桌面专业闭环
- 已完成：桌面导航新增“措施管理”“变更影响”“知识库推荐”三个中文页面。
- 已完成：PFMEA 页面新增筛选入口，覆盖 AP 高、AP 中、逾期、待措施、待措施后评价、待确认、知识库推荐待处理和变更影响待处理。
- 已完成：`table_editor` 增加 UI-neutral helper，可把三表结果转换为措施管理行、变更影响列表和知识库推荐列表，并生成推荐/变更处理 patch item。
- 已完成：桌面 SQLite 增加 `knowledge_rules` 表，自动写入默认知识库规则，支持查看、新增、停用和从推荐沉淀本地规则。
- 已完成：桌面服务层新增 `handle_recommendation` 和 `resolve_change_impact`，推荐采纳/忽略、变更处理/忽略都统一走 `edit_patch`。
- 已完成：修正桌面运行记录的累计 patch 保存和回读，关闭后重新加载仍能拿到完整 edit_patch。
- 已完成：Qt 知识库推荐页支持采纳、忽略、沉淀为知识库；变更影响页支持标记已处理和忽略，忽略时要求填写原因。
- 已验证：`python -m pytest tests/test_desktop_table_editor.py tests/test_desktop_shell.py tests/test_edit_patch.py tests/test_aiag_vda_v15.py -q`：33 项通过。
- 已验证：`python -m pytest tests/test_ai_drawing_three_table_workflow.py tests/test_generate_pfmea_stage.py tests/test_generate_control_plan_stage.py tests/test_qt_app_helpers.py tests/test_export_modes.py tests/test_legacy_excel_adapter.py -q`：44 项和 3 个 subtests 通过。
- 已验证：`python -m unittest discover -s tests -v`：294 项全部通过。
- 已验证：`python -m minos_desktop.cli --smoke --output-dir out\desktop_acceptance\preflight --db-path out\desktop_acceptance\preflight\minos_desktop.sqlite3`：`status=ready`。

## MINOS v1.7 导出与验收实现
- 已完成：聚焦 `minos_core/exporters/*`、`edit_patch` 导出入口和导出/acceptance 测试，不改桌面 UI。
- 已完成：APQP/PFMEA 导出列顺序按 AIAG-VDA 审核顺序打磨，三表拆分导出增加草案首行显眼标记。
- 已完成：正式统一工作簿新增“正式导出审计”页，汇总质量门、人工确认、manual_review、edit_patch 历史和软删除摘要。
- 已完成：编辑后正式导出会把软删除摘要写入导出链路 metadata，表格行继续过滤软删除项，审计页保留摘要。
- 已完成：补充 final export 阻断、正式审计页内容、草案标记和 xlsx zip 可打开测试。
- 已验证：`python -m pytest tests/test_export_modes.py tests/test_edit_patch.py tests/test_ai_drawing_three_table_workflow.py tests/test_demo_acceptance.py tests/test_apqp_rebuild_contract.py -q`：45 项通过。
- 已验证：`python -m pytest tests/test_legacy_excel_adapter.py -q`：1 项和 3 个 subtests 通过。
- 已验证：`python -m pytest tests/test_export_modes.py tests/test_demo_acceptance.py -q`：9 项通过。

## MINOS v1.8.1 子任务 B：真实 API 与端到端验收入口
- 已新增 `tests/acceptance/test_real_api_acceptance.py`。
- 默认运行时，未设置 `MINOS_RUN_REAL_ACCEPTANCE=1` 会跳过真实验收，不访问外网。
- 显式设置 `MINOS_RUN_REAL_ACCEPTANCE=1` 后，会要求真实 API key 和 `MINOS_REAL_DRAWING_PATH`；缺失时用失败暴露配置问题，不跳过。
- 验收入口复用 `OpenAIResponsesMultimodalDrawingAnalyzer` 和 `generate_three_tables_from_drawing(...)`，并检查 Responses payload 的 `stream=true`。
- 验收入口覆盖真实图纸生成 PFD/PFMEA/CP、统一三表工作簿、三份独立 Excel、AI 预审和 AIAG-VDA 正式审计页结构。
- 已验证：`python -m unittest discover -s tests\acceptance -v`：1 项跳过，符合默认不触网策略。
- 已验证：`python -m py_compile tests\acceptance\test_real_api_acceptance.py`：通过。

## MINOS v1.8.1 子任务 B 待真实运行
/// 1. 设置 `MINOS_RUN_REAL_ACCEPTANCE=1`。
/// 2. 配置 `MINOS_OPENAI_API_KEY` / `OPENAI_API_KEY` / `ARK_API_KEY`，或确保 Codex auth 可用。
/// 3. 设置 `MINOS_REAL_DRAWING_PATH` 指向授权可用于验收的真实 PDF/PNG/JPG 图纸。
/// 4. 可选设置 `MINOS_REAL_ACCEPTANCE_OUTPUT_DIR` 指定输出目录。
/// 5. 运行 `python -m unittest discover -s tests\acceptance -v`。

## MINOS v1.8.1 子任务 C：静默错误与覆盖缺口
- 已完成：`domain.from_mapping` 对非 mapping 输入统一抛出 `TypeError`，不再把非 dict 静默变成空对象。
- 已完成：`drawing_analysis` 对不可解析的 `confidence` 记录 `confidence_parse_errors`，并通过质量门和人工复核项暴露。
- 已完成：桌面 AI 预审纳入 `quality_gate.review_issues`，同一目标行去重时优先保留带 `issue_id` 的后端问题。
- 已补测试：domain mapping、drawing confidence parse、xlsx sheet 名、导出器 `quality_gate=None`、quality_matching、platform artifacts/utils、AI 预审空建议。
- 保留说明：桌面 UI/预检中的宽泛异常包装用于透明展示原始错误，本子任务未收窄。
- 已验证：`python -m pytest tests\test_domain_mapping.py tests\test_ai_drawing_three_table_workflow.py::AIDrawingThreeTableWorkflowTests::test_invalid_confidence_is_traceable_in_drawing_gate tests\test_export_modes.py tests\test_quality_matching.py tests\test_desktop_table_editor.py::DesktopTableEditorTests::test_automation_review_none_suggestion_does_not_generate_fix_patch tests\platform\test_artifacts_utils.py`：15 项通过。
- 已验证：`python -m pytest tests\test_desktop_table_editor.py`：23 项通过。

## MINOS v1.9 三表联动 + FMEA 知识库增强

- 已完成：第 0 步 — 流程文档更新，project_flow.mmd 已加入 linkage/registry/knowledge/baseline 新节点。
- 已完成：第 1 步 — `minos_core/three_table_linkage.py`（build_three_table_linkage_map / evaluate_three_table_linkage / find_linkage_gaps），14 项测试。
- 已完成：第 2 步 — `quality_gates/__init__.py` 接入 linkage gaps，`StageQualityGate` 新增 linkage_gaps/linkage_summary 字段，linkage blocker 阻止 final export。4 项新测试。
- 已完成：第 3 步 — `minos_core/characteristic_registry.py`（build_characteristic_registry / attach_characteristics_to_three_tables），15 项测试。
- 已完成：第 4 步 — `configs/knowledge/fmea_rules.zh-CN.json`（16 条结构化规则，覆盖冲压/焊接/铆接/装配/涂油/表面处理/热处理/检验/包装/特殊特性/高AP/注塑等）。`knowledge_recommendation.py` 增强：新增 process_terms/characteristic_terms/risk/rating_hint/recommended_controls 匹配，多维度推荐拆分。22 项新测试。
- 已完成：第 5 步 — `edit_patch.py` 增强 accept_recommendation（写入 suggested_fields 到目标行 + linked_control_plan_suggestion 到 CP 行，不覆盖已有字段）。9 项新测试。
- 已完成：第 6 步 — `change_management.py` 新增 compare_three_table_baseline 和 analyze_linked_change_impacts。20 项新测试。
- 已完成：第 7 步 — `pipeline.py` 的 generate_three_tables_from_drawing 输出包含 linkage_map/linkage_gaps/characteristic_registry/knowledge_recommendations。`__init__.py` 新增 7 个公开导出。

### 最终测试结果
- 完整回归：**541 通过，48 subtests 通过，7 失败**
- 7 项失败均为预存问题（2 项 AI 绘图工作流、4 项 input_package、1 项 phase6 pilot），与本次改动无关
- 新增约 100 项测试全部通过
- 旧测试零退化（0 项由本次改动导致的失败）

## MINOS v1.9.1 三表联动与 FMEA 知识库稳定化

- 进行中：步骤一 — 更新基线文档。
- 待开始：步骤二 — 修回归问题（trace link、pyproject.toml、PFMEA 阈值）。
- 待开始：步骤三 — 三表联动强化（孤儿 CP blocker、异常不吞）。
- 待开始：步骤四 — 知识库接入主流程（默认 JSON、拆分推荐字段、空值判断）。
- 待开始：步骤五 — 特性注册表贯穿三表。

## MINOS v1.10 工程试用打磨目标

- 已确定：短期优先借鉴 Relyence PFMEA 的三表联动、行级追溯和正式导出强门；中期吸收 APIS IQ-Software 的结构化 FMEA 知识复用、评分目录和失效链沉淀。
- 已确定：MINOS 定位不是复制传统 FMEA 软件，而是 AI 图纸/旧表/知识库驱动的三表草案与复核工作台。
- 待开始：修正式导出旁路。`export_mode="final"` 且质量门不允许时，不得生成看起来像正式文件的 workbook；桌面端必须显示阻断原因和待处理清单。
- 待开始：集中清零 known failures，补齐 final export 旁路、generated/human-edited evidence bypass、platform final export、split workbook final mode 的回归测试。
- 待开始：把人工复核页从只读摘要升级为可处理任务清单，支持分组、跳转目标行、处理后刷新状态。
- 待开始：把 `linkage_map` 做成桌面联动视图，按 PFD 工序展示 PFMEA 风险、CP 控制、gap 和特殊特性贯穿状态。
- 待开始：把 `characteristic_registry` 升级为特性主数据页，支持查看特性来源、挂接状态和人工修正后回写三表。
- 待开始：增强 Excel 追溯矩阵，展示 PFD->PFMEA->CP 链路、gap、确认状态、软删除摘要和知识推荐处理状态。

### v1.10 路线估计
- 1-2 周目标：达到可控开发内测，核心是正式导出强门、复核任务化、联动跳转和回归清零。
- 3-5 周目标：达到工程试用，核心是联动工作台、特性主数据、PFD 变更影响、CP 补行建议和真实脱敏样例回归。
- 2-3 个月目标：推进 APIS 式知识复用，包括 FMEA 模块库、S/O/D/AP catalog、相似模块推荐、功能链/失效链和采纳后知识沉淀。

## V1.9.1 收口状态

- 已完成三个修复：
  1. registry 提前挂接 -- PFD->PFMEA->CP 每步生成后立即用 attach_characteristics_to_three_tables 挂接特性。
  2. envelope 顶层三表与 chain 一致 -- process_flow/pfmea/control_plan 和 chain 内部使用同一份已挂接数据。
  3. apply-review/final export 恢复 -- ai_inferred_item 汇总确认项可用，平台测试恢复通过。
- 全量回归：588 passed, 1 skipped, 48 subtests passed。

## V1.10 Professional Three-Table Review Loop

- 进行中：工作包 A -- 基线收口。
- 待开始：工作包 B -- sync_snapshot / sync_issues。
- 待开始：工作包 C -- risk_structure 风险结构视图。
- 待开始：工作包 D -- recommendation lifecycle。
- 待开始：工作包 E -- review_dashboard。
- 待开始：工作包 F -- final export gate 收紧。
- 待开始：工作包 G -- 桌面端最小接入。
- 待开始：工作包 H -- 文档验收。

## V1.12 Knowledge Reuse and Action Closure Loop

- 进行中：工作包 A — 基线记录。
- 进行中：工作包 B — 本地知识库 v2（knowledge_base.py）。
- 待开始：工作包 C — 知识推荐接入 v2。
- 待开始：工作包 D — 推荐应用动作拆分。
- 进行中：工作包 E — PFMEA 行动项对象（action_tracking.py）。
- 待开始：工作包 F — 行动项写入与刷新。
- 待开始：工作包 G — resolve_action_item patch。
- 待开始：工作包 H — 质量门和 dashboard 收紧。
- 待开始：工作包 I — 桌面端最小闭环。
- 待开始：工作包 J — Excel 导出增强。
- 待开始：工作包 K — 文档验收。

## V1.13 Tauri + React Apple 风格桌面工作台

- 已完成：作为子代理 C，新增 OpenSpec 变更 `v1.13-tauri-apple-desktop`，记录 Define / Specify / Implement / Verify 四步闭环。
- 已完成：明确 V1.13 桌面迁移目标为 Tauri + React + Apple 风格桌面工作台。
- 已完成：明确 PySide6 冻结为 legacy，不作为新能力主路径。
- 已完成：明确 `minos_core` 不引入前端依赖。
- 已完成：明确 `minos_platform` 不作为本次桌面主后端。
- 已完成：把 V1.13 开发步骤按 `///` 风格写入 `task_plan.md` 和 OpenSpec tasks。
- 已完成：把 V1.13 工作流同步到 `project_flow.mmd`。
- 已完成：安装并验证前端依赖，`npm run build` 通过。
- 已完成：安装 Rustup、Visual Studio Build Tools C++ 工具链，并验证 Tauri/Rust `cargo check` 通过。
- 已完成：补齐 Tauri 标准 Rust 结构，新增 `src-tauri/src/lib.rs`，`main.rs` 保持薄入口。
- 已完成：补齐 Windows resource 所需 `src-tauri/icons/icon.ico`。
- 待实现：Tauri + React 桌面壳。
- 待实现：图纸选择、三表生成、三表编辑、联动预览刷新、闭环任务处理和导出入口。
- 待验证：1280x800 下主要控件和文字无重叠。

### 明确验收
- 图纸可选择。
- PFD、PFMEA、CP 三表可生成。
- PFD、PFMEA、CP 三表可编辑。
- 联动预览可刷新。
- 复核、知识推荐、行动项等闭环任务可处理。
- 导出可用，草案/正式边界清楚。
- 1280x800 下主要控件和文字无重叠。

## V1.14 Drawing Knowledge Linkage Closure

- 已启动：V1.14 文档与流程 worker 建立图纸识别、知识复用、三表联动、行动闭环的文档基线，后续交由主代理审核。
- 已完成：确认 OpenSpec 变更目录为 `openspec/changes/v1.14-drawing-knowledge-linkage-closure`。
- 已完成：V1.14 范围锁定为图纸事实层、知识复用对象、PFD -> PFMEA -> CP 联动视图、行动项闭环和正式导出质量门。
- 已完成：V1.14 非目标锁定为不重写视觉引擎、不接外部系统、不自动批准 AI 推荐、不替换现有三表顶层 schema。
- 已完成：三个 XLSX 种子族已转换为本地零件族知识包，默认索引包含 `stamping`、`limiter`、`door_hinge`。
- 已完成：新增零件族分类、PFD 族上下文推导、PFMEA/CP 知识推荐评分与去重、统一闭环任务、V1.14 desktop API。
- 已完成：补齐 `/api/knowledge/families` 和 `/api/knowledge/import-seeds`，桌面端版本同步为 `1.14.0`。
- 已完成：修正 FMEA V2 知识库规则验收口径，默认规则集为 58 条 active 规则，不再沿用旧 16 条硬编码。
- 已完成：修正 `KR-HIGH-AP-REACTION-015`，增加 `requires_high_ap`，并把全局高 AP 推荐类型独立为 `high_ap_*`，避免挤掉具体工艺规则。
- 已验证：V1.14 定向测试 `26 tests OK`。
- 已验证：知识库相关测试 `54 tests OK`。
- 已验证：全量 Python 单元测试 `711 tests OK`。
- 已验证：Tauri 前端 `npm run build` 通过。
- 已验证：Tauri/Rust `cargo check` 通过。
- 待人工验收：用真实图纸在 Tauri 桌面端跑完整链路，确认真实 GPT 图纸识别、零件族确认、PFD 预览、三表编辑、闭环处理和正式导出体验。

## V1.14.1 OCR-first Drawing Analysis

- 当前状态：V1.14.1 OCR-first / hybrid 图纸分析计划已收口到代码、桌面 API、Tauri UI 和定向验收。
- 基于状态：V1.14 已具备图纸事实、零件族知识、三表联动、行动闭环和正式导出门；V1.14.1 不推翻这些能力，只补稳定的图纸入口。
- 已完成：新增 OpenSpec 变更目录 `openspec/changes/v1.14.1-ocr-first-drawing-analysis`。
- 已完成：proposal/design/tasks 已说明 OCR-first/hybrid 目标、非目标、执行步骤和验收标准。
- 已完成：`task_plan.md` 已追加 V1.14.1 可执行计划，所有开发步骤使用 `///` 前缀。
- 已完成：`findings.md` 已记录 GPT 视觉 `stream_read_error` 不能导致整体失败，以及 OCR 结果必须可追溯的原因。
- 已完成：`project_flow.mmd` 已追加 PDF 渲染、PDF 文字层、RapidOCR、OCR `drawing_analysis`、可选 AI 增强、零件族、PFD、三表、闭环、导出门节点。
- 已完成：`minos_core/adapters/ocr.py` 提供 PDF 文字层、RapidOCR 和 auto composite OCR adapter，OCR block 保留 page、bbox、confidence、engine、source_ref。
- 已完成：`minos_core/drawing_ocr_analysis.py` 提供 `analyze_drawing_with_ocr(...)` 公开入口，并把 OCR page/block 转成可追溯 `drawing_analysis_bundle`。
- 已完成：`generate_three_tables_from_drawing(...)` 支持 `analysis_mode=hybrid|ocr_only|vision_only` 和 `ocr_engine=auto|pdf_text|rapidocr`，hybrid 下 AI 视觉 `stream_read_error` 会记录为 analysis error 并保留 OCR 草案。
- 已完成：桌面 API `/api/projects` 接收并存储 `analysis_mode`、`ocr_engine`，`DesktopRunService` 创建运行时传给 pipeline。
- 已完成：Tauri/React 图纸导入页已加入识别模式选择，默认 hybrid，并把 `analysis_mode`、`ocr_engine="auto"` 写入项目 context。
- 已完成：图纸识别状态区显示 OCR 状态、AI 视觉状态、识别来源和待确认字段数量；`stream_read_error` 主文案改为“AI 视觉识别中断，已保留 OCR 识别结果。”。
- 已验证：OCR drawing analysis 覆盖 OCR-only 结构、PDF 文字层 fake fitz、RapidOCR 缺依赖清晰错误、公开 OCR 入口可追溯。
- 已验证：pipeline OCR-first 覆盖 OCR-only 进入三表、hybrid `stream_read_error` 保留 OCR 草案、draft 导出保留 OCR/AI 复核警示、final export 继续阻断。

## V1.14.2 Title Block Family Knowledge

- 当前状态：已启动图框优先零件族识别修正，目标是让“整件名称”优先于“衬套”等局部组件词。
- 已完成：新增 OpenSpec 变更目录 `openspec/changes/v1.14.2-title-block-family-knowledge`。
- 已完成：proposal/design/tasks 已明确标题栏强证据、OCR 无标签图框提取、三类零件族线索和验收标准。
- 已完成：`task_plan.md` 已追加 V1.14.2 可执行计划，开发步骤使用 `///` 前缀。
- 已完成：`part_family_classifier.py` 增加字段权重、标题栏优先、长词优先和组件词降权；“衬套/bushing/轴套”不再能单独把图纸判为门铰链。
- 已完成：`drawing_ocr_analysis.py` 增加无标签标题栏提取，可从“图号 + D00R HIMGE/尾门较链”这类短行提取零件名并保留 OCR block evidence。
- 已完成：`adapters/multimodal.py` 的视觉提示已强化图框优先，要求区分整件零件名和局部组件。
- 已完成：`configs/knowledge/fmea_rules.zh-CN.json` 新增门铰链、限位器、冲压薄板特征三条规则，并收窄冲压规则避免抢掉旧孔径规则。
- 已完成：`pipeline.py` 在 hybrid 视觉成功后加入 OCR 身份锁定；高置信 OCR 标题栏会写回最终 `drawing_identity`，合并 OCR evidence，并把 `door_hinge` 等零件族锁定到 `metadata.locked_part_family_classification`。
- 已验证：标题栏尾门铰链压过衬套、单独衬套不判门铰链、OCR 无标签图框抽取、知识规则加载。
- 已验证：hybrid 测试覆盖“视觉把整件名写成衬套，但 OCR 标题栏为尾门较链”场景，最终保留 OCR 整件身份和 `door_hinge` 零件族。
- 已验证：V1.14.2 定向测试 `48 tests OK`，相邻族上下文/PFD/知识推荐测试 `9 tests OK`，知识库 JSON 可解析。

## V1.14.3 Process Inference Knowledge Integration

- 当前状态：已把用户新增的 `configs/knowledge/process_inference` 从静态文件接入默认零件族知识加载和 PFD 推导。
- 已完成：删除偏系统级/方法论级规则 `KR-STAMPING-AP-METHODOLOGY-063`、`KR-DOOR-SYSTEM-INTEGRATION-FMEA-066`，默认 FMEA 规则从 80 条降为 78 条。
- 已完成：`part_family_knowledge.py` 默认加载 `door_hinge`、`limiter`、`stamping` 时会读取同族 `process_inference/*.json`，并把 `process_flow_variants` 转成 `process_route_templates`。
- 已完成：`drawing_to_pfd.py` 会根据图纸文本从多个工艺变体里选择最匹配的一条，避免把同族所有工艺路线一次性展开。
- 已完成：PFD 保留 `process_inference` 细工序名，不再统一压成“焊接/铆接”等泛化名称。
- 已验证：`fmea_rules.zh-CN.json` 和三类 `process_inference` JSON 均可解析。
- 已验证：知识库/PFD/推荐/分类/pipeline 族上下文定向测试 `59 tests OK`。

## V1.14.4 Desktop Interaction State Hardening

- 当前状态：已修复桌面端主要交互状态串台问题，重点覆盖没导入图纸误生成、导入后界面阻塞、按钮空点、最近结果污染当前项目。
- 已完成：新版工作台启动自动恢复最近结果时只做只读展示，不再写入 `current_project_id`；用户必须导入图纸或点击“打开最近项目”才可生成。
- 已完成：生成入口统一校验图纸路径、文件存在、文件类型；路径失效时不会先显示“生成中”。
- 已完成：生成任务使用 `GenerationWorker` + `QThread` 后台执行，运行中锁住导入、生成、打开最近、编辑、保存和导出入口。
- 已完成：新导入图纸会清空旧运行结果；生成失败后顶部状态改为“失败”，项目页/图纸页保留真实图纸和失败状态。
- 已完成：项目页、图纸页、设置页从静态假状态改为可刷新状态；设置页默认输出目录可真实保存到 SQLite settings。
- 已完成：空回调按钮默认禁用；三表状态筛选真实生效且不改变源行号；复核页“查看来源证据”不再误连“跳转三表”。
- 已完成：横向补齐导出质量门英文键读取，正式导出未放行时桌面入口提前阻止；只读恢复结果显示“仅查看”；设置页和复核闭环按钮纳入运行中锁；三表筛选识别真实编辑元字段；导出页同时统计待确认项和质量门问题。
- 已完成：Tauri 图纸导入页改为常驻挂载，切到三表、评审、导出或设置页面时只隐藏导入页，不卸载生成中的链式会话状态。
- 已完成：新增 `tests/test_desktop_tauri_app_state.py`，防止后续把 `DrawingImportPage` 改回条件卸载。
- 已验证：桌面相关测试与相邻 UI 模型/表格编辑测试 `63 tests OK`，相关 UI 文件 `py_compile` 通过，桌面窗口可启动。
- 已验证：Tauri App 状态回归测试 `1 test OK`，Tauri 前端 `npm run build` 通过，Tauri/Rust `cargo check` 通过。

## V1.14.5 Staged Three-table Confirmation

- 当前状态：桌面主生成路线已从“一次性生成 PFD/PFMEA/CP”收口为“AI 推理 PFD -> 人工确认 -> AI 推理 PFMEA -> 人工确认 -> AI 推理 CP”。
- 已完成：新增 `analyze_drawing_for_three_table_chain(...)`，链式启动只做图纸识别，不再先后台跑完整 `generate_three_tables_from_drawing(...)`。
- 已完成：链式 PFD 推理失败会落库为失败状态并展示原始错误，不再静默 fallback 到模板 PFD。
- 已完成：链式文本 LLM 统一走 Responses API，结构化输出使用 Responses `text.format=json_schema`，避免图纸识别能跑但 PFMEA/CP 生成走错接口。
- 已完成：图纸识别得到的零件族和 `process_inference` 路线摘要会传入 PFD 推理上下文。
- 已完成：编辑 PFD 会清空 PFMEA/CP 并把下游阶段重置为未开始；编辑 PFMEA 会清空 CP 并要求重新生成/确认。
- 已完成：Tauri 图纸导入页移除“一次性生成”切换，开始生成固定进入链式确认流程。
- 已完成：旧兼容接口 `POST /api/projects/{id}/runs`、`jobs.run_project(...)`、`DesktopRunService.run_project(...)` 已全部收口到链式流程，不再触发一次性三表生成。
- 已完成：Tauri API client 删除旧 `createProjectRun(...)` 导出，前端只保留 `startChainRun(...)` 作为生成入口。
- 已完成：链式阶段确认/重生成失败会把原始错误写回 run；链式状态会随 DB 和磁盘结果一起保存，避免重开后丢失阶段状态。
- 已完成：确认 PFD/PFMEA/CP 时会同步清除对应表行的待确认标记；失败后重生成成功会清掉旧失败状态。
- 已完成：文本 LLM 链路默认不再继承 Codex 的 `xhigh` 推理强度，PFD/PFMEA/CP JSON 生成默认使用 `high`，可用 `MINOS_TEXT_LLM_REASONING_EFFORT` 覆盖。
- 已完成：文本 LLM 读取超时从裸 `The read operation timed out` 改为明确的 PFD/PFMEA/CP 文本模型响应超时，并支持 `MINOS_TEXT_LLM_TIMEOUT_SECONDS` 调整。
- 已完成：Tauri 导入页根据返回的 `chain_stages.pfd.status` 和 `failure_message` 显示真实状态，不再把 PFD failed 固定显示成“PFD 已生成”。
- 已完成：Tauri 三表工作台默认先看 PFD，选中 PFD 行即可直接确认；如输入框有修改，会把修改作为 `edit_patch` 随确认一起提交。
- 已完成：链式确认接口在确认时应用上游修改会同步执行下游失效规则，避免 PFD 修改后继续保留旧 PFMEA/CP 阶段或旧 CP 行。
- 已完成：PFD 数据从工艺路线清单升级为标准过程流程图字段，PFD LLM/schema、规则推导和桌面表格均包含流程类型、流程符号、输入、输出、前序和后续工序。
- 已完成：`normalize_process_flow_steps` 只在缺失流向时补线性默认；如果知识库或 LLM 已给出分支、返工或外协回路，会保留已有 `previous_step_ids` / `next_step_ids`。
- 已完成：Tauri PFD 视图新增节点+箭头流程图，并用标准流程符号区区分加工、检验、运输、存储、返工和外协；点击节点可回选对应 PFD 行。
- 已完成：清除 PFD 图残余风险。Tauri PFD 图现在通过 `buildProcessFlowLayout` 从 `next_step_ids` 生成 SVG 拓扑边，并用 `data-edge-kind` 区分 `sequence`、`branch`、`backlink`、`rework`，不再只按数组相邻节点横向画箭头。
- 已验证：`python -m pytest tests/test_ai_drawing_three_table_workflow.py -q`：22 项通过。
- 已验证：`python -m pytest tests/test_desktop_tauri_app_state.py -q`：5 项通过。
- 已验证：`python -m pytest tests/test_desktop_table_editor.py -q`：23 项通过。
- 已验证：`python -m pytest tests/test_desktop_shell.py tests/test_desktop_api_sidecar.py tests/test_desktop_api_ocr_mode.py -q`：29 项通过。
- 已验证：`python -m pytest tests/test_desktop_tauri_app_state.py tests/test_ai_drawing_three_table_workflow.py tests/test_desktop_table_editor.py -q`：50 项通过。
- 已验证：`python -m py_compile minos_core/drawing_to_pfd.py minos_core/pipeline_chain.py minos_desktop/table_editor.py`：通过。
- 已验证：Tauri 前端 `npm run build` 通过。
- 已验证：同一张 `JLV03000500_001_AC_RR DH ASSY.pdf` 真实 API 链式重跑成功，`run #13` 生成 PFD `12` 行，`8` 项待确认，耗时约 `103` 秒，无 `failure_message`。

## V1.14.6 PFMEA 来源与 PFD 一致性修复

- 当前状态：已完成 PFD -> PFMEA 链路修复，PFMEA 不再接受与确认后 PFD 不一致的工序编号和工序名称。
- 已完成：`normalize_process_flow_steps` 不再把 `default_input_material` 插入为 `P05` 物料伪工序；物料名只补到首道真实工序的 `input_material`。
- 已完成：链式 `generate_pfmea_from_confirmed_pfd` 会按确认 PFD 的 `process_step_id` 建立映射，PFMEA 行必须引用存在的 PFD 工序。
- 已完成：PFMEA 行强制继承 PFD 的 `operation`、`process_step_name`、`process_step`、`structure_process_step`、`function_process_step` 和 `function_requirement`，避免表格名称和流程图名称错位。
- 已完成：PFMEA 行缺少 `failure_mode` 或引用孤儿 PFD 编号时直接失败暴露，不生成“待工程人员填写失效模式”占位结果。
- 已完成：桌面联动同步不再把 PFD gap 自动应用成 PFMEA 占位行。
- 已完成：`live_linkage` 中 PFD 新增工序只提示“需要基于确认后的 PFD 重新推理 PFMEA”，不再生成 PFMEA stub add item。
- 已完成：`three_table_linkage` 不再为 PFD 缺 PFMEA gap 生成 add PFMEA 同步建议；CP 仍可从已有 PFMEA 派生同步建议。
- 已验证：`python -m pytest tests/test_ai_drawing_three_table_workflow.py::AIDrawingThreeTableWorkflowTests::test_llm_pfd_generation_normalizes_standard_process_flow_fields tests/test_ai_drawing_three_table_workflow.py::AIDrawingThreeTableWorkflowTests::test_normalize_process_flow_steps_does_not_create_material_pseudo_step tests/test_ai_drawing_three_table_workflow.py::AIDrawingThreeTableWorkflowTests::test_chain_pfmea_inherits_confirmed_pfd_process_fields tests/test_ai_drawing_three_table_workflow.py::AIDrawingThreeTableWorkflowTests::test_chain_pfmea_rejects_rows_not_from_confirmed_pfd -q`：4 项通过。
- 已验证：`python -m pytest tests/test_desktop_api_sidecar.py::test_linkage_sync_does_not_create_pfmea_placeholder_for_chain_run -q`：1 项通过。
- 已验证：`python -m pytest tests/test_live_linkage.py tests/test_three_table_linkage.py -q`：34 项通过。
- 已验证：`python -m pytest tests/test_ai_drawing_three_table_workflow.py tests/test_desktop_api_sidecar.py tests/test_desktop_table_editor.py tests/test_desktop_shell.py -q`：86 项通过。
- 已验证：`python -m pytest tests/test_ai_drawing_three_table_workflow.py tests/test_desktop_api_sidecar.py tests/test_live_linkage.py tests/test_three_table_linkage.py tests/test_desktop_table_editor.py tests/test_desktop_shell.py -q`：120 项通过。
- 已验证：`python -m py_compile minos_core/drawing_to_pfd.py minos_core/pipeline_chain.py minos_core/live_linkage.py minos_core/three_table_linkage.py minos_desktop/api/jobs.py`：通过。
- 已验证：`git diff --check`：通过。
- 已验证：Tauri 前端 `npm run build` 通过。

## V1.14.7 PFMEA 最新版格式修复

- 当前状态：正在把 PFMEA 从旧 RPN 风格收口到 AIAG-VDA FMEA Handbook First Edition 2019 的七步法 / PFMEA Form C 风格。
- 已完成：`normalize_pfmea_row` 统一补齐 `structure_process_item`、`structure_process_step`、`structure_work_element`、`function_process_item`、`function_process_step`、`function_work_element`、`preventive_action`、`detection_action`、`optimization_action`、`responsible_person`、`status`、`AP` 等字段。
- 已完成：PFMEA 归一化保留 `calculate_rpn` 作为旧模块兼容函数，但新版 PFMEA 行不再默认输出 `rpn` / `after_rpn`。
- 已完成：链式 PFMEA LLM prompt/schema 明确 AIAG-VDA 2019 AP 口径，删除旧 RPN 必填字段，增加结构分析、功能分析和优化措施字段。
- 已完成：规则生成路径 `infer_pfmea_from_process_flow` 和 `normalize_pfmea_rows` 复用新版归一化，避免规则路径和 LLM 路径字段不一致。
- 已完成：Tauri PFMEA 表格改为七步法分组字段：结构、功能、失效、风险和优化，不再显示旧 RPN 列。
- 已完成：统一/拆分三表导出的 PFMEA 表头移除 `RPN` 与 `措施后 S/O/D/AP/RPN`，改为 `措施后 S/O/D/AP`。
- 已完成：Tauri 启动自动恢复最近运行时跳过 `status=failed` 且 `blocked_stage=pfmea` 的旧失败运行，避免旧失败结果被误认为最新 PFMEA。
- 已完成：Tauri 三表工作台新增“重新生成失效模式分析”按钮，PFMEA 阶段失败时可直接基于确认后的 PFD 重试。
- 已完成：PFMEA 生成遇到 Responses `504 Gateway Time-out` 时会按临时上游错误重试，不再一次网关超时就直接失败；失败文案会明确提示“AI 上游模型或中转服务响应超时”。
- 已定位：run 20 的已确认 PFD 有 11 个工序；真实实验中 1 个 PFD 工序的 PFMEA 请求约 52.8 秒成功生成 4 行，2 个工序合并请求约 185 秒后被中转返回 504，说明主要根因是 PFMEA 批量请求过重，不是 PFD 内容错误或模型完全不可用。
- 已修复：链式 `generate_pfmea_from_confirmed_pfd(...)` 不再把整张确认 PFD 一次性发给文本 LLM，而是按每个 PFD 工序分别生成 PFMEA，再统一校验 `process_step_id`、继承 PFD 工序/功能/特性字段并汇总。
- 已修复：文本 Responses 请求默认带 `stream=true`，并复用 SSE 解析器读取 `response.output_text.delta` / `response.completed`；流式用于减少中转空闲超时风险，核心降负载仍靠按工序拆分。
- 已加固：单个 PFD 工序请求返回的 PFMEA 行必须匹配当前工序编号，不能串到另一个已确认工序；SSE 解析也兼容只有 `event:`、`data` 内无 `type` 的响应事件。
- 已验证：真实 run 20 单工序拆分 smoke 已跑通，11 个 PFD 工序生成 44 条 PFMEA 行，耗时约 557 秒，结果写入 `out/desktop/pfmea_per_step_smoke_run20.json`。
- 已验证：新增红灯回归测试覆盖后端 PFMEA Form C 字段、规则生成路径、导出表头、Tauri PFMEA 列、旧失败 run 自动恢复和 PFMEA 重生成入口。

## V1.14.8 PFD 排序与三表总审核收口

- 当前状态：已按用户反馈继续诊断 PFD 仍拖不动和 AI 审核时机问题，修复已完成并已重启发布版软件。
- 已修复：PFD 表格行保持整行可拖，同时拖拽手柄自身也可触发 drag start，降低 Tauri WebView 中表格行原生拖拽不稳定的影响。
- 已修复：PFD 左侧手柄改为 pointer 拖动兜底，不再和 HTML5 `draggable` 抢事件；拖出手柄/行区域后松手也会用 `elementFromPoint` 查找目标行。
- 已修复：PFD 排序不再因为搜索、风险或状态筛选而被整体禁用；排序保存会把可见顺序映射回完整 PFD 行顺序并写入 `sequence` patch。
- 已修复：PFD 手动排序保存现在同步重建线性 `previous_step_ids` / `next_step_ids`，避免上方流程图继续按旧连线显示错误箭头。
- 已新增：PFD 排序保留上移/下移按钮作为可靠兜底，按钮和拖拽都走同一 `onReorderPfdRows` 保存链路。
- 已修复：CP 确认后才生成 `automation_review`，其中写入 `review_stage=after_control_plan` 和 `human_decision_priority=True`。
- 已修复：旧 `batch_confirm_automation_review` 服务入口增加后端门禁；CP 未确认或没有 after-control-plan 审核结果时直接返回当前 run，不再改任何行。
- 已修复：桌面审核模型能读取 `automation_review.batch_confirm_candidates`，并让可批量确认候选优先于同目标普通人工任务。
- 已验证：新增服务层行为测试已先红后绿，覆盖 CP 未确认时不能执行 AI 批量确认、CP 确认后才允许基于三表总审核结果执行。
- 已验证：`python -m pytest tests/test_desktop_tauri_app_state.py -q`：22 项通过。
- 已验证：`python -m pytest tests/test_desktop_shell.py -q`：26 项通过。
- 已验证：`python -m pytest tests/test_automation_review.py -q`：4 项通过。
- 已验证：`python -m pytest tests/test_closure_tasks.py -q`：3 项通过。
- 已验证：`python -m pytest tests/test_desktop_table_editor.py tests/test_desktop_chain_state.py -q`：27 项通过。
- 已验证：Tauri 前端 `npm run build` 通过；发布 exe `npm run tauri -- build --no-bundle` 通过。
- 已验证：已启动 `D:\MINOS-CORE\apps\desktop-tauri\src-tauri\target\release\minos-core-desktop.exe`，进程响应正常，窗口标题为 `MINOS-CORE Workbench`。

## V1.14.9 CP 生成 502 修复

- 当前状态：已定位 CP 阶段 502 根因并完成后端修复。
- 已定位：PFMEA 阶段已经拆成每个 PFD 工序一次请求，但 CP 阶段仍把全部高/中 AP 的 PFMEA 行和整张 PFD 一次性发给文本 LLM；这会在控制计划阶段再次触发上游 `502 upstream_error`。
- 已修复：链式 `generate_cp_from_confirmed_pfmea(...)` 改为每条目标 PFMEA 行单独调用文本 LLM 生成 CP，再合并为控制计划。
- 已加固：CP 返回行必须引用当前请求的 `pfmea_id`，并且 `process_step_id` 必须匹配该 PFMEA 行和已确认 PFD；串到其他 PFMEA 行会直接失败。
- 已加固：CP schema 明确要求 `pfmea_id` 和 `characteristic_number`，避免生成结果缺少追溯来源。
- 已验证：新增红灯回归测试先失败后通过，覆盖 CP 不再整批请求以及 CP 串 PFMEA ID 会被拒绝。
- 已验证：`python -m pytest tests/test_ai_drawing_three_table_workflow.py tests/test_desktop_shell.py tests/test_desktop_tauri_app_state.py tests/test_llm_text_responses.py tests/test_openai_multimodal_adapter.py -q`：101 项通过。
- 已验证：`git diff --check`：通过，仅有 CRLF 提示。
- 已定位：用户再次看到 502 时，系统实际仍由旧窗口残留的 `python -m uvicorn ... --port 8000` sidecar 提供服务；新 Tauri 窗口没有接管端口，因此前端继续连到旧后端代码。
- 已修复：Tauri sidecar 不再因为 `8000` 已打开就直接复用未知服务；如果没有显式 `MINOS_DESKTOP_API_BASE_URL`，会在 `8000-8020` 中选择空闲端口启动自己托管的 sidecar，并把实际端口回传给前端。
- 已验证：人为用 `python -m http.server 8000` 占住 `8000` 后启动 MINOS，新版会把自己的 sidecar 启动到 `8001`，`8001/api/health` 通过。
- 已验证：清理测试占用后重新打开 MINOS，当前 `minos-core-desktop.exe` 的子进程 `python.exe` 正常运行 `uvicorn ... --port 8000`，健康检查通过。
- 已验证：run 23 第一条高风险 PFMEA `PFMEA-P01-01` 的单行 CP 真实 smoke 成功，13.2 秒生成 1 条 CP，证明新 CP 单行路径和模型可用。

## V1.14.10 CP 过程控制可用性增强

- 当前状态：已按用户反馈把 CP 从偏“结果检验计划”补成“过程控制 + 结果检验”的控制计划结构。
- 已完成：链式 CP LLM schema/prompt 新增并要求 `process_parameter`、`parameter_specification`、`process_control_method`、`setup_verification`、`poka_yoke_device`、`poka_yoke_verification`、`process_record`。
- 已完成：规则生成路径 `generate_control_plan_from_pfmea` 会从 PFMEA 的过程特性、失效原因、预防控制派生过程参数、参数规格/设定范围、过程控制方法、首件/换型确认、防错验证和过程记录。
- 已完成：`normalize_control_plan_rows` 与 `ControlItem` 兼容新增字段，旧数据缺字段时不会断。
- 已完成：桌面后端表格、Tauri CP 表格、统一三表工作簿和独立控制计划工作簿均显示新增过程控制字段。
- 已修复：`tests/test_desktop_table_editor.py` 中措施管理用例原本依赖真实日期；当前日期为 2026-05-11 时会把 2026-05-10 判定为逾期。已改为测试内传入固定日期，避免后续日期漂移。
- 已验证：新增红灯测试先失败后通过，覆盖 CP 过程控制字段、导出列和 Tauri 表格列。
- 已验证：`python -m pytest tests/test_ai_drawing_three_table_workflow.py tests/test_generate_control_plan_stage.py tests/test_desktop_table_editor.py tests/test_desktop_tauri_app_state.py -q`：94 项通过。
- 已验证：`python -m pytest tests/test_aiag_vda_v15.py tests/test_stage_result.py tests/test_quality_audit.py tests/test_three_table_linkage.py -q`：56 项和 4 个 subtests 通过。
- 已验证：Tauri 前端 `npm run build` 通过；`git diff --check` 无空白错误，仅有 CRLF 提示。

## V1.14.11 PFMEA 控制逻辑增强

- 当前状态：已按用户确认的方案把 PFMEA 从“只列失效原因/预防/探测”增强为“风险控制逻辑可继承”的结构，但没有把 PFMEA 做成第二张 CP。
- 已完成：PFMEA 行新增并稳定生成 `cause_process_parameter`、`prevention_control_target`、`prevention_control_timing`、`detection_control_target`、`detection_control_timing`、`control_logic_review`。
- 已完成：`normalize_pfmea_row` 会从 PFD/PFMEA 的过程特性推导原因过程参数，从失效原因、预防控制、探测控制推导控制对象、控制时机和复核摘要。
- 已完成：规则生成路径 `infer_pfmea_from_process_flow` 为每条风险行补齐控制逻辑字段，避免离线/规则模式继续输出薄 PFMEA。
- 已完成：链式 PFMEA LLM prompt/schema 要求模型输出原因过程参数、预防控制对象/时机、探测对象/时机和控制逻辑复核；schema 为 strict JSON 字段。
- 已完成：Tauri PFMEA 表格、桌面后端 PFMEA 表格、统一三表工作簿和独立 PFMEA 工作簿均显示新增控制逻辑字段。
- 已完成：PFMEA 关键字段变更影响扩展到新增控制逻辑字段，控制逻辑改动会提示 CP 需同步确认。
- 已完成：CP 继承路径优先使用 PFMEA `cause_process_parameter`，包括规则 CP 生成、链式 CP 后处理、桌面旧/手工 CP 行继承显示和联动新增 CP 建议。
- 已完成：子代理只读审核指出的两个漏口已修复：桌面 CP 继承显示补 `cause_process_parameter -> process_parameter`；PFMEA 缺 CP 的联动建议补过程参数、过程控制、首件/防错/记录字段。
- 已验证：新增红灯测试先失败后通过，覆盖 PFMEA 控制逻辑字段、CP 继承原因过程参数、桌面表格、Tauri 表格和联动新增 CP 建议。
- 已验证：`python -m pytest tests/test_ai_drawing_three_table_workflow.py tests/test_generate_control_plan_stage.py tests/test_desktop_table_editor.py tests/test_desktop_tauri_app_state.py tests/test_three_table_linkage.py -q`：115 项通过。
- 已验证：`python -m pytest tests/test_aiag_vda_v15.py tests/test_stage_result.py tests/test_quality_audit.py -q`：37 项和 4 个 subtests 通过。
- 已验证：`python -m py_compile minos_core/aiag_vda_pfmea.py minos_core/pfd_to_pfmea_ai.py minos_core/pipeline_chain.py minos_core/generate_control_plan.py minos_core/exporters/three_table_workbooks.py minos_core/exporters/apqp_workbook.py minos_core/change_management.py minos_core/three_table_linkage_reports.py minos_desktop/table_editor.py`：通过。
- 已验证：Tauri 前端 `npm run build` 通过。

## V1.14.12 CP JSON 解析加固

- 已定位：当前 run #25 卡在 CP 阶段不是 502/504，而是模型返回了完整 JSON 后又追加“原因判断 / 处理方案”等解释文字，导致严格 JSON 解析失败。
- 已修复：文本 LLM 解析器在纯 JSON 和代码块解析失败后，会提取第一个完整 JSON 对象，能兼容“JSON + 额外说明”的真实返回。
- 已收紧：CP system prompt 和单条 PFMEA prompt 明确要求只输出 schema JSON，不输出 Markdown、原因判断、处理方案或解释文字。
- 已验证：新增红灯测试先失败后通过，覆盖 `{"rows": ...}` 后追加中文解释文字的流式响应。
- 已验证：`python -m pytest tests/test_llm_text_responses.py -q`：9 项通过。
- 已验证：`python -m pytest tests/test_ai_drawing_three_table_workflow.py -q -k "chain_cp or control_plan_generation"`：5 项通过，31 项未选中。
- 已验证：`python -m py_compile minos_core\adapters\llm_text.py minos_core\pipeline_chain.py`：通过。

## V1.14.13 Responses 流式事件横向加固

- 已定位：run #27 的 PFMEA 失败不是路径权限问题，而是 Responses 流式返回没有被解析器识别到文本，错误为 `OpenAI Responses API stream did not contain output text`。
- 已横向排查：项目中只有 `minos_core.adapters.multimodal._parse_responses_stream` 一个共享 Responses SSE 解析器；文本 LLM 和图纸多模态识别都复用它。
- 已修复：流式解析器除 `response.output_text.delta` 外，继续兼容 `response.output_text.done`、`response.reasoning_text.done`、`response.done`、`response.output_item.done` 和 `response.content_part.done`。
- 已验证：新增红灯测试覆盖 `output_text.done`、`response.done`、`output_item.done`、`content_part.done` 四类完成事件。
- 已验证：`python -m pytest tests/test_openai_multimodal_adapter.py tests/test_llm_text_responses.py -q`：23 项通过。
- 已验证：`python -m pytest tests/test_ai_drawing_three_table_workflow.py -q -k "chain_pfmea or chain_cp"`：6 项通过，30 项未选中。
- 已验证：`python -m py_compile minos_core\adapters\multimodal.py`：通过；`git diff --check` 无空白错误，仅 CRLF 提示。

## V1.14.14 SSE 上游过载重试

- 已定位：run #28 的 PFMEA 失败不是解析器事件漏口，而是上游在 SSE 流里明确返回 `service_unavailable_error / server_is_overloaded`。
- 根因：HTTP 429/500/502/503/504 已会重试，但同类临时错误如果包在 SSE `error` 事件里，会被 `_parse_responses_stream` 抛出后直接包装成阶段失败。
- 已修复：新增共享 `is_retryable_responses_stream_error(...)`，识别 `server_is_overloaded`、`service_unavailable`、`temporarily unavailable`、`try again later` 和 `rate_limit`。
- 已修复：文本 LLM 与多模态图纸识别两条 Responses 流式链路都复用该判断，遇到这类 SSE 临时上游错误会按已有 attempt 策略重试。
- 已验证：新增红灯测试覆盖文本 PFMEA/PFD/CP 链路和图纸视觉链路的 SSE `server_is_overloaded` 重试。
- 已验证：`python -m pytest tests/test_openai_multimodal_adapter.py tests/test_llm_text_responses.py -q`：25 项通过。
- 已验证：`python -m pytest tests/test_ai_drawing_three_table_workflow.py -q -k "chain_pfmea or chain_cp"`：6 项通过，30 项未选中。
- 已验证：`python -m py_compile minos_core\adapters\llm_text.py minos_core\adapters\multimodal.py`：通过；`git diff --check` 无空白错误，仅 CRLF 提示。

## V1.14.15 PFMEA 生成中断韧性修复

- 已完成：读取计划 `C:\Users\fgtan\.claude\plans\minos-core-pfmea-plan-scalable-eclipse.md`，本轮按“后端不中断、SSE 可保活、前端可重连、PFMEA 部分结果可保存”收口。
- 已完成：后端 `ProgressChannel` 支持 heartbeat；链式触发路由创建 channel 后立即绑定事件循环，避免后台任务先 emit 时丢事件。
- 已完成：链式 PFMEA 单工序失败时发送 `step_failed`，记录 `failed_step_ids` 并继续处理剩余 PFD 工序；仅所有工序失败时阶段失败。
- 已完成：Tauri `sse-client.ts` 增加 `StepFailedEvent`、`HeartbeatEvent`、连接状态回调和最多 5 次自动重连；应用层 `error` 事件仍直接交给错误处理。
- 已完成：三表工作台和图纸导入页处理 `step_failed` 与重连状态，断线时显示“正在自动重连”，不再显示“连接中断，已获取最终状态”。
- 已完成：`DesktopRunService.generate_pfmea_for_confirmed_pfd()` 和 `regenerate_pfmea_stage()` 在 `step_complete` 时把已生成 PFMEA 行 checkpoint 到 SQLite 与磁盘，metadata 标记 `chain_stage_status=partial`。
- 已完成：补上 `routes_runs.py` 的 `asyncio` 导入，避免真实链式确认入口运行时缺导入。
- 已验证：`python -m pytest tests/desktop/test_sse_chain_resilience.py tests/test_desktop_tauri_app_state.py -q`：29 项通过。
- 已验证：Tauri 前端 `npm run build` 通过。

## V1.14.16 独立 Windows 安装包封装

- 已完成：读取计划 `C:\Users\fgtan\.claude\plans\minos-core-exe-declarative-papert.md`，本轮按“PyInstaller 后端 sidecar + Tauri NSIS 自包含安装包”收口。
- 已完成：新增 `minos_core/_paths.py`，提供 `resource_root()`、`configs_dir()`、`user_data_dir()`；冻结环境优先使用 `_MEIPASS`，否则使用 exe 所在目录。
- 已完成：`minos_core/config.py`、`knowledge_base.py`、`knowledge_recommendation.py`、`part_family_knowledge.py` 改为通过 lazy `configs_dir()` 解析资源，支持 `MINOS_CONFIGS_DIR` 测试和打包覆盖。
- 已完成：`minos_desktop/services.py` 默认 DB/output 改为用户本地数据目录；测试同步验证默认输出不再指向仓库 `out/desktop`。
- 已完成：新增 `minos-desktop-api.spec`，采用 PyInstaller one-folder，收集 configs、uvicorn/FastAPI hidden imports 和 OCR 相关依赖资源。
- 已完成：新增 `scripts/build_sidecar.ps1`、`scripts/build_release.ps1`、`apps/desktop-tauri/src-tauri/binaries/.gitkeep`，并在 `.gitignore` 忽略 sidecar exe 与 one-folder 产物。
- 已完成：Tauri 配置新增 icon、`externalBin` 和 `_internal` 资源映射；新增 `capabilities/default.json` 的 shell sidecar 执行权限。
- 已完成：Rust 端新增 `tauri-plugin-shell`，用 `app.shell().sidecar("minos-desktop-api")` 启动后端，传入随机 token、端口、DB 路径和 output 路径；日志写到 app local data `logs/api.log`。
- 已完成：生成 Tauri 全套图标尺寸；`build.rs` 在 debug/check 场景生成占位 sidecar，正式 release 仍依赖 `build_sidecar.ps1` 生成真实产物。
- 已验证：新增资源路径测试先失败后通过，覆盖 env configs、冻结 exe 资源根、零件族 index 和 desktop 用户数据目录默认值。
- 已验证：`python -m unittest tests.test_runtime_paths tests.desktop.test_services -v`：20 项通过。
- 已验证：`python -m py_compile minos_core\_paths.py minos_core\config.py minos_core\knowledge_base.py minos_core\knowledge_recommendation.py minos_core\part_family_knowledge.py minos_desktop\services.py tests\test_runtime_paths.py tests\desktop\test_services.py`：通过。
- 已验证：Tauri Rust `cargo check` 通过。
- 已验证：`powershell -ExecutionPolicy Bypass -File .\scripts\build_sidecar.ps1` 通过，真实 PyInstaller one-folder sidecar 已生成并复制到 Tauri binaries。
- 已验证：`npm run release:nsis` 通过，生成 `apps\desktop-tauri\src-tauri\target\release\bundle\nsis\MINOS-CORE_1.14.0_x64-setup.exe`，大小约 95 MB。
- 已修复：打包后 sidecar 启动失败的根因是 `minos-desktop-api.spec` 仍直接把 `minos_desktop/api/cli.py` 当脚本入口，导致包内相对导入 `from .app import create_app` 在冻结环境下失败；已新增 `scripts/entrypoint_desktop_api.py`，改为以包模块身份调用 `minos_desktop.api.cli.main()`。
- 已修复：外部入口位于 `scripts/` 后，PyInstaller 需要显式 `pathex=[str(repo_root)]`，否则分析阶段会找不到 `minos_core` / `minos_desktop`；spec 已改为基于 `SPECPATH` 的仓库根路径，并用绝对 configs 路径收集资源。
- 已加固：windowed PyInstaller sidecar 在无标准输出/错误流时会把启动日志写入 `%LOCALAPPDATA%\MINOS-CORE\logs\api-bootstrap.log`，避免后续启动异常完全不可见。
- 已验证：新增回归测试先红后绿，覆盖 spec 不再指向 `cli.py`、必须包含仓库 `pathex`、windowed sidecar 标准流兜底；`python -m unittest tests.test_runtime_paths tests.desktop.test_services -v`：22 项通过。
- 已验证：重新执行 `powershell -ExecutionPolicy Bypass -File .\scripts\build_sidecar.ps1` 通过，one-folder 内 sidecar `--help` 可运行；带 `Authorization: Bearer smoke` 访问 `/api/health` 返回 `{"ok":true,"status":"ok","service":"minos-desktop-api","version":"1.14.0"}`。
- 已验证：重新执行 `npm run release:nsis` 通过，新的安装包已生成到 `apps\desktop-tauri\src-tauri\target\release\bundle\nsis\MINOS-CORE_1.14.0_x64-setup.exe`，大小约 95 MB。
- 已验证：启动 `apps\desktop-tauri\src-tauri\target\release\minos-core-desktop.exe` 后，进程能拉起自己的 `minos-desktop-api.exe` 子进程，并传入本地用户目录下的 SQLite DB 与输出目录。

## V1.14.18 AI 默认 URL 切换

- 已完成：MINOS-CORE 默认 AI Responses base URL 改为 `https://allincode.top`；实际 Responses 请求路径为 `https://allincode.top/responses`。
- 已保留：显式 `MINOS_OPENAI_BASE_URL`、`OPENAI_BASE_URL`、`ARK_BASE_URL` 仍优先于默认值。
- 已保留：Codex 的 auth、wire_api、store、reasoning 和 user-agent 仍可复用；Codex `base_url` 不再作为 MINOS 默认 AI 地址。
- 已同步：桌面设置状态在无显式 URL 环境变量时显示 `base_url_source=default`，`responses_path=responses`。
- 已验证：`python -m pytest tests/test_ai_config.py tests/desktop/test_shell.py tests/test_llm_text_responses.py tests/test_openai_multimodal_adapter.py -q`：49 项通过。
- 已验证：`python -m pytest tests/test_desktop_tauri_app_state.py -q`：25 项通过。
- 已验证：Tauri 前端 `npm run build` 通过；运行时配置读取显示 `https://allincode.top`、`base_url_source=default`、`responses_path=responses`。
- 已验证：`git diff --check` 通过，仅有 CRLF 换行提示。

## V3.2.1 工作台旧快照刷新修复

- 已定位：用户看到的“失效模式分析仍生成中、0 行”不是后端未完成。安装后服务 `/api/runs/1/chain/state` 已返回 `pfmea.status=generated`、`row_count=53`、`pending_count=15`。
- 根因：工作台前端仍持有离开页面前的旧 `activeRun` 快照；SSE 连接在页面切换/休眠后无法保证继续推送最终 `done`，而工作台重新显示时没有主动 `getRun()`。
- 已修复：`App.tsx` 新增 `refreshActiveRun()`，右上角刷新按钮真正重新读取当前 run；`ThreeTableWorkbench.tsx` 新增 `onRunRefresh`，在进入工作台、窗口聚焦和页面重新可见时刷新 run 快照。
- 已验证：新增回归测试先红后绿，`python -m pytest tests/test_desktop_tauri_app_state.py::test_workbench_refreshes_stale_run_when_reopened_or_toolbar_refresh_clicked tests/test_desktop_tauri_app_state.py::test_chain_sse_client_reconnects_and_workbench_handles_step_failed -q`：2 项通过。
- 已验证：`npm run build` 通过。
- 已验证：`python -m pytest tests/test_desktop_tauri_app_state.py tests/test_release_version_sync.py -q`：36 项通过。
- 已重建：`powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1` 通过，重新生成 `release/MINOS-CORE_3.2.1_x64-setup.exe`。
- 已核对：安装包版本 `3.2.1`，大小 `93,958,544` bytes，SHA256 `BF4F2AE82AD13847A6DAF7F0C83BA058476EEF9670F648AA6A589934B15F57F4`。

## V3.2.1 真实图纸打开测试与 auto OCR 修复

- 已按操作手册用源码版 sidecar + Vite 前端执行 JLV 种子图纸打开测试，输入为 `C:\Users\fgtan\Desktop\知识库种子\JLV03000500_001_AC_RR DH ASSY.pdf`。
- 已确认 CORS 修复后 `POST /api/projects/{id}/chain-runs` 能成功进入后端并创建 run；Playwright 打开测试通过。
- 已定位第二个阻塞点：`ocr_engine=auto` 被固定解析为 MinerU，当前机器 MinerU 本地服务因 OpenBLAS 内存分配失败无法启动，导致真实图纸链路停在 OCR 阶段。
- 已修复：`minos_core.pipeline.drawing_analysis._effective_ocr_engine()` 对 `auto` 调用 `get_default_ocr_engine()`，按本机可用 OCR 引擎选择；显式 `mineru` 行为不变。
- 已补测试：`tests/test_pipeline_ocr_first.py` 覆盖 auto 使用检测到的默认 OCR 引擎。
- 已完成完整草案链路：PFD 12 行、PFMEA 53 行、CP 34 行，`cp-confirm` 后 run 状态为 `draft_ready`。
- 已完成导出验证：统一三表工作簿和三份独立工作簿均生成，OpenXML zip 检查通过。
- 已确认中途边界：第一次草案导出响应中 `final_export_allowed=false`，原因是 CP 完整性复核项仍需人工处理；该边界已在后续“JLV 正式导出闭环修复”中关闭。
- 已验证：`python -m pytest tests/test_pipeline_ocr_first.py tests/test_desktop_api_ocr_mode.py tests/test_desktop_api_sidecar.py -q`：32 项和 3 个 subtests 通过。
- 已验证：Tauri 前端 `npm run build` 通过。
- 已验证：`git diff --check` 无空白错误，仅 CRLF 提示。

## V3.2.1 JLV 正式导出闭环修复

- 已继续按操作手册处理 JLV run 的质量门闭环，目标从草案包推进到正式导出允许状态。
- 已修复：PFD 在 LLM 漏填 `evidence_refs` 时回填图纸页证据；PFMEA 和 CP 从上游继承 `evidence_refs`。
- 已修复：PFMEA 从 PFD 继承特殊特性引用到 `characteristic_refs`，CP 继承 `source_special_characteristics` 并回填 `product_process_characteristic`。
- 已修复：CP 确认后刷新三表聚合结果，质量门、顶层 metadata 和知识库推荐会物化到当前 run。
- 已修复：新增 `evidence_confirmation` 闭环任务和 `confirm_review_target` edit patch，可把证据/OCR 复核项写入 `metadata.review_confirmations`。
- 已修复：质量门 warning 不再作为 edit gate 的正式导出硬阻断；同步阻断仍继续阻断。
- 已修复：特殊特性校验不再把普通产品/过程特性误判为特殊特性。
- 已修复：服务层 PFMEA 生成测试替身签名补 `model=None`，与真实函数调用契约一致。
- 已完成真实 run #3：PFD/PFMEA/CP 已确认，正式导出返回 `allow_formal_release=true` / `final_export_allowed=true`。
- 已生成正式导出：`D:\MINOS-CORE\out\open-test\ui-run-latest\exports-final\三表总工作簿.xlsx` 和 `三表独立文件` 下 3 个独立表。
- 已验证：4 个 xlsx 均通过 OpenXML zip 可打开性检查。
- 已验证：`python -m pytest tests/test_pipeline_ocr_first.py tests/test_desktop_api_ocr_mode.py tests/test_desktop_api_sidecar.py tests/three_table_workflow/test_control_plan_generation.py tests/test_closure_tasks.py tests/test_review_issues.py tests/test_stage_result.py tests/desktop/services/test_run_service_integration.py -q`：81 项和 3 个 subtests 通过。
- 已验证：Tauri 前端 `npm run build` 通过。
- 已验证：`git diff --check` 无空白错误，仅 CRLF 提示。
- 已完成 Reasonix 计划复审：已把正式质量门当前状态、真实复测通过/失败判定、修复-测试映射、已知限制和前端可观测性处理说明补回计划文档。

## V3.2.1 正式输出质量门防复发计划当前状态

- 已明确：用户当前目标不是修当前 JLV 报告结果，而是让 MINOS-CORE 以后不再把同类问题放进正式输出。
- 已建立：`docs/superpowers/plans/2026-06-01-v3.2.1-formal-output-quality-gates.md`，计划用 JLV 小夹具复现缺陷，不依赖真实 PDF、OCR 或 AI。
- 已建立：OpenSpec 目录 `openspec/changes/v3.2.1-formal-output-quality-gates/`，包含 `proposal.md`、`design.md`、`tasks.md`。
- 已完成：新增 JLV 缺陷 fixture 和正式输出质量门回归，不依赖真实 PDF、OCR 或 AI；坏链路会暴露重复 CP ID、未覆盖 PFMEA、泛化 CP、OCR 身份疑点和盐雾红锈 240h 漏项。
- 已完成：`audit_chain()` 会生成重复 `control_plan_id`、PFMEA 未覆盖、缺 CP 特性和泛化控制文本 blocker；`evaluate_export_gate()` 会因结构 blocker 阻断正式导出，并投影到 `manual_review_items` / `review_issues`。
- 已完成：链式 CP 归一化不再信任模型返回的重复 CP ID；规则 CP 生成不再信任源 row 的 `control_plan_id`，但保留 `linked_control_plan_id` 的兼容语义。
- 已完成：drawing metadata risk 会从 drawing gate、hybrid OCR 和三表 chain metadata 进入正式质量门；review 级风险可继续生成草案，但未确认前不能正式放行；同一 risk id 合并时 blocker 优先。
- 已完成：红锈 240h 正式质量门不再只依赖 metadata risk；只要 evidence 里出现红锈 240h，未删除控制计划必须覆盖同一语义片段内的红锈 + 240h。白锈 240h 与红锈外观判定用分号、逗号、斜杠或括号并列时，不能误判为红锈 240h 已覆盖。
- 已完成：APQP workbook 在无显式 traceability matrix 时从 PFMEA/CP 关系合成追溯行；人工复核清单在 manual review 为空但 review issue 未解决时写入复核项。
- 已完成：JLV 正反夹具回归证明坏 fixture 阻断、修正 fixture 放行，不是“一刀切”拒绝。
- 已验证：`python -m pytest tests/test_jlv_formal_output_quality_gate.py tests/test_quality_audit.py tests/edit_patch/test_export_gate.py tests/three_table_workflow/test_control_plan_generation.py tests/three_table_workflow/test_drawing_analysis.py tests/test_apqp_rebuild_contract.py -q` 通过，结果为 82 项和 4 个 subtests 通过。
- 已验证：`npm run build --prefix apps/desktop-tauri` 通过。
- 已验证：`git diff --check` 通过，仅有 CRLF 换行提示；OpenSpec、计划、进度、发现和流程图均可用 UTF-8 读取；`project_flow.mmd` 节点 ID 不重复。

## V3.3.1 OCR 数值指标特殊特性边界修复

- 已定位：当前 #1 结果中，`不低于120h` 由 OCR fallback 进入 `special_characteristics`，分类为 PTC，随后 PFD/PFMEA/CP 被放大为 SC。
- 已建立：OpenSpec 目录 `openspec/changes/v3.3.1-ocr-numeric-special-characteristic-boundary/`，记录 Define / Specify / Implement / Verify 四步闭环。
- 已完成：新增 OCR 回归测试，普通盐雾阈值只应进入 `numeric_specifications`，明确 `SC` 标识仍进入 `special_characteristics`。
- 已修复：`minos_core/drawing_ocr_analysis.py` 不再把数值阈值生成 `OCR-NS-*` 特殊特性候选。
- 已验证：`python -m pytest tests/test_drawing_ocr_analysis.py -q` 通过，16 项通过。
- 已验证：`python -m pytest tests/test_drawing_ocr_analysis.py tests/test_characteristic_registry.py tests/test_pipeline_ocr_first.py -q` 通过，49 项通过。
- 已验证：`python -m compileall minos_core\drawing_ocr_analysis.py` 通过。
- 已验证：OpenSpec、计划、进度、发现和流程图均可用 UTF-8 读取；`project_flow.mmd` 节点 ID 不重复。
- 已验证：本轮文件 `git diff --check` 通过，仅有 CRLF 换行提示。

## V3.3.2 Mimo V2.5 特殊特性候选识别

- 已建立：OpenSpec 目录 `openspec/changes/v3.3.2-mimo-v25-special-characteristic-candidates/`。
- 已完成：`proposal.md` 记录 mimo-v2.5 作为视觉候选识别 provider 的目标、非目标和验收边界。
- 已完成：`design.md` 锁定当前已确认的小米 mimo Chat Completions API：`base_url=https://api.xiaomimimo.com/v1`、`endpoint=chat/completions`、图片通过 `image_url` 方式传入。
- 已完成：`tasks.md` 拆分后续配置、adapter、候选 schema、OCR/vision 融合、注册表、下游清理、导出 gate 和验证任务。
- 已更新：`task_plan.md`、`findings.md` 和 `project_flow.mmd` 追加本变更记录。
- 已完成：`minos_core.ai_config.load_vision_config()` 和 `load_vision_api_key()`，mimo 使用 `wire_api=chat_completions`、`responses_path=chat/completions`。
- 已完成：新增 `MimoV25ChatCompletionsDrawingAnalyzer`，按官方 `messages[].content[].image_url.url` 传图，并解析 `choices[0].message.content`。
- 已完成：新增 `special_characteristic_candidates` 规范化、规则确认、风险投影和未确认引用清理。
- 已完成：hybrid 融合 OCR 明确 SC/CC 文本候选；注册表和 orchestration 只让已确认 SC/CC 进入 PFD/PFMEA/CP。
- 已配置：本机用户环境变量已设置 `MINOS_VISION_PROVIDER=mimo`、`MINOS_MIMO_MODEL=mimo-v2.5`、`MINOS_MIMO_BASE_URL=https://api.xiaomimimo.com/v1` 和 `MINOS_MIMO_API_KEY`。
- 已验证：`python -m pytest tests/test_ai_config.py tests/test_openai_multimodal_adapter.py tests/test_special_characteristic_candidates.py tests/test_drawing_ocr_analysis.py tests/test_characteristic_registry.py tests/test_drawing_to_pfd.py tests/test_pipeline_ocr_first.py tests/three_table_workflow/test_drawing_analysis.py -q` 通过，133 项通过。
- 已验证：`python -m compileall` 覆盖本轮修改的 Python 模块，通过。
- 已验证：本轮代码和测试文件 `git diff --check` 通过，仅有 CRLF 换行提示。

## V3.6.0 本地版本提交

- 已开始：按用户要求把当前本轮能力以本地版本 `3.6.0` 提交。
- 已定位：版本同步测试要求 Python package、桌面 package/lock、Cargo/Tauri、sidecar API 和前端 fallback 版本一致。
- 已更新：`pyproject.toml`、`apps/desktop-tauri/package.json`、`apps/desktop-tauri/package-lock.json`、`apps/desktop-tauri/src-tauri/Cargo.toml`、`apps/desktop-tauri/src-tauri/Cargo.lock`、`apps/desktop-tauri/src-tauri/tauri.conf.json`、`apps/desktop-tauri/src-tauri/src/lib.rs`、`minos_desktop/api/app.py`、`minos_desktop/api/routes_health.py`、`apps/desktop-tauri/src/App.tsx`、`apps/desktop-tauri/src/pages/SettingsPage.tsx` 和 `tests/test_release_version_sync.py` 到 `3.6.0`。
- 已验证：`python -m pytest tests/test_release_version_sync.py tests/test_ai_config.py tests/test_openai_multimodal_adapter.py tests/test_special_characteristic_candidates.py tests/test_drawing_ocr_analysis.py tests/test_characteristic_registry.py tests/test_drawing_to_pfd.py tests/test_pipeline_ocr_first.py tests/three_table_workflow/test_drawing_analysis.py -q` 顺序重跑通过，136 项通过。
- 已验证：`python -m compileall` 覆盖本轮修改的 Python 模块和 sidecar 版本文件，通过。
- 已验证：`npm run build --prefix apps/desktop-tauri` 通过，前端版本 fallback 可编译。
- 已验证：文档 UTF-8 可读、`project_flow.mmd` 节点 ID 不重复、敏感 key 前缀未出现在代码或文档中。

## V3.6.0 默认 AI 地址修正与重新封装

- 已确认：桌面端 PFD 阶段失败来自文本 LLM Responses 通道，当前默认地址原为 `https://cx.allincoding.cc`，DNS 解析失败；mimo 地址 `https://api.xiaomimimo.com/v1` 解析正常，但它只用于视觉候选识别。
- 已按用户要求修正：默认 AI Responses base URL 改为 `https://allincode.top`，实际请求路径仍为 `/responses`。
- 已同步：设置页 placeholder、配置诊断默认值、README、ADR、OpenSpec 记录、测试和流程记录。
- 已验证：`Resolve-DnsName allincode.top` 可解析到 A/AAAA 记录。
- 已验证：`python -m pytest tests/test_ai_config.py tests/test_desktop_tauri_app_state.py -q` 通过，51 项通过。
- 已验证：`python -m pytest tests/desktop/test_sse_chain_resilience.py tests/edit_patch/test_action_items.py tests/test_automation_review.py tests/test_quality_audit.py tests/three_table_workflow/test_control_plan_generation.py -q` 通过，52 项和 4 个 subtests 通过。
- 已验证：`python -m compileall minos_core/ai_config.py minos_core/observability/config_diagnostics.py` 通过。
- 已验证：`npm run build --prefix apps/desktop-tauri` 通过。
- 已重新封装：`release/MINOS-CORE_3.6.0_x64-setup.exe` 和 `dist/build/out/MINOS-CORE_3.6.0_x64-setup.exe` 已更新。
- 已校验：安装包大小 `94,020,745` bytes，SHA256 `572A6FBCE3CF69E31FF2C4B0655365B3DD043AEEEED38961C06DBDBB84D956DE`，版本信息 `ProductVersion=3.6.0` / `FileVersion=3.6.0`。

## v3.6.2 声明数量驱动的 CC/SC 识别

- 计划已建立：`docs/superpowers/plans/2026-06-05-declared-count-special-characteristics-discovery.md`
- OpenSpec：`openspec/changes/v3.6.2-declared-count-special-characteristics/`
- 已完成：Mimo 请求现在每页发送整页图、右下标题栏/声明表放大图、顶部产品特殊特性表放大图；局部图只作为同页阅读辅助，不产生新的 evidence id。
- 已完成：hybrid 融合层改为优先保留带正数的声明数量，避免 OCR/MinerU 抽取失败产生的 `{"CC":0,"SC":0}` 覆盖 Mimo 视觉读到的 `{"CC":2,"SC":1}`。
- 已完成：`special_characteristic_discovery` 不再把“未找到/未发现”且无真实 bbox 的占位 location 算作已定位。
- 已验证：真实 JLV 源码版 run `D:\MINOS-CORE\.tmp\browser-test\v362-jlv-crop-output-8011\run-direct\three_table_generation_result.json` 输出 `declared_totals={"CC":2,"SC":1}`、`found_counts={"CC":0,"SC":0}`、`missing_counts={"CC":2,"SC":1}`。
- 已验证：同一真实 run 进入 `SC-DISCOVERY-MISSING-CC`、`SC-DISCOVERY-MISSING-SC`、`SC-JUDGE-COUNT-MISMATCH-CC`、`SC-JUDGE-COUNT-MISMATCH-SC` 风险；状态为 `needs_review`，没有再静默显示无 SC/CC。
- 已发现并修复：源码版 sidecar 若父进程未继承 Windows 用户环境变量，会导致 Mimo key 读不到并退回 `hybrid_ocr_fallback`。
- 已新增回归：`test_desktop_sidecar_source_mode_reads_mimo_from_windows_user_environment` 先红后绿，锁定桌面 sidecar 源码模式也能读取 Windows 用户环境中的 Mimo 配置。
- 已真实复测：Codex 浏览器重新导入 JLV 图纸后，run #1 输出 `analysis_source=hybrid_vision`、`declared_totals={"CC":2,"SC":1}`、`missing_counts={"CC":2,"SC":1}`，不再出现 `mimo API key is not configured`。
- 已发现并修复：Workbench 表格把图纸级 `declared_totals` / `special_characteristic_discovery` 当成每行“特殊特性”显示，造成 `声明CC/声明SC/缺少CC/缺少SC` 在行内重复出现。
- 已修复：`rowsFromResult()` 不再把 drawing analysis 的全局 special 字段复制进每个 row.raw；“特殊特性”列只显示行级正式 `CC/SC`、行级 confirmed judgment 或 `-`。
- 已收窄：行级字符串中的 `图纸声明CC 2个` / `图纸声明SC 1个` 只作为说明被剥离，表格显示为干净的 `CC / 特征` 或 `SC / 特征`。
- 已验证：`python -m pytest tests/test_desktop_tauri_app_state.py -q` 通过，40 项通过。
- 已验证：特殊特性相关聚焦回归 `python -m pytest tests/test_ai_config.py tests/test_openai_multimodal_adapter.py tests/test_special_characteristic_declarations.py tests/test_special_characteristic_discovery.py tests/test_special_characteristics_evidence.py tests/test_special_characteristics_judge.py tests/test_pipeline_ocr_first.py tests/three_table_workflow/test_drawing_analysis.py tests/test_jlv_formal_output_quality_gate.py tests/test_desktop_tauri_app_state.py -q` 通过，163 项通过。
- 已验证：`npm run build --prefix apps/desktop-tauri` 通过；仍有既有 CSS minify warning `Expected identifier but found "-"`。
- 已真实复测：Codex 浏览器刷新 `http://127.0.0.1:1420/` 后，PFD 表格特殊特性列只显示 `CC / ...`、`SC / ...` 或 `-`，未发现 `声明CC/声明SC/缺少CC/缺少SC/候选/PTC`。

## V3.6.5 当前版本命名同步

- 已按用户在浏览器中标注的顶部版本号，将当前产品版本命名从 `3.6.0` 同步为 `3.6.5`。
- 已更新：`pyproject.toml`、桌面 `package.json/package-lock.json`、Tauri `Cargo.toml/Cargo.lock/tauri.conf.json`、bootstrap、FastAPI app、`/api/health`、前端顶部和设置页 fallback。
- 已验证：`python -m pytest tests/test_release_version_sync.py -q` 通过，3 项通过。
- 已验证：`npm run build --prefix apps/desktop-tauri` 通过；仍有既有 CSS minify warning `Expected identifier but found "-"`。
- 已真实复测：Codex 浏览器刷新 `http://127.0.0.1:1420/` 后，DOM 中存在 `v3.6.5` 且不存在 `v3.6.0`。

## V3.8.0 删除 Mimo，改用 GPT5.5 + MinerU 特殊特性识别

- 已建立：详细修改计划 `docs/superpowers/plans/2026-06-06-v3.8.0-remove-mimo-gpt55-mineru.md`。
- 已建立：OpenSpec 目录 `openspec/changes/v3.8.0-remove-mimo-gpt55-mineru/`，包含 `proposal.md`、`design.md`、`tasks.md`。
- 已同步：`task_plan.md`、`progress.md`、`findings.md` 和 `project_flow.mmd` 追加本次 3.8.0 计划记录。
- 已明确：Mimo 组件删除，不保留 fallback；视觉通道只保留 OpenAI Responses/GPT5.5。
- 已明确：JLV 图纸验收目标为 `CC=2, SC=1`，SC 在技术要求第 4 条第(2)项，CC 在第 5 条和第 6 条。
- 已完成：并行 5 个子代理执行删除 Mimo、GPT5.5 visual locator/视觉裁剪、hybrid/evidence 接入、drawing analysis 清理和 3.8.0 版本同步。
- 已完成：`minos_core/ai_config.py` 不再把 `MINOS_VISION_PROVIDER=mimo` 或 `MINOS_MIMO_*` 作为视觉 provider；`minos_core/adapters/multimodal.py` 不再包含 Mimo Chat Completions analyzer、Mimo prompt 或 Mimo payload helper。
- 已完成：新增 `drawing_visual_evidence.py`，会生成整页、标题栏/声明区、产品特殊特性表、技术要求总区和逐条技术要求裁剪；这些 crop 会进入 OpenAI Responses 多模态请求和 drawing evidence refs。
- 已完成：新增 GPT5.5 visual locator 契约，`located_occurrences` 会进入 hybrid fusion、special characteristic evidence packet 和后续 judge 候选链路。
- 已完成：版本面同步到 `3.8.0`，`tests/test_release_version_sync.py` 已覆盖当前发布源文件。
- 已验证：`python -m pytest tests/test_ai_config.py tests/test_openai_multimodal_adapter.py tests/test_drawing_visual_evidence.py tests/test_special_characteristics_visual_locator.py tests/test_special_characteristics_evidence.py tests/test_special_characteristics_judge.py tests/test_pipeline_ocr_first.py tests/three_table_workflow/test_drawing_analysis.py tests/test_special_characteristic_candidates.py tests/test_release_version_sync.py -q`：127 项通过。
- 已验证：`python -m compileall minos_core minos_desktop` 通过。
- 已验证：`git diff --check` 无空白错误，仅有 Git LF/CRLF 提示。
- 已验证：`npm run build --prefix apps/desktop-tauri` 通过；仍有既有 CSS minify warning `Expected identifier but found "-"`。
- 已验证：`powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1` 通过，重新生成 `MINOS-CORE_3.8.0_x64-setup.exe`。
- 已验证：`release`、`dist/build/out` 和 Tauri target 三处安装包大小均为 `94,047,578` bytes，SHA256 均为 `E96F60711DBF1B368E6B9BC611D1BC29EE877808EB32E9E8A0FE2BD2D1C335C7`，PE 头为 `MZ`。
- 已验证：打包后的 one-folder sidecar 启动后 `/api/health` 返回 `{"ok":true,"status":"ok","service":"minos-desktop-api","version":"3.8.0"}`。
- 当前限制：真实 JLV 图纸试跑尚不能标记完全验收。现有裁剪和 prompt 能改善第 5/6 条 CC 召回，但第 4 条第(2)项 `转动力矩(0.5~2.5)Nm` 的 SC 在真实 GPT5.5 调用中仍不稳定；正式结果仍必须依赖 judge confirmed 或 human confirmed。
- 待完成：继续针对真实 JLV 的第 4 条第(2)项 SC 做稳定化；本轮不能声称真实图纸完全验收通过。

## V3.8.5 当前版本提交

- 已开始：按用户要求把当前最新工作区提交到本地 git，并把产品版本同步为 `3.8.5`。
- 已更新：Python、npm、Cargo、Tauri、sidecar API、桌面 UI fallback 和 `tests/test_release_version_sync.py` 的版本面。
- 已验证：`tests/test_release_version_sync.py` 通过，特殊特性相关聚焦回归 139 项通过。
- 已验证：`scripts/build_release.ps1` 通过，生成 `MINOS-CORE_3.8.5_x64-setup.exe`。
- 已验证：`release`、`dist/build/out` 和 Tauri target 三处 `3.8.5` 安装包 SHA256 一致，PE 头为 `MZ`。
- 已验证：packaged sidecar `/api/health` 返回 `{"ok":true,"status":"ok","service":"minos-desktop-api","version":"3.8.5"}`。

## V3.8.6 安全加固与发布整改

- 已开始：按审计证据版蓝图执行 PR 1 到 PR 9。
- 已建立：OpenSpec 目录 `openspec/changes/v3.8.6-security-release-hardening/`，包含 `proposal.md`、`design.md`、`tasks.md`。
- 已同步：`task_plan.md` 追加本次目标、流程图、OpenSpec 四步闭环和 `///` 开发步骤。
- 当前策略：先做后端可快速闭环的 SSE、路径校验、SecretStr 和 SQLite migration，再做 Rust/Platform/CI/release/checklist。
- 已完成：PR1 SSE 短期 stream token、PR2 桌面 API 路径校验、PR3 Tauri 打开路径白名单、PR4 Platform required auth、PR5 SecretStr Pydantic 脱敏、PR6 CI/repo hygiene、PR7 release 制品清理、PR8 桌面 SQLite migration、PR9 发布验收清单。
- 已新增：`scripts/check_repo_hygiene.py`、`docs/release-checklist.md`、`release/.gitkeep`、`tests/desktop/api/test_sse_auth.py`、`tests/desktop/api/test_path_validation.py`、`tests/desktop/services/test_sqlite_store_migration.py`、`tests/platform/test_auth_cors.py`。
- 已验证：`python -m pytest tests/desktop/api/test_sse_auth.py tests/desktop/test_sse_chain_resilience.py -q` 通过，10 项通过。
- 已验证：`python -m pytest tests/desktop/api/test_path_validation.py tests/test_desktop_api_sidecar.py -q` 通过，18 项通过。
- 已验证：`python -m pytest tests/desktop/security/test_secret_str.py tests/test_desktop_api_sidecar.py -q` 通过，33 项通过。
- 已验证：`python -m pytest tests/desktop/services/test_sqlite_store_migration.py tests/desktop/services -q` 通过，53 项通过。
- 已验证：`python -m pytest tests/platform -q` 通过，38 项通过。
- 已验证：`python -m pytest tests/test_desktop_tauri_app_state.py -q` 通过，42 项通过。
- 已验证：`python scripts/check_repo_hygiene.py` 通过；`git ls-files release` 不再列出 release 安装包或诊断 PDF。
- 已验证：`npm run build` 在 `apps/desktop-tauri` 通过；仍有既有 CSS minify warning `Expected identifier but found "-"`。
- 已验证：`cargo check --locked` 在 `apps/desktop-tauri/src-tauri` 通过。
- 已验证：`git diff --check` 退出码 0，仅有 Windows LF/CRLF 提示。

## V3.8.7 Task 11 本机最终验收

- 已验证：全量非真实 API pytest `1590 passed, 8 skipped, 101 subtests`，总覆盖率 `82.85%`；diff coverage `84%`。
- 已验证：完整 unittest discovery `1004 tests OK, 7 skipped`；三表、OpenXML、JLV fixture 与 SC locator `104 passed, 37 subtests passed`。
- 已验证：Ruff、strict mypy 168 个源码文件、pip check、repository hygiene、git diff check、npm ci、npm audit high 和 npm build 全部通过。
- 已验证：安装 Visual Studio Build Tools 17.14.36、MSVC 14.44.35207 和 Windows SDK 10.0.26100.0 后，本机 `cargo check --locked` 通过。
- 未关闭：正式签名、RFC3161、真实安装卸载、Office 无修复打开和真实 API acceptance 必须取得外部证据。
- 未关闭：真实 JLV 第 4 条第(2)项 SC 召回仍不稳定，不能用 FakeGPT55 fixture 结果替代真实模型验收。
- 已执行真实 API acceptance：第一次调用完成图纸识别和 PFD/PFMEA/CP 主链，生成 4 个 OpenXML 可打开工作簿与 `run_manifest.json`；最后因 exporter 不兼容序列化 `quality_gate` 字典而失败。
- 已按 TDD 修复 exporter 的对象/字典兼容边界：回归测试先以同一 `AttributeError` 失败，修复后通过；对象输入兼容回归 `32 passed, 6 skipped, 37 subtests passed`。
- 已重跑真实 API acceptance：第二次 Responses 流式调用在 120 秒超时，管线按设计回落为 OCR 草案，验收在缺少 `adapter_metadata` 处停止；这次结果不能算真实视觉链路通过。
- 真实 JLV 最新状态：第一次调用定位到第 4 条转动力矩 `0.5~2.5Nm` 的 SC 候选，但 `confirmation_status=needs_human_review`，置信度 `0.42`；尚无 judge/human confirmed 证据。
- 已验证 exporter 修复：聚焦导出回归 `32 passed, 6 skipped, 37 subtests passed`；全仓 Ruff、Core/Desktop strict mypy 168 个源码文件、UTF-8、Mermaid 节点唯一和 `git diff --check` 通过。
- 已构建：唯一 internal 包 `MINOS-CORE_3.8.6_x64-internal-unsigned-setup.exe`，大小 `100394318` bytes，SHA256 `FBDA55F07C8D987033EDF65E9431AB3E5CBABA1CCA707ABF5282D985144202E8`，Authenticode 状态为 internal 预期的 `NotSigned`。
- 已修复：`verify_installer.ps1` 不再硬编码旧 `MINOS-CORE.exe`，而是从安装根目录唯一定位主程序并排除 sidecar/uninstaller；安装和卸载均同步等待并检查退出码，卸载前等待 PyInstaller sidecar 映像锁释放。
- 已验证：官方 `verify_installer.ps1` 对 3.8.6 internal 包真实通过；主程序和 sidecar 启动、Bearer health 200、无 token 401、安装目录进程清零、静默卸载和临时目录删除均完成。

## V3.8.7 真实 JLV req4 SC 聚焦稳定化

- 已执行聚焦 locator：54.69 秒定位第 4 条第(2)项 SC 候选，置信度 `0.82`，符号框和文本框非零，引用整页、技术要求总区及目标行裁剪。
- 已复现 judge 引用契约缺陷：模型输出 `confirmed`，但把页面裁剪 ID 写入 standard/symbol refs；verifier 正确降为 `needs_human_review`。
- 已按 TDD 修复：测试先失败，再明确 standard/symbol/page 三类字段各自允许的 evidence packet ID；聚焦 judge 测试 `5 passed`。
- 已复用同一候选和 packet 做三次修复后 judge-only：7.32 秒 `needs_human_review`、6.29 秒 `judge_confirmed`、6.74 秒 `judge_confirmed`，三次引用均通过 verifier 命名空间检查。
- 当前结论：引用契约缺陷已关闭，但真实模型业务 verdict 只有 2/3 确认，未达到连续三次 `judge_confirmed`；没有伪造 human confirmation，Task 11 继续保持未关闭。
