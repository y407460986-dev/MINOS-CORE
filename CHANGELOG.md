# Changelog

本文件记录 MINOS-CORE 的版本变更。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [3.0.0] - 2026-05-28

v3.0.0 是一次以重构与基础设施为主的发布。围绕 4 个 Track 落地，并在 Track 5 补齐文档与扩展点。

### Added

- **Track 1 – Module Restructuring**：拆分 `minos_desktop/services.py` 与 `minos_core/pipeline.py` 为同名 package；`quality_gates/_support.py` 拆为 `core_evaluators` / `evidence_coverage` / `export_gate` / `report_projections`。所有原导入路径仍可用。详见 [ADR 001](docs/adr/001-module-restructuring.md)。
- **Track 2 – AI Resilience**：新增 `minos_core/ai_resilience/`（service pool、retry strategy、circuit breaker、fallback strategies），新增 `minos_core/ocr_detection.py` 自动检测可用 OCR 引擎，新增 `minos-core doctor` 诊断命令，质量门规则外置为 `config/quality_gates.yaml`。详见 [ADR 002](docs/adr/002-ai-resilience.md)。
- **Track 3 – Security**：新增 `minos_desktop/security/`（`SecretStr`、`SecureAPIKeyStore`、`AuthMiddleware`），桌面 API 通过 `MINOS_DESKTOP_API_TOKEN` 启用 Bearer 鉴权。详见 [ADR 003](docs/adr/003-security-validation.md)。
- **Track 4 – Observability**：新增 `minos_core/observability/`（`structlog` 日志、`MinosError` 错误层、资源上下文管理器、配置诊断），日志支持 JSON / 控制台双格式与 contextvar 关联 ID。详见 [ADR 004](docs/adr/004-observability.md)。
- **Track 5 – Plugins & Documentation**：新增 `minos_core/plugins/`（`OCREnginePlugin` / `KnowledgeSourcePlugin` 协议、注册表、entry-point 发现），新增 `docs/architecture/`、`docs/plugins.md`、`docs/MIGRATION.md`。详见 [ADR 005](docs/adr/005-extensibility.md)。

### Changed

- 默认 OCR 引擎选择策略调整为 MinerU 优先，未安装时回退到 RapidOCR / PDF text。
- 全局日志切换到 `structlog`，控制台与 JSON 输出由 `MINOS_LOG_JSON` 控制。

### Dependencies

- 新增运行时依赖 `structlog>=24.1.0`。
- `keyring` 用于 `SecureAPIKeyStore`，按需安装即可（不在核心依赖中强制要求）。

### Migration

升级要点见 [MIGRATION 指南](docs/MIGRATION.md)。无对最终用户可见的破坏性变更。
