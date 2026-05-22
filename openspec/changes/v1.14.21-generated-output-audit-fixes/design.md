# Design: V1.14.21 Generated Output Audit Fixes

## Test Alignment
`generate_pfmea_from_confirmed_pfd` 已支持 `on_progress` checkpoint，因此 API 测试桩必须接受该参数。自动批量确认已经收紧到 CP 确认后的总审核阶段，测试应先确认 CP 再断言批量确认生效。

## Backup
直接复制 SQLite 主库文件在 WAL 模式下可能漏掉已提交但未 checkpoint 的数据。使用 `sqlite3.Connection.backup()` 生成临时库，再将临时库写入 zip。

## Packaging
Debug/check 场景可以生成占位 sidecar，但如果 `binaries/<sidecar>/_internal` 已存在真实 PyInstaller 内容，`build.rs` 不能再写 `.placeholder`。`release:nsis` 必须先运行 sidecar 构建，避免直接打包旧产物。

## Documentation
README 和流程图应反映当前事实：
- 默认模型为 `gpt-5.5`。
- 默认 Responses 地址为 `https://cx.allincoding.cc/responses`。
- Codex `base_url` 不再作为 MINOS 默认地址。
- 桌面测试命令引用现存测试文件。
