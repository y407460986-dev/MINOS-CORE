# 模块地图

本文件列出 MINOS-CORE v3.0 主要 Python 包的职责和公共入口（以各包 `__init__.py` 实际导出的符号为准）。导入路径均相对仓库根目录。

## minos_core.pipeline

负责 APQP 三表生成的整体编排：图纸分析、三表生成、复核与导出。是核心库对外的主要入口。

公共入口（节选自 `minos_core/pipeline/__init__.py`）：

- `analyze_drawing_for_three_table_chain`
- `generate_three_tables_from_drawing`
- `assemble_generated_apqp_chain`
- `apply_review`、`apply_edit_patch`
- `evaluate_edit_export_gate`、`export_edited_three_tables`
- `validate_fixture`、`export_fixture`、`export_draft_fixture`
- 常量：`PIPELINE_STAGES`、`ANALYSIS_MODES`、`OCR_ENGINES`、`DEFAULT_OCR_ENGINE`

`minos_core.pipeline_chain` 仍保留 `generate_pfd_from_drawing` / `generate_pfmea_from_confirmed_pfd` / `generate_cp_from_confirmed_pfmea` 三个分阶段函数，由 `pipeline.orchestration` 调度。

## minos_core.ai_resilience

AI 服务调用的韧性层：多端点轮询、退避重试、熔断、降级。所有外部 AI 调用都应该走这一层。

公共入口（来自 `minos_core/ai_resilience/__init__.py`）：

- `AIServicePool`、`AIEndpoint`
- `ExponentialBackoffRetry`、`RetryConfig`
- `CircuitBreaker`、`CircuitBreakerConfig`、`CircuitState`、`CircuitBreakerOpenError`
- `FallbackStrategy`、`LocalKnowledgeFallback`、`RuleBasedFallback`、`CachedResponseFallback`、`ChainedFallback`

详见 [ADR 002](../adr/002-ai-resilience.md)。

## minos_core.observability

集中提供日志、错误模型、资源管理、配置诊断。

公共入口（来自 `minos_core/observability/__init__.py`）：

- 日志：`configure_logging`、`get_logger`、`bind_request_context`、`unbind_request_context`、`clear_request_context`
- 错误：`MinosError`、`ConfigurationError`、`ValidationError`、`ExternalServiceError`、`ResourceError`、`PipelineError`、`format_error_for_user`、`format_error_for_log`
- 资源：`temporary_directory`、`managed_subprocess`
- 配置诊断：`ConfigSource`、`describe_config_sources`、`format_config_sources`

详见 [ADR 004](../adr/004-observability.md)。

## minos_core.adapters

输入与外部系统适配器（fixture、legacy Excel、OCR 实现等）。`__init__.py` 仅导出 `convert_legacy_workbook` 和 `load_fixture_payload`；其它模块（`mineru_ocr`、`openai_llm`、`multimodal` 等）按需深度导入。

## minos_core.quality_gates

阶段质量门：判断链路是否可继续以及是否允许导出。

公共入口（来自 `minos_core/quality_gates/__init__.py`）：

- `evaluate_export_gate`、`require_export_gate`
- 阶段评估器：`evaluate_analysis_bundle_gate`、`evaluate_pfd_bundle_gate`、`evaluate_pfmea_bundle_gate`、`evaluate_control_plan_bundle_gate`、`evaluate_failure_mode_candidates_gate`、`evaluate_brainstorm_failure_modes_input_gate`
- 数据类：`StageQualityGate`、`ExportGateError`

## minos_core.exporters

Excel 工作簿导出。`__init__.py` 导出 `export_apqp_workbook`、`WorkbookWriter`、`sanitize_sheet_name`；三表分发由 `exporters.three_table_workbooks` 实现，被 `pipeline` 直接 re-export。

## minos_core.plugins

插件扩展点（v3.0 新增）：注册自定义 OCR 引擎与知识源。

公共入口：

- 注册：`register_ocr_engine`、`register_knowledge_source`
- 查询：`get_ocr_engine`、`get_knowledge_source`、`iter_ocr_engines`、`iter_knowledge_sources`
- Entry-point 发现：`load_entry_point_plugins`
- 协议：`OCREnginePlugin`、`KnowledgeSourcePlugin`
- 错误：`PluginError`

详见 [ADR 005](../adr/005-extensibility.md) 和 [插件指南](../plugins.md)。

## minos_desktop.services

UI-neutral 桌面业务层（SQLite + 三表运行编排）。

公共入口（来自 `minos_desktop/services/__init__.py`）：

- `DesktopSQLiteStore`、`DesktopProjectStore`、`DesktopSettingsStore`、`DesktopKnowledgeStore`
- `DesktopDataManagementService`
- `DesktopRunService`、`format_desktop_failure`
- `DEFAULT_DESKTOP_DB_PATH`、`DEFAULT_DESKTOP_OUTPUT_DIR`
- 透出 `analyze_drawing_for_three_table_chain` 以便 UI 端复用

## minos_desktop.api

本地 FastAPI sidecar。

公共入口（来自 `minos_desktop/api/__init__.py`）：

- `app`、`create_app`

`auth.py` 中的 `require_api_token` 依赖环境变量 `MINOS_DESKTOP_API_TOKEN` 进行 Bearer 鉴权（详见 [ADR 003](../adr/003-security-validation.md)）；具体路由模块为 `routes_projects`、`routes_runs`、`routes_tables`、`routes_exports`、`routes_closure`、`routes_health`、`routes_knowledge`、`routes_settings`、`routes_sse`。
