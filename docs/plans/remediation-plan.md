# MINOS-CORE 全面整改计划

**基线**: v3.8.5 | **范围**: 🔴🟡🟢 全部 | **方式**: 分阶段逐步执行，每阶段结束后 review

---

## 总览

```
Phase 1 ─→ Phase 2 ─→ Phase 3 ─→ Phase 4 ─→ Phase 5
极速修复    工具链加固    代码手术    文档重建    测试纵深
 1-2天       1天          3-4天       1-2天       2-3天
```

**总预计**: 8-12 天（并行子代理可压缩到 5-7 天）

---

## Phase 1：极速修复（1-2 天）

**目标**：解决阻塞性问题，让 CI 变绿，消灭低 hanging fruit

### 1.1 修复 28 个测试失败

| 失败组 | 文件 | 根因 | 方案 |
|--------|------|------|------|
| config_diagnostics | `test_observability_config_diagnostics.py` | 默认 URL 从 "allincoding" 改成 "allincode.top" 未同步 | 更新测试期望值 |
| CP batch | `test_add_update.py` | `build_automation_review` 不再返回 CP batch 确认候选项 | 追 API 变更调整断言 |
| platform 路由 | `test_platform_*.py` | DB 路径/环境依赖 | 修正 fixture 路径 |
| CLI | `test_cli.py` | 输出目录依赖 | 隔离 tmp_path |

**验证**: `python -m unittest discover -s tests -v` 全部通过

### 1.2 更新 CHANGELOG

- 从 `git log` 重构 v3.1.0 → v3.8.5 每条变更
- 按 Keep a Changelog 格式（已引用但未遵守）
- 添加 `[Unreleased]` 节
- 给每个版本加 GitHub 比较链接

**验证**: CHANGELOG.md 包含 8 个版本条目

### 1.3 补全缺失的 git tag

```bash
git tag v3.2.1 <commit-hash>
git tag v3.3.0 <commit-hash>
git tag v3.6.0 <commit-hash>
git tag v3.8.5 HEAD
```

**验证**: `git tag -l` 输出 9 个标签

### 1.4 冻结 domain dataclass

- `domain.py` 全部 10 个 dataclass 加 `frozen=True`
- 定位所有 `dataclasses.replace()` 或构造器新的调用点
- 确保 `from_mapping()` 工厂方法兼容

**验证**: 所有测试通过 + `domain.py` 中无可变 dataclass

### 1.5 切换 16 个文件从 logging → structlog

受影响的文件：
- `adapters/ocr.py`, `adapters/llm_text.py`
- `automation_review.py`, `knowledge_recommendation.py`
- `ai_resilience/circuit_breaker.py`, `fallback.py`, `retry_strategy.py`, `service_pool.py`
- `pipeline_chain.py`, `edit_patch.py`, `analysis.py`
- etc.（共 16 个）

模式：
```python
# Before
import logging
logger = logging.getLogger(__name__)
logger.info("msg %s", var)

# After
from minos_core.observability.logging import get_logger
logger = get_logger(__name__)
logger.info("msg", var=var)
```

**验证**: `grep -rn "import logging" minos_core/ minos_desktop/` 无结果

### 1.6 安全 quick-fix

- `routes_knowledge.py:93,98` 加 `InputValidator.validate_path_traversal()`
- `data_management_service.py:136` f-string 表名改用白名单 + 参数化模式
- FastAPI 加安全中间件（`Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options`）

**验证**: 安全扫描报告对应项从 WARN 降为 PASS

---

## Phase 2：工具链加固（1 天）

**目标**：建立 CI 门禁，防止新代码引入同类问题

### 2.1 Dependabot 配置

创建 `.github/dependabot.yml`，覆盖 Python (pip)、npm、cargo。

**验证**: Dependabot 在 GitHub 仓库设置中可识别

### 2.2 CI 增强

在 `.github/workflows/ci.yml` 中追加：

| 步骤 | 工具 | 说明 |
|------|------|------|
| Python lint | `ruff check --output-format=github` | 风格 + 常见错误 |
| Python 安全扫描 | `pip-audit` | 已知 CVE 检测 |
| Python 类型检查 | `mypy --strict` | 类型错误检测 |
| npm audit | `npm audit --audit-level=high` | 前端依赖扫描 |
| Cargo audit | `cargo audit` | Rust 依赖扫描 |
| pip 缓存 | `actions/cache` for `~/.cache/pip` | 加速安装 |
| Cargo 缓存 | `Swatinem/rust-cache` | 加速构建 |

**验证**: CI pipeline 所有步骤通过

### 2.3 补齐 pyproject.toml 声明

添加缺失运行时依赖：`httpx`, `openpyxl`, `pydantic`, `PyYAML`, `shapely`, `opencv-python`, `tqdm`

添加 `[project.optional-dependencies] dev` 组：
- `ruff>=0.5,<1`
- `mypy>=1.10,<2`
- `pip-audit>=2.7,<3`

### 2.4 项目工具配置

| 文件 | 内容 |
|------|------|
| `.editorconfig` | 缩进、换行、编码统一 |
| `.pre-commit-config.yaml` | ruff check + ruff format |
| `pyproject.toml [tool.ruff]` | lint 规则配置 |
| `pyproject.toml [tool.mypy]` | 类型检查配置 |

**验证**: `ruff check .` 和 `mypy minos_core/` 通过

---

## Phase 3：代码手术（3-4 天）

**目标**：偿还架构债务，拆分大文件，接入未使用的组件

### 3.1 拆分 run_service.py（2,083 行）

```
minos_desktop/services/
├── run_service.py          ← 剥离后保留编排核心 (~400 行)
├── run_chain.py            ← 链式流程编排（新文件）
├── run_patches.py          ← 撤销/重做/补丁应用（新文件）
├── run_exports.py          ← 导出逻辑（新文件）
└── __init__.py
```

**验证**: 功能不变，所有测试通过

### 3.2 拆分 table_editor.py（2,118 行）

```
minos_desktop/
├── table_editor.py         ← 核心编辑器逻辑 (~500 行)
├── table_editor_selection/ ← 选择/光标管理
├── table_editor_undo/      ← 撤销重做
└── table_editor_export/    ← 导出
```

### 3.3 拆分其他 800+ 行大文件

按优先级：
1. `edit_patch.py`（1,448 行）→ 按操作类型拆分（增/删/改/审/合）
2. `pipeline_chain.py`（1,418 行）→ 每个生成阶段独立文件
3. `part_family_knowledge.py`（1,374 行）→ 按知识操作拆分
4. `drawing_to_pfd.py`（1,294 行）→ 拆分编排与 step 构建
5. `drawing_ocr_analysis.py`（1,081 行）→ 拆分 OCR 策略与分析逻辑
6. `cli.py`（919 行）→ 命令分到独立模块
7. 其余 800+ 文件

### 3.4 AI 韧性层接入 LLM 调用点

核心变更点在 `pipeline_chain.py`：

```python
# Before
result = llm_adapter.analyze(prompt, model=model)

# After
retry = ExponentialBackoffRetry(max_retries=3)
breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)
result = await retry.execute_with_retry(
    lambda: breaker.call(llm_adapter.analyze, prompt, model=model)
)
```

**验证**: LLM 调用失败时有重试 + 熔断保护，已有单元测试验证行为

### 3.5 Plugin 系统接入主流水线

在 `pipeline_chain.py` 的适当阶段插入插件钩子：
- 绘制分析前：OCR 插件选择
- PFMEA 生成前：知识源插件查询

**验证**: `test_plugins_*.py` 通过

### 3.6 类型加固：TypedDict 替代 `-> Any`

先选最常用的 5 个 dict 类型作为示范：
- `DrawingAnalysisResult`
- `ProcessFlowStep`
- `PFMEARow`
- `ControlPlanRow`
- `QualityGateResult`

```python
class DrawingAnalysisResult(TypedDict):
    process_name: str
    steps: list[ProcessFlowStep]
    materials: list[str]
    # ...
```

**验证**: 替换后对应函数签名不再是 `-> Any`

### 3.7 ADR "Pending" 条目清理

逐条检查 5 个 ADR 的 Pending 条目：
- 已完成的 → 标注 ✅ Done
- 已废弃的 → 标注 ❌ Superseded
- 仍待定的 → 标注 ⏳ Still pending + 后续计划链接

---

## Phase 4：文档重建（1-2 天）

**目标**：让文档追上代码

### 4.1 更新架构文档到 v3.8

| 文档 | 需补充内容 |
|------|-----------|
| `docs/architecture/modules.md` | 新增模块：特殊特性识别、复合图纸、混合分析、编辑补丁 |
| `docs/architecture/data-flow.md` | 补充特殊特性发现/审查/定位流程分支 |
| `docs/architecture/README.md` | 更新 4 层图里的组件清单 |

### 4.2 更新 README

- 版本引用从 "v3.0" 改为 "v3.8"
- 补充 Tauri 桌面应用构建步骤
- 添加新 CLI 命令说明

### 4.3 添加 API 概览文档

创建 `docs/api-overview.md`，列出 `minos_desktop.api` 全部路由：
```
GET    /health          → 健康检查
POST   /auth/login      → 获取 Bearer token
GET    /projects        → 项目列表
POST   /projects        → 创建项目
...
```

### 4.4 根目录清理

- `task_plan.md` → `docs/plans/task_plan.md`
- `progress.md` → `docs/plans/progress.md`
- `findings.md` → `docs/plans/findings.md`

### 4.5 给 docstring 缺口大的模块补 docstring

目标：从 ~21% 提升到 50%+
优先模块：`minos_core/` 中 docstring 覆盖率 < 20% 的模块

---

## Phase 5：测试纵深（2-3 天）

**目标**：补核心缺口，提升薄弱模块覆盖率

### 5.1 config_loader.py 测试（0% → 85%+）

```python
# 测试场景：
- 加载默认 quality_gates.yaml
- 验证所有门定义结构正确
- 门阈值校验
- 配置缺失/格式错误的错误处理
```

### 5.2 导出器测试（0% → 80%+）

- `exporters/apqp_workbook.py`: 验证 XLSX 单元格内容
- `exporters/three_table_workbooks.py`: 输出格式符合 schema

### 5.3 Platform 路由测试（45% → 80%+）

每个 router 补充：
- 成功路径测试
- 错误路径测试（404, 422, 500）
- 认证失败测试

### 5.4 薄弱模块补测

| 模块 | 当前 | 目标 |
|------|------|------|
| `stage/assembler.py` | 69% | 85%+ |
| `pipeline/utilities.py` | 70% | 85%+ |
| `pipeline/hybrid_fusion.py` | 79% | 85%+ |
| `ocr_detection.py` | 58% | 80%+ |
| `desktop/api/routes_runs.py` | 54% | 80%+ |
| `desktop/api/routes_closure.py` | 65% | 80%+ |

### 5.5 清理 `.archived/` 目录

- 确认内容确实过时 → 删除
- 内容有价值的 → 移入 `docs/archive/`

---

## 执行秩序

```
Phase 1 ──────────────────────────────────────
 1.1 修测试失败                              ← 必须先做：否则后续无法验证
 1.2 更新 CHANGELOG                          ← 独立，与 1.3 并行
 1.3 补 git tag                              ← 独立，与 1.2 并行
 1.4 冻结 dataclass                          ← 1.1 通过后再做
 1.5 切换 structlog                          ← 与 1.4 并行
 1.6 安全修复                                ← 与 1.4 并行
 │
Phase 2 ──────────────────────────────────────
 2.1 Dependabot                              ← 独立
 2.2 CI 增强                                 ← 2.1 后
 2.3 pyproject.toml 补齐                     ← 独立
 2.4 工具配置                                ← 独立，与 2.2 并行
 │
Phase 3 ──────────────────────────────────────
 3.1-3.3 拆分大文件                          ← 可并行拆，但同一文件串行
 3.4 AI 韧性接入                             ← 需测试通过
 3.5 Plugin 接入                             ← 需测试通过
 3.6 TypedDict 替换                          ← 可与 3.1-3.3 并行
 3.7 ADR 清理                                ← 独立
 │
Phase 4 ──────────────────────────────────────
 4.1-4.3 文档更新                            ← 可通过子代理并行
 4.4 根目录清理                              ← 独立
 4.5 docstring 补全                          ← 可与 4.1-4.3 并行
 │
Phase 5 ──────────────────────────────────────
 5.1-5.3 补测试                              ← 串行，每个模块独立验证
 5.4 薄弱模块补测                            ← 与 5.1-5.3 并行
 5.5 清理 .archived                          ← 独立
```

---

## 各阶段验收标准

| Phase | PASS 条件 |
|-------|----------|
| **1** | `python -m unittest discover -s tests -v` 全绿 + CHANGELOG 完整 |
| **2** | CI pipeline 全绿 + `ruff check .` 通过 + Dependabot 生效 |
| **3** | 无文件 > 800 行 + LLM 调用走韧性层 + 测试全绿 |
| **4** | 架构文档反映 v3.8 + README 更新 + 根目录无规划文件 |
| **5** | 整体覆盖率 >= 85% + config_loader 和导出器有测试 + `.archived` 清理 |
