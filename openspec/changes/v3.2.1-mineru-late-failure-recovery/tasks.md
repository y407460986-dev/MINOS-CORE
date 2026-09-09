# Tasks: V3.2.1 MinerU Late Failure Recovery

## Define
- [x] /// 1. 意图：确认真实失败点。输入：运行记录 failure_message 和用户说明“识别已完成但仍报错”。输出：失败点定位为 MinerU CLI 本地连接/后处理失败。验证：run #1 原始错误包含 `MinerU OCR failed` 与 `All connection attempts failed`。

## Specify
- [x] /// 2. 意图：锁定 MinerU 已落盘 Markdown 时不应整次失败。输入：适配器非零退出路径。输出：`test_uses_mineru_markdown_output_when_cli_reports_late_failure`。验证：测试先红，当前实现直接抛 `OCRDependencyError`。
- [x] /// 3. 意图：锁定桌面错误归因。输入：包含 `mineru-api` 和 `All connection attempts failed` 的错误文本。输出：`test_failure_formatter_identifies_mineru_local_connection_failure`。验证：测试先红，当前实现误判为 AI 配置缺失。

## Implement
- [x] /// 4. 意图：最小恢复 MinerU 已有输出。输入：`minos_core/adapters/mineru_ocr.py`。输出：失败分支先读取 Markdown，有结果则返回。验证：MinerU adapter 新测试通过。
- [x] /// 5. 意图：修正桌面失败归因。输入：`minos_desktop/services/run_service.py`。输出：MinerU 本地连接失败优先于通用 `api/key` 判断。验证：formatter 新测试通过。

## Verify
- [x] /// 6. 意图：运行聚焦回归。输入：MinerU adapter、桌面错误 formatter、OCR mode API 测试。输出：pytest 通过记录。验证：命令 exit 0。
- [x] /// 7. 意图：重新封装 3.2.1。输入：`scripts/build_release.ps1`。输出：新的 `MINOS-CORE_3.2.1_x64-setup.exe`。验证：安装包存在、哈希记录、可读性检查通过。
