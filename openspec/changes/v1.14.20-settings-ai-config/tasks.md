# Tasks: V1.14.20 Settings AI Config

## Define
- [x] /// 1. 明确问题：安装版用户需要在软件内配置 AI 服务。
- [x] /// 2. 明确非目标：不新增多 provider，不改变三表生成逻辑。

## Specify
- [x] /// 3. 定义优先级：环境变量 > 设置页/SQLite > Codex auth / ARK fallback / 默认。
- [x] /// 4. 定义脱敏：API Key 只显示是否已配置，不回显明文。
- [x] /// 5. 定义 URL 安全边界：远端 HTTPS，本机 HTTP 允许。

## Implement
- [x] /// 6. `ai_config` 支持 DB override provider。
- [x] /// 7. `DesktopSettingsStore` 支持 AI override 读写和状态返回。
- [x] /// 8. 新增 `PATCH /api/settings/ai-config`。
- [x] /// 9. 设置页新增 AI 服务配置卡片。
- [x] /// 10. 文本和多模态 LLM HTTP 错误不回显上游响应体。

## Verify
- [x] /// 11. AI 配置优先级测试通过。
- [x] /// 12. API 脱敏测试通过。
- [x] /// 13. Tauri 静态测试和前端构建通过。
