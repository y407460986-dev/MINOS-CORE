# Changelog

本文件记录 MINOS-CORE 的版本变更。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [Unreleased]

## [3.8.6] - 2026-06-29

### Security
- SSE 进度流增加短期 stream token 鉴权，未授权请求不能订阅
- 桌面 API 统一图纸文件与输出目录校验（扩展名、magic number、路径遍历、null byte）
- Tauri 打开路径命令收紧为白名单校验，只允许打开用户选择过或应用管理范围内的路径
- Platform API 增加 `MINOS_PLATFORM_AUTH_REQUIRED=1` 交付环境强制鉴权模式
- 修复 `SecretStr` Pydantic 序列化明文回显问题

### Added
- 桌面 SQLite 显式 schema version 与幂等 migration 骨架
- 仓库卫生脚本 `scripts/check_repo_hygiene.py`，CI 新增前端 build、Rust check 与卫生检查门
- 发布前验收清单 `docs/release-checklist.md`

### Changed
- 核心巨型模块低风险拆分：`pipeline_chain.py` 拆为 `pipeline_chain_pfd/pfmea/cp.py`，`drawing_ocr_analysis.py` 拆为 core/engines，`drawing_to_pfd.py` 拆出 build 模块，`table_editor.py` 拆为 `table_editor/` 包，`part_family_knowledge` 拆为 convert/load/match，CLI 拆为 `commands/` 子包
- 清理 Git 追踪的 release 安装包与诊断 PDF

### Fixed
- 修复 platform 测试 fixture 目录 SHA256 漂移导致 input-package 注册链路 422

## [3.8.5] - 2026-06-08

### Added
- 特殊特性（Special Characteristic）识别硬化，提升 SC/CC 检测准确率

### Fixed
- 启用桌面端混合绘图分析（hybrid drawing analysis）
- 在链式 PFD 中透出特殊特性候选结果
- 限制特殊特性候选仅为 SC 和 CC 类型

## [3.6.0] - 2026-06-04

### Changed
- 桌面端发布（desktop sidecar release），捕获 v3.6.0 发布资产
- NSIS 安装包默认包含 Geist 字体与配置

## [3.5.0] - 2026-06-04

### Changed
- 前端迁移到 Vercel 设计语言：Geist 字体 + 墨黑主色 + 6px 统一圆角

### Added
- Windows NSIS 安装包支持，含自动更新与配置迁移

## [3.3.0] - 2026-06-01

### Added
- **多图纸支持（Multi-Drawing）**：分三阶段落地
  - Phase 1：数据库、状态、API 模式、项目存储新增 `component_drawings` 字段
  - Phase 2：管道层接受 `component_drawings` 并渲染合并图纸页
  - Phase 3：前端多图纸 UI，包含组件图纸文件选择器与 Rust 命令
- 工作台表格增强：粘性横向滚动条、拖拽滚动、键盘快捷键
- PFMEA 上下文丰富化：集成 OCR 公差、检验要求、标准引用

### Fixed
- 应用 10 项代码审计修复：管道、通道生命周期、SSE、前端
- 控制计划（CP）阶段弹性增强 + 类级别撤销/重做栈 + API 端点 + 前端按钮
- 前端 `onDone` 添加 `try/catch`，改善链式启动错误引导
- 桌面端传递用户配置的模型到所有管道生成调用
- 包装撤销/重做按钮至 Fragment，修复 JSX 编译错误
- 修复 `DesktopProjectRecord` 中 `component_drawings` 字段的顺序以符合 dataclass 要求
- 强制 MinerU pipeline 后端用于 `ocr_only` 模式（替代缓慢的 VLM 默认）
- 启动时清理陈旧 sidecar 进程，防止端口漂移

## [3.2.1] - 2026-05-30

### Fixed
- 安全性修复：未处理的 Promise rejection、令牌暴露、认证、日志脱敏
- 为 `urllib.request.urlopen` mock 添加 `context` 参数以修复测试

## [3.2.0] - 2026-05-28

### Security
- 解决 v3.1.0 中发现的 5 个关键安全漏洞
- 增强 `.gitignore`，添加全面的敏感文件模式

### Added
- 桌面端 E2E 集成测试套件
- 撤销/重做栈的内存预算跟踪
- 项目专属开发指南文档

### Changed
- 所有依赖版本添加上限约束
- CLI 文件中的 `print()` 统一替换为 `structlog`
- 拆分过大的测试文件为聚焦的测试模块

### Fixed
- OpenAI LLM：保留 HTTP 错误上下文并脱敏处理
- CI：添加 GitHub 环境作用域以实现安全机密管理

## [3.1.0] - 2026-05-28

### Security
- API 密钥存储在系统密钥链（keyring）而非 SQLite 中
- 实现持久化认证令牌
- 处理 keyring 操作的错误场景与 TokenManager 异常

### Added
- 敏感数据脱敏模块（`minos_core.observability.redaction`）

### Fixed
- 质量门（quality gates）评估运行时的崩溃问题
- 敏感数据在日志列表与元组中的脱敏处理
- 日志脱敏规则正确应用到所有日志输出

### Tests
- 添加 keyring 存储失败时原子标志设置的测试

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

[Unreleased]: https://github.com/y407460986-dev/MINOS-CORE/compare/v3.8.6...HEAD
[3.8.6]: https://github.com/y407460986-dev/MINOS-CORE/compare/v3.8.5...v3.8.6
[3.8.5]: https://github.com/y407460986-dev/MINOS-CORE/compare/v3.6.0...v3.8.5
[3.6.0]: https://github.com/y407460986-dev/MINOS-CORE/compare/v3.5.0...v3.6.0
[3.5.0]: https://github.com/y407460986-dev/MINOS-CORE/compare/v3.3.0...v3.5.0
[3.3.0]: https://github.com/y407460986-dev/MINOS-CORE/compare/v3.2.1...v3.3.0
[3.2.1]: https://github.com/y407460986-dev/MINOS-CORE/compare/v3.2.0...v3.2.1
[3.2.0]: https://github.com/y407460986-dev/MINOS-CORE/compare/v3.1.0...v3.2.0
[3.1.0]: https://github.com/y407460986-dev/MINOS-CORE/compare/v3.0.0...v3.1.0
[3.0.0]: https://github.com/y407460986-dev/MINOS-CORE/releases/tag/v3.0.0
