# MINOS-CORE

MINOS-CORE 是一个证据驱动的 APQP 三表链路核心引擎，用于把可追溯证据整理为 PFD、PFMEA、控制计划之间的结构化链路；它不是完整 PPAP 平台。

当前主线是：

```text
ingest -> analyze -> generate_pfd -> brainstorm_failure_modes -> generate_pfmea -> generate_control_plan -> validate -> audit -> export
```

## 当前已实现范围

当前仓库聚焦 APQP 三表链路的核心编排、规则生成、质量门校验、审计与导出，已覆盖以下阶段：

- `ingest`：读取并标准化输入证据包。
- `analyze`：基于规则分析证据，形成可追溯的分析结果。
- `generate_pfd`：从分析结果生成过程流程图所需的结构化过程步骤。
- `brainstorm_failure_modes`：围绕过程步骤和证据线索生成失效模式候选。
- `generate_pfmea`：根据过程步骤、失效模式候选和证据链生成 PFMEA 结构。
- `generate_control_plan`：根据 PFMEA 和过程步骤生成控制计划结构。
- `validate`：执行阶段质量门，判断链路是否满足继续流转或需要人工复核。
- `audit`：输出证据覆盖、链路完整性、人工复核点等审计信息。
- `export`：将核心结构导出为交付格式。

## 当前交付状态

- APQP workbook 当前固定导出 7 张 sheet：`摘要`、`质量门状态`、`过程流程图`、`PFMEA`、`控制计划`、`三表追溯矩阵`、`人工复核清单`。
- 测试数量不在文档中固化；当前通过情况以本地 `python -m unittest discover -s tests -v` 或任务记录中的最新检查结果为准。
- `generate-draft` / `run-pipeline` 入口输出草案 JSON，不等同正式导出。

## 工程化基础设施

- 项目提供最小 `pyproject.toml`，可被 Python 打包工具识别为 `minos-core` 包，并注册 `minos-core` CLI 入口。
- 运行时第三方依赖保持为空；真实 LLM/OCR SDK 不进入 core。
- `.gitignore` 已覆盖 Python 缓存、本地虚拟环境、测试缓存、常见构建/输出目录以及 `.claude/settings.local.json`，避免提交本地 Claude 配置。

## 明确非目标

MINOS-CORE 当前不承诺、也不内置以下能力：

- 不是真实 AI/OCR 平台；当前只保留适配器边界和占位契约。
- 不提供数据库、长期存储、权限模型或多租户能力。
- 不提供 UI、审批流、签核流、消息通知或企业门户。
- 不负责 ERP、MES、PLM、QMS 等企业系统集成。
- 不是完整 PPAP 平台，不覆盖所有 PPAP 表单、客户门户提交、正式批准闭环。
- 不在核心模块中直接调用真实 LLM/OCR SDK、网络服务或写入 API key。

## 阶段输入输出简表

| 阶段 | 主要输入 | 主要输出 |
| --- | --- | --- |
| `ingest` | fixture JSON、`input_package` v1、legacy Excel、OCR/LLM 占位输入等外部证据 | 标准化 evidence bundle |
| `analyze` | evidence bundle、`keyword_rules` | `analysis_bundle`，包含证据线索、规则命中和复核标记 |
| `generate_pfd` | `analysis_bundle` | 过程步骤、过程顺序、步骤级证据引用 |
| `brainstorm_failure_modes` | 过程步骤、分析线索、证据引用 | 失效模式候选及其证据来源 |
| `generate_pfmea` | 过程步骤、失效模式候选、证据链 | PFMEA 结构化条目 |
| `generate_control_plan` | PFMEA、过程步骤、证据链 | 控制计划结构化条目 |
| `validate` | PFD、PFMEA、控制计划、证据链 | 质量门结果、阻断项、人工复核项 |
| `audit` | 全链路产物、质量门结果 | 审计摘要、覆盖情况、可追溯性检查结果 |
| `export` | 已验证或带复核标记的链路产物 | Excel 等交付文件 |

## input_package v1 最小契约

`input_package` v1 用于把外部证据包交给 `ingest`，最小必填字段为：`document_type: "input_package"`、`schema_version: "minos-core.input_package.v1"`、`package_id`、`evidence_path`、`metadata`。`review_patch_path` 可选；`source_documents` 可选，用于记录来源文件元数据。当前 fixture adapter 会先按该 schema 校验，再读取 `evidence_path` 和可选的 `review_patch_path`，最终标准化为 `evidence_bundle`。

## 质量门字段语义

质量门只负责表达“当前链路是否足够继续流转、是否需要人工介入”，不替代工程判断或客户批准。

- `passed`：当前质量门是否通过。为 `false` 时，表示存在阻断问题，不应无提示地继续生成下游交付。
- `blocking_issues`：必须先解决的问题，例如关键过程步骤缺失、PFMEA 与控制计划链路断裂、证据引用缺失等。
- `warnings`：不一定阻断流转，但会影响可信度或完整性的风险提示。
- `needs_human_review`：需要人工复核的内容，常见于证据不足、AI 推断、规则无法确认或工程语义不确定。
- `evidence_refs`：质量门判断所依赖的证据引用，用于追溯判断来源。
- `stage`：质量门对应的阶段，便于定位问题发生在 PFD、PFMEA、控制计划或整体链路。

## AI 接入边界

- 默认 `analyze` 仍走 `keyword_rules`，不需要真实 LLM 配置。
- `analyze_evidence_bundle_with_ai(...)` 只增强 `analysis_bundle`，不直接生成 PFD、PFMEA 或控制计划。
- AI 输出必须引用已有 evidence，并标记 `ai_inferred` 和 `needs_confirmation`。
- AI 线索不能单独满足下游质量门，必须经过规则证据、质量门和人工复核。
- 当前只使用 LLM adapter / FakeLLM 契约，不在 core 中写入真实 API key、SDK 或网络调用。
- 真实 AI/OCR 如果接入，应位于 `adapters/` 边界之外或通过明确 adapter 注入，核心生成器仍保持可测试、可复现、可审计。

## 运行

```powershell
python -m minos_core.cli list --samples-dir configs\samples
python -m minos_core.cli validate --input tests\fixtures\apqp_chain
python -m minos_core.cli audit --input tests\fixtures\apqp_chain
python -m minos_core.cli export --input tests\fixtures\apqp_chain --output out.xlsx
```

## Demo input package CLI 端到端流程

以下命令把内置 demo input package 通过标准 CLI 链路跑成草案、草案导出、人工复核结果、正式导出和 manifest：

```powershell
mkdir out
python -m minos_core.cli generate-draft --input tests\fixtures\demo_input_package --output out\demo_draft_result.json --manifest-output out\demo_draft_manifest.json
python -m minos_core.cli export-draft --input out\demo_draft_result.json --output out\demo_draft.xlsx --manifest-output out\demo_draft_export_manifest.json
python -m minos_core.cli apply-review --draft-result out\demo_draft_result.json --review-patch tests\fixtures\demo_input_package\review_patch.json --output out\demo_review_result.json --manifest-output out\demo_review_manifest.json
python -m minos_core.cli export --input out\demo_review_result.json --output out\demo_final.xlsx --manifest-output out\demo_final_manifest.json
```

- `demo_draft.xlsx` 是带 `DRAFT_ONLY` 标记的工程复核草案，不是正式提交件。
- `demo_final.xlsx` 只从 `apply-review` 后通过质量门的 review result 导出。
- 每一步的 `--manifest-output` 会生成可审计的 run manifest。

## 测试

```powershell
python -m unittest discover -s tests -v
```

## 模块边界

- `domain.py` 只放业务对象，不读文件、不调模型、不写 Excel。
- `stage.py` 只编排阶段，不承载生成规则。
- `quality_gates.py` 只判断阶段能否继续、哪些内容需要人工复核。
- `adapters/` 负责外部输入边界，例如 fixture JSON、legacy Excel、OCR/LLM 占位。
- `exporters/` 负责交付格式。
- `generate_pfmea.py` 和 `generate_control_plan.py` 是薄规则生成器，不接 LLM、不做文件 IO。
