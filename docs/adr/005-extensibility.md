# ADR 005: Plugin Extensibility (OCR Engines & Knowledge Sources)

**Status**: Accepted

**Date**: 2026-05-28

**Context**: Track 5 - Documentation & Extensibility

## Context

MINOS-CORE 在三表生成链路上有两个高频被定制的环节：

1. **OCR 引擎**：不同客户偏好不同的 OCR 后端（MinerU、RapidOCR、PDF text、定制 OCR 服务），但代码中 OCR 选择是硬编码的。
2. **零件族知识源**：知识库内容因行业而异（汽车冲压、半导体封装、注塑等），客户希望注入自家的工艺数据，而不必 fork core。

之前可行的扩展方式是：fork 仓库或者打 monkey-patch。两种都不可持续：升级时合并冲突大，且 monkey-patch 一旦失败会拖垮主流程。

## Decision

引入一个最小但完整的插件机制，仅暴露两类扩展点，不在 v3.0 主流程中触发自动加载（避免无意中改变默认行为）。

### 扩展点

- `OCREnginePlugin`（结构化 Protocol）：必须提供 `name: str` 和 `analyze(pages, *, context) -> dict`。
- `KnowledgeSourcePlugin`（结构化 Protocol）：必须提供 `family_key: str` 和 `load() -> dict`。

### 注册与查询

`minos_core.plugins` 模块提供：

- `register_ocr_engine(plugin)` / `register_knowledge_source(plugin)`
- `get_ocr_engine(name)` / `get_knowledge_source(family_key)`
- `iter_ocr_engines()` / `iter_knowledge_sources()`
- `reset_registry()`（用于测试）
- `PluginError`（继承自 `MinosError`，code=`MINOS_PLUGIN_ERROR`）

实现保存在内存字典中，重复注册或访问未注册名都会抛 `PluginError`。

### Entry-point 发现

`minos_core.plugins.entrypoints.load_entry_point_plugins()` 通过 `importlib.metadata.entry_points()` 发现：

- `minos_core.ocr_engines` 组中的 OCR 插件；
- `minos_core.knowledge_sources` 组中的知识源插件。

每个 entry point 加载到的对象：如果已经实现协议（带 `name` / `family_key` 属性），直接注册；否则当作零参工厂，调用一次再注册。

加载或注册阶段任何异常都通过 `minos_core.observability.logging.get_logger` 写入结构化警告日志，**不会** 中断宿主进程或后续插件。

### 不在本期范围

- **不** 自动调用 `load_entry_point_plugins()`：宿主必须显式触发，避免 import-time 副作用。
- **不** 改写现有 OCR / 知识库调用点：`minos_core.pipeline` 仍然使用内置实现。后续 Track 会补充把已注册插件接入主链路的工作。
- **不** 增加新的运行时依赖：`importlib.metadata` 是标准库，`structlog` 已由 ADR 004 引入。

## Consequences

### Positive

1. 第三方可以通过普通 Python 包发布扩展，只需要在 `pyproject.toml` 中声明 entry point，无需改动 core 源码。
2. 插件可以在测试中通过 `reset_registry()` 完全隔离，单元测试稳定。
3. `PluginError` 与 `MinosError` 共用错误模型，桌面 API/CLI 可以统一处理。

### Negative

1. 主链路尚未真正消费插件，目前仅限于注册与查询（按 YAGNI 主动收口）。
2. 协议是结构化（`Protocol`），运行时会做属性/方法存在性检查，但不会校验签名细节。

### Neutral

1. 注册器是进程内字典：跨进程或跨 venv 不共享。
2. 已注册的插件会一直存活直到进程退出（或显式调用 `reset_registry`）。

## Implementation Status

**Completed**:

- ✅ `minos_core/plugins/registry.py`（注册表 + 协议）
- ✅ `minos_core/plugins/entrypoints.py`（entry point 发现）
- ✅ `tests/test_plugins_registry.py` / `tests/test_plugins_entrypoints.py`
- ✅ `docs/plugins.md`（用户指南）

**Pending**:

- ⏳ 把已注册插件接入 `pipeline.drawing_analysis` 与 `part_family_knowledge` 的运行时选择路径。
- ⏳ 在 `minos-core doctor` 中可选地展示插件注册情况。

## References

- `minos_core/plugins/__init__.py`
- `minos_core/plugins/registry.py`
- `minos_core/plugins/entrypoints.py`
- `docs/plugins.md`

## Related ADRs

- ADR 001: Module Restructuring
- ADR 004: Observability（提供 `MinosError` 与 structured logging）

### Status Update (2026-06-26)

Phase 3 of the MINOS-CORE remediation plan reviewed this ADR:

| Item | Status | Notes |
|------|--------|-------|
| `registry.py` (registration + query + protocol) | ✅ Done | Registration, query, iteration, and reset support present |
| `entrypoints.py` (entry point discovery) | ✅ Done | `load_entry_point_plugins()` uses `importlib.metadata.entry_points()` for `minos_core.ocr_engines` and `minos_core.knowledge_sources` groups |
| Plugin unit tests | ✅ Done | `tests/test_plugins_registry.py` and `tests/test_plugins_entrypoints.py` exist |
| `docs/plugins.md` user guide | ✅ Done | Plugin documentation exists |
| Wire plugins into `pipeline.drawing_analysis` & `part_family_knowledge` runtime selection | ⏳ Still pending | No references to `load_entry_point_plugins`, `get_ocr_engine`, or `get_knowledge_source` in `pipeline_chain.py`, `drawing_to_pfd.py`, or `part_family_knowledge.py` |
| Plugin status in `minos-core doctor` | ⏳ Still pending | No "plugin" reference found in `cli_doctor.py` |
