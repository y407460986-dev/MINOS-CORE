# 从 v2.0.1 迁移到 v3.0.0

v3.0.0 是一次以重构与可观测性为主的发布。主要补全四块基础能力（拆模块、AI 韧性、安全、可观测性），并新增插件扩展点。本指南列出对调用方可见的影响面与排查清单。

## 重要影响面一览

| 维度 | 影响 |
| --- | --- |
| Python 版本 | 仍是 `>= 3.11`，不变 |
| 公共导入路径 | 兼容；旧路径仍可用 |
| 运行时依赖 | **新增 `structlog>=24.1.0`** |
| CLI | 新增 `minos-core doctor` |
| 桌面 API | 启用 Bearer 鉴权（环境变量 `MINOS_DESKTOP_API_TOKEN`） |
| 扩展点 | 新增 `minos_core.plugins` 包 |
| 行为变更 | 默认 OCR 选择策略调整为优先 MinerU；细节见 ADR 002 |

## 1. 模块布局调整

`minos_desktop/services.py` 与 `minos_core/pipeline.py` 已经被拆分为同名 package（`minos_desktop/services/` 与 `minos_core/pipeline/`），并在 `__init__.py` 中 **重新导出原有公共符号**。

**对调用方的影响**：

- 如果你之前用：
  ```python
  from minos_desktop.services import DesktopRunService
  from minos_core.pipeline import generate_three_tables_from_drawing
  ```
  这两种写法在 v3.0 仍然有效。
- 如果你想精确一点，可以从子模块导入：
  ```python
  from minos_desktop.services.run_service import DesktopRunService
  from minos_core.pipeline.orchestration import generate_three_tables_from_drawing
  ```

详见 [ADR 001](adr/001-module-restructuring.md)。

## 2. 新增 `minos-core doctor`

v3.0 引入诊断命令：

```powershell
python -m minos_core.cli doctor
```

输出内容包括 Python 版本、可用 OCR 引擎、AI 配置、磁盘空间、关键依赖等。建议在部署或换环境后第一时间运行一次。

详见 [ADR 002](adr/002-ai-resilience.md)。

## 3. 桌面 API Bearer 鉴权

`minos_desktop.api.auth.require_api_token` 现在读取 **环境变量 `MINOS_DESKTOP_API_TOKEN`**：

- 若设置了 token：所有受保护路由必须携带 `Authorization: Bearer <token>`，否则 401 `UNAUTHORIZED`。
- 若未设置：依赖会放行（兼容本地脚本与单元测试）。

CLI 启动 `minos-desktop-api` 时若未提供 token，会自动通过 `secrets.token_urlsafe(24)` 生成并注入环境变量。Tauri 前端在启动 sidecar 时需要拿到同一个 token 才能访问。

可以通过 CLI 参数显式指定：

```powershell
minos-desktop-api --token <your-token>
```

详见 [ADR 003](adr/003-security-validation.md)。

## 4. 结构化日志

所有日志现在通过 `minos_core.observability.logging.get_logger` 走 `structlog`：

- 控制台默认输出彩色文本；
- 设置 `MINOS_LOG_JSON=1` 切换到 JSON 输出（便于聚合）；
- 设置 `MINOS_LOG_LEVEL=DEBUG` 调高级别。

调用方迁移建议：

```python
# 旧
import logging
logger = logging.getLogger(__name__)
logger.info("Doing work for %s", project_id)

# 新
from minos_core.observability.logging import get_logger
logger = get_logger(__name__)
logger.info("doing_work", project_id=project_id)
```

旧的 `logging.getLogger` 仍然可用，但不会享有结构化字段、上下文绑定等好处。

详见 [ADR 004](adr/004-observability.md)。

## 5. 错误模型

新增 `minos_core.observability.errors.MinosError` 作为根异常，子类有 `ConfigurationError`、`ValidationError`、`ExternalServiceError`、`ResourceError`、`PipelineError`，并多重继承自 `RuntimeError` / `ValueError`。

**老代码无需立即改动**：原本 `except RuntimeError`、`except ValueError` 仍能捕获到这些子类。建议新代码使用更精确的类型并通过 `format_error_for_user` 给出中文消息。

## 6. 插件扩展点

`minos_core.plugins` 是 v3.0 新增的扩展面：

- 协议：`OCREnginePlugin`、`KnowledgeSourcePlugin`
- 注册/查询：`register_ocr_engine`、`get_ocr_engine`、`iter_ocr_engines`、`register_knowledge_source` 等
- Entry-point 发现：`load_entry_point_plugins()`
- 错误：`PluginError`

**当前版本不会自动加载插件**。宿主显式调用 `load_entry_point_plugins()` 后插件才会进入注册表，并且 v3.0 主流水线尚未消费这些注册项；这是后续 Track 计划改造的部分。

详见 [ADR 005](adr/005-extensibility.md) 与 [插件指南](plugins.md)。

## 7. 是否有破坏性变更？

对最终用户（运行 CLI / 桌面应用）：**无破坏性变更**。所有 v2.0.1 的命令、文件输出格式、SQLite schema 均保持兼容。

对二次开发者：

- 没有删除/重命名任何已发布的公共 API。
- 全新的 `minos-desktop-api` 部署需要在前端配置 Bearer token，否则受保护接口会返回 401。
- 启动后第一次写日志时，控制台输出格式变成 `structlog` 风格（更结构化，但不再是裸 `logging.Formatter`）。

## 升级清单

1. `pip install -U minos-core`（或重新执行项目的依赖安装命令）。
2. 确认 `structlog>=24.1.0` 已经被解析到。
3. 跑一次 `minos-core doctor`，对照报告补齐缺失依赖与 AI 配置。
4. 启动桌面 API 前，确保 `MINOS_DESKTOP_API_TOKEN` 已设置（或让 CLI 自动生成并把值传给前端）。
5. 如果你的环境里有自定义 OCR / 知识源脚本，参考 [插件指南](plugins.md) 把它们打包成扩展。
