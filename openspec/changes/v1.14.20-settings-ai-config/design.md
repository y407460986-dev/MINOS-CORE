# Design: V1.14.20 Settings AI Config

## Config Priority
`minos_core.ai_config` 增加 DB override 层：
1. `MINOS_OPENAI_*` / `OPENAI_*` / `ARK_*` 等显式环境变量。
2. 桌面 SQLite settings 中保存的 override。
3. Codex auth、ARK fallback 和 MINOS 默认值。

## API
`PATCH /api/settings/ai-config` 接收可选 `base_url`、`api_key`、`model`：
- 空字符串表示清除对应 override。
- API Key 留空且字段缺失表示保持不变。
- 返回 settings 时只返回 `api_key_override_set`。

## UI
设置页显示服务地址、API Key、模型名：
- 环境变量锁定时禁用对应输入。
- API Key 用 password 输入框，留空保持不变。
- “清除自定义”清空三项 override。

## Safety
远端 HTTP URL 会泄漏 Bearer Key，因此保存时拒绝；本机 `127.0.0.1`、`localhost`、`::1` 可使用 HTTP 代理。
