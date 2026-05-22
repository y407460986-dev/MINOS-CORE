# Proposal: V1.14.20 Settings AI Config

## Why
安装版用户不能合理地修改系统环境变量或 Codex 配置文件。MINOS-CORE 需要在桌面设置页提供 AI 服务地址、API Key 和模型名配置入口，同时保留环境变量优先级和密钥脱敏。

## What
- 设置页新增 AI 服务配置卡片。
- SQLite settings 保存 `base_url`、`api_key`、`model` override。
- AI 配置优先级为显式环境变量 > 设置页 override > Codex auth / ARK fallback / 默认值。
- API Key 只允许写入和清除，不回显明文。
- 远端 AI URL 必须 HTTPS；本机 HTTP 代理允许用于调试。
- LLM HTTP 错误不回显上游响应体。

## Non-goals
- 不改变三表生成业务逻辑。
- 不删除 Codex auth 复用。
- 不支持多 provider UI。

## Acceptance
- 无环境变量时，设置页保存的 AI URL、API Key、模型名生效。
- 有显式环境变量时，环境变量优先生效且设置页显示锁定。
- API 响应、错误和日志不包含明文 API Key。
