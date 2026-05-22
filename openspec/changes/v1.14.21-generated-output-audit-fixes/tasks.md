# Tasks: V1.14.21 Generated Output Audit Fixes

## Define
- [x] /// 1. 审查当前生成物、未提交改动、测试和文档记录。
- [x] /// 2. 明确只修复已复现问题，不扩大功能范围。

## Specify
- [x] /// 3. API 测试必须匹配当前链式流程规则。
- [x] /// 4. SQLite 备份必须包含 WAL 中已提交数据。
- [x] /// 5. Tauri check/build 不得污染真实 sidecar 目录。
- [x] /// 6. 文档和流程图必须与当前默认 AI URL、模型、测试文件一致。

## Implement
- [x] /// 7. 更新 API sidecar 测试桩和 CP 确认后批量确认断言。
- [x] /// 8. 给数据备份增加 WAL 回归测试，并改用 SQLite 在线 backup。
- [x] /// 9. 修改 Tauri `build.rs` 只在 `_internal` 缺失或为空时写占位文件。
- [x] /// 10. 修改 npm release 脚本和 PowerShell 发布脚本。
- [x] /// 11. 更新 README、OpenSpec V1.13 和 `project_flow.mmd`。

## Verify
- [x] /// 12. 运行 Python 聚焦回归。
- [x] /// 13. 运行 Tauri 前端构建和 Rust `cargo check`。
- [x] /// 14. 运行 `git diff --check` 和可打开性检查。
