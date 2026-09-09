# 模块地图

本文件列出 MINOS-CORE v3.8 主要 Python 包的职责和公共入口（以各包 `__init__.py` 实际导出的符号为准）。导入路径均相对仓库根目录。

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

内部模块：

| 模块 | 职责 |
| --- | --- |
| `plugins/registry.py` | 进程内字典注册表，按名称查找引擎/知识源 |
| `plugins/entrypoints.py` | 通过 `pyproject.toml` entry points 自动发现并注册插件 |

## minos_core.pipeline（子模块）

`pipeline/` 子包将原先单文件的编排逻辑拆为独立模块，每个模块聚焦一个阶段。

| 子模块 | 职责 |
| --- | --- |
| `pipeline/drawing_analysis.py` | 图纸分析编排：调用 OCR + 多模态视觉 + 零件族上下文 |
| `pipeline/family_context.py` | 零件族上下文提取与写入 |
| `pipeline/hybrid_fusion.py` | OCR 与多模态结果的融合逻辑 |
| `pipeline/orchestration.py` | 三表生成主编排器：串联 PFD / PFMEA / CP 三步 |
| `pipeline/review_export.py` | 复核注入、导出门评估、最终导出 |
| `pipeline/utilities.py` | 管道内共享工具函数 |
| `pipeline/_llm_protected.py` | 受保护的 LLM 调用包装（带韧性层） |

## minos_core._types

`_types.py` 提供 TypedDict 类型别名，替换散落的 `dict[str, Any]` 返回值标注，使数据流更易追踪与重构。

- `DrawingAnalysisResult` — 图纸分析结果形状
- `DrawingPage` — 渲染图纸页面形状
- `QualityGateResult` — 质量门评估结果形状

## minos_core.edit_patch / edit_patch_reports

复核变更（edit patch）的构建、应用与导出。

| 模块 | 公共符号 |
| --- | --- |
| `edit_patch.py` | `EDIT_PATCH_VERSION`、`EditPatchError`、`apply_edit_patch`、`evaluate_edit_export_gate`、`export_edited_three_tables` |
| `edit_patch_reports.py` | Edit patch 可视化报告生成 |

## minos_core.characteristic_registry

特性注册表：在 APQP 三维表格中附加/构建 SC/CC 特性映射。

公共入口（来自 `__init__.py`）：

- `attach_characteristics_to_three_tables`
- `build_characteristic_registry`

## minos_core.special_characteristic_*

特殊特性（SC/CC）的发现、判定与视觉定位。以一组平级文件组织，而非子包：

| 文件 | 职责 |
| --- | --- |
| `special_characteristic_candidates.py` | 从图纸分析结果中提取 SC/CC 候选 |
| `special_characteristic_discovery.py` | 基于 OCR 文本的 SC/CC 自动发现 |
| `special_characteristic_declarations.py` | 图纸上 SC/CC 声明的解析 |
| `special_characteristics_evidence.py` | SC/CC 证据汇总 |
| `special_characteristics_judge.py` | 基于规则的 SC/CC 判定逻辑 |
| `special_characteristics_visual_locator.py` | 在图纸图像上定位 SC/CC 标记的可视区域 |

## minos_core.cli

CLI 命令解析与处理统一由 `minos_core/cli.py` 实现。`minos_core.commands` 仅保留包标识，不再维护不可达的同名命令处理器副本。

主要子命令包括 `generate-three-tables`、`validate`、`export`、`accept-three-tables`、`doctor` 与 `compare-ocr-engines`。

## minos_core.part_family_knowledge

零件族知识的加载、索引、匹配和种子转换统一由 `minos_core/part_family_knowledge.py` 提供；旧的平级拆分副本已移除，避免出现两个权威实现。

## minos_core.three_table_linkage

三表联动分析：PFD / PFMEA / CP 之间的 traceability 映射、间隙检测与质量评估。

公共入口（来自 `__init__.py`）：

- `build_three_table_linkage_map`
- `evaluate_three_table_linkage`
- `find_linkage_gaps`

## minos_desktop.security

桌面端安全模块：API Key 安全存储与请求鉴权。

| 模块 | 公共符号 |
| --- | --- |
| `security/secret_str.py` | `SecretStr` — 秘密字符串包装 |
| `security/api_key_store.py` | `SecureAPIKeyStore` — 加密 API Key 存储 |
| `security/auth_middleware.py` | `AuthMiddleware`、`require_auth` — 请求鉴权中间件 |
| `security/token_manager.py` | Token 生命周期管理 |

## minos_desktop.table_editor

桌面端表格编辑器：行级 CRUD、Patch 构建、自动化复核。

| 模块 | 职责 |
| --- | --- |
| `table_editor/specs.py` | 表格规格定义：列标签、行状态、表结构 |
| `table_editor/rows.py` | 行操作：过滤、确认、软删除、排序、模型转换 |
| `table_editor/patches.py` | Patch 构建：自动化复核 patch、编辑 patch、临时 patch |
| `table_editor/models.py` | 业务模型：变更影响、知识推荐、复核 dashboard、导航 |

## minos_desktop.services

UI-neutral 桌面业务层（SQLite + 三表运行编排）。

公共入口（来自 `minos_desktop/services/__init__.py`）：

- `DesktopSQLiteStore`、`DesktopProjectStore`、`DesktopSettingsStore`、`DesktopKnowledgeStore`
- `DesktopDataManagementService`
- `DesktopRunService`、`format_desktop_failure`
- `DEFAULT_DESKTOP_DB_PATH`、`DEFAULT_DESKTOP_OUTPUT_DIR`
- 透出 `analyze_drawing_for_three_table_chain` 以便 UI 端复用

内部模块：

| 模块 | 职责 |
| --- | --- |
| `services/run_service.py` | 桌面运行编排：校验、生成、复核、导出全流程 |
| `services/run_chain.py` | 链状态管理 |
| `services/run_exports.py` | 桌面端导出逻辑 |
| `services/run_patches.py` | 桌面端 patch 应用逻辑 |
| `services/project_store.py` | 项目 SQLite 存储 |
| `services/settings_store.py` | 设置 SQLite 存储 |
| `services/knowledge_store.py` | 知识库 SQLite 存储 |
| `services/sqlite_store.py` | 基础 SQLite 存储抽象 |
| `services/data_management_service.py` | 数据管理（导入/导出/清理） |

## minos_desktop.app_state / chain_state

桌面端状态模型。

| 模块 | 典型类型 |
| --- | --- |
| `app_state.py` | `DesktopProjectState`、`DesktopRunState`、`DesktopRunRecord`、`DesktopExportRecord`、`DesktopAIConfigState`、`GenerationRunSummary` |
| `chain_state.py` | 三表链状态跟踪 |

## minos_desktop.api

本地 FastAPI sidecar。

公共入口（来自 `minos_desktop/api/__init__.py`）：

- `app`、`create_app`

`auth.py` 中的 `require_api_token` 依赖环境变量 `MINOS_DESKTOP_API_TOKEN` 进行 Bearer 鉴权（详见 [ADR 003](../adr/003-security-validation.md)）。

路由模块（`api/routes_*.py`）：

| 路由 | 功能 |
| --- | --- |
| `routes_projects` | 项目 CRUD |
| `routes_runs` | 三表运行管理 |
| `routes_tables` | 表格数据查询 |
| `routes_exports` | 导出 |
| `routes_closure` | 关闭任务（变更影响、知识推荐、review issue 等） |
| `routes_health` | 健康检查 |
| `routes_knowledge` | 知识库管理 |
| `routes_settings` | 设置管理 |
| `routes_sse` | SSE 事件推送 |
| `routes_auth` | API token 认证 |

附加 API 模块：

| 模块 | 功能 |
| --- | --- |
| `api/app.py` | FastAPI app 工厂与生命周期 |
| `api/cli.py` | 桌面 API CLI 入口 |
| `api/jobs.py` | 后台任务管理（状态轮询、任务队列） |
| `api/sse.py` | SSE 流实现 |
| `api/schemas.py` | Pydantic 请求/响应模型 |
