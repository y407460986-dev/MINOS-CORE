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

## 第 6 阶段小范围真实项目试运行

第 6 阶段用于让工程/质量人员把少量真实项目资料整理成可追溯、已脱敏的 `input_package` 输入，验证 MINOS-CORE 的 APQP 三表链路草案能力。该阶段不是客户最终 PPAP 自动提交，也不替代工程签核、质量批准或客户门户提交。

标准目录建议从以下模板复制后再填写：

```text
tests\fixtures\real_project_input_package_template\
  input_package.json
  source_index.json
  evidence.json
  review_patch.json
```

- `input_package.json`：登记包 ID、脱敏项目元数据、证据文件路径、复核补丁路径和来源文件清单。
- `source_index.json`：记录图纸、BOM、过程流程、特殊特性、检验规范、作业指导书、客户特殊要求、已有 PFMEA/控制计划（如有）的修订、来源位置、脱敏状态和复核责任。
- `evidence.json`：只写可追溯事实摘录；每条 evidence 必须引用 `source_document_id` 和能定位页/区域/条款/行号的 `source_ref`。
- `review_patch.json`：由工程/质量人员在草案复核后填写确认或修正项；不能用来掩盖缺失证据。模板目录中的该文件只是占位示例，复制后必须替换复核人、时间、证据和确认内容，不能直接当作已确认补丁使用。

填写前检查清单：

- 已确认资料可以用于内部试运行，并完成必要授权和脱敏。
- 已删除客户名称、供应商名称、人员姓名、联系方式、价格、精确产能、客户门户编号和未授权整页图纸/规范。
- 已准备真实资料类型：图纸、BOM、过程流程、特殊特性、检验规范、作业指导书、客户特殊要求；已有 PFMEA/控制计划如有则加入，没有则明确写 `not_available`。
- 每份资料都有修订、来源位置、来源引用和复核责任人/职能。

填写后检查清单：

- 先把 `tests\fixtures\real_project_input_package_template\` 复制到新的项目工作目录，再替换占位内容后运行 pipeline；模板目录只用于 JSON/schema/结构校验，不要求也不应直接 `generate-draft` 通过。
- `input_package.json`、`source_index.json`、`evidence.json`、`review_patch.json` 都是合法 UTF-8 JSON，可打开、无乱码。
- `input_package.json` 的 `evidence_path` 和 `review_patch_path` 指向同目录内实际文件。
- `source_documents[*].source_document_id`、`source_index.json` 的 sources、`evidence.json` 的 `source_document_id` 三者能对上。
- 每条 evidence 的 `source_ref` 足够定位，且不含未脱敏敏感信息。
- 所有 `needs_confirmation: true` 的内容已在 `review_patch.json` 中由人工确认或修正。
- 草案输出仍带人工复核边界；不得把 draft 当作正式提交件。

建议命令链（在项目根目录执行）：

```powershell
python -m json.tool tests\fixtures\real_project_input_package_template\input_package.json > $null
python -m json.tool tests\fixtures\real_project_input_package_template\source_index.json > $null
python -m json.tool tests\fixtures\real_project_input_package_template\evidence.json > $null
python -m json.tool tests\fixtures\real_project_input_package_template\review_patch.json > $null
# 模板目录到此为止只做 JSON/schema/结构校验；不要直接对模板目录运行 generate-draft。
# 复制模板、替换所有占位内容并完成授权脱敏后，再在新项目工作目录执行：
python -m minos_core.cli generate-draft --input path\to\filled_real_project_input_package --output out\real_project_draft_result.json --manifest-output out\real_project_draft_manifest.json
python -m minos_core.cli review-template --draft-result out\real_project_draft_result.json --output out\review_patch_template.json
python -m minos_core.cli export-draft --input out\real_project_draft_result.json --output out\real_project_draft.xlsx --manifest-output out\real_project_draft_export_manifest.json
python -m minos_core.cli apply-review --draft-result out\real_project_draft_result.json --review-patch path\to\filled_real_project_input_package\review_patch.json --output out\real_project_review_result.json --manifest-output out\real_project_review_manifest.json
python -m minos_core.cli export --input out\real_project_review_result.json --output out\real_project_final.xlsx --manifest-output out\real_project_final_manifest.json
```

`draft` / `final` 边界：`generate-draft` 和 `export-draft` 只生成内部工程复核草案；`apply-review` 后的 `export` 只表示已应用人工复核并通过 MINOS-CORE 内部质量门，仍不是客户最终 PPAP 自动提交件。

第 6 阶段暂不接 OCR、真实 AI、客户复杂模板、客户门户、审批流或完整 PPAP 自动提交；这些能力应留在核心模块外的适配层或后续阶段单独设计。

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
- `minos_platform/` 是独立平台层，不向 `minos_core` 引入任何依赖。

## 平台后端 MVP（可选）

`minos_platform` 是建立在 `minos_core` 上的 PPAP 项目管理层，提供 FastAPI REST API 与 SQLite 持久化。本层为可选依赖，需单独安装：

```powershell
pip install -e ".[platform]"
python -m minos_platform
```

启动后访问 `http://localhost:8000/docs`（自动生成的 Swagger 文档）。

### 平台 API 端点

| 端点 | 功能 |
|------|------|
| `POST /api/projects` | 创建 PPAP 项目 |
| `GET /api/projects` | 列出所有项目 |
| `GET /api/projects/{id}` | 查看项目详情和最新运行 |
| `POST /api/projects/{id}/input-packages` | 登记已脱敏 input_package（复制到 artifact 区，验证 SHA256） |
| `POST /api/projects/{id}/draft-runs` | 调用 generate_draft 生成草案 |
| `POST /api/projects/{id}/review-template` | 生成人工填写 review template |
| `POST /api/projects/{id}/review-patches` | 提交人工填写的 review patch（复制到 artifact 区，验证 SHA256） |
| `POST /api/projects/{id}/apply-review` | 应用 review patch，生成 review result |
| `POST /api/projects/{id}/exports` | 导出 draft/final workbook |
| `GET /api/artifacts/{id}` | 下载产物文件（只能下载已登记的 artifact） |
| `POST /api/projects/{id}/ppap-packages` | 创建 PPAP Package（自动初始化 18 项要素） |
| `GET /api/projects/{id}/ppap-packages` | 列出项目的所有 Package |
| `GET /api/ppap-packages/{id}` | 获取 Package 详情 |
| `PATCH /api/ppap-packages/{id}/elements/{eid}` | 更新要素状态 |
| `POST /api/ppap-packages/{id}/elements/{eid}/artifacts` | 关联 Artifact 到要素 |
| `POST /api/ppap-packages/{id}/refresh-from-project` | 自动关联项目 Artifact 到 PFD/PFMEA/Control Plan |

### 项目状态流转

```
created → input_registered → draft_ready → review_template_ready
→ review_patch_submitted → review_applied → final_export_ready / blocked
```

### 核心设计原则

- **文件安全**：所有用户提交的 input package 和 review patch 都会被复制到 `out/platform/artifacts/` 下的平台管理区，原始路径不用于后续运行。
- **SHA256 校验**：所有复制的文件都会计算真实 SHA256 与客户端提交值比对，不匹配返回 422。
- **Artifact 可追溯**：每个产物（draft result、review template、review result、export）都有真实 SHA256 记录在 `ppap_artifacts` 表中。
- **最终导出隔离**：final export 只能从 `review_applied` 状态执行，必须使用 apply-review 生成的 review result（含 patched_chain），不能使用 draft result。
- **草案导出不改变状态**：draft export 成功后只记录 `draft_export_ready`，不改变项目状态。

### 明确非目标

- 本层不提供网页 UI、权限模型、多租户、客户门户。
- 不接真实 OCR/AI、客户复杂模板、审批流或自动 PPAP 提交。
- 不向 `minos_core` 引入数据库、异步框架或平台状态。

### 数据存储

- SQLite 数据库：`out/platform/minos_platform.sqlite3`（含 `ppap_schema_version` 表记录平台 schema 版本）
- 产物文件：`out/platform/artifacts/{project_id}/inputs/`（input packages、review patches）
- 产物文件：`out/platform/artifacts/{project_id}/`（draft results、review results、exports）

## PPAP Package 与要素状态管理（B阶段）

`minos_platform` 支持在项目下创建 PPAP Package 并管理 18 项 PPAP 提交要素的完成状态。

### PPAP Package 概念

每个项目可创建一个或多个 PPAP Package，每个 Package 记录：
- 提交等级（`submission_level`）
- 当前状态（`draft` / `ready_for_submission` / `submitted` / `approved` / `rejected`）
- 18 项要素的完成状态

### 18 项 PPAP 要素

创建 Package 时自动初始化以下 18 项要素：

| # | 要素 Key | 显示名称 |
|---|----------|----------|
| 1 | `design_records` | Design Records |
| 2 | `engineering_change_documents` | Authorized Engineering Change Documents |
| 3 | `engineering_approval` | Customer Engineering Approval |
| 4 | `dfmea` | DFMEA |
| 5 | `process_flow_diagram` | Process Flow Diagram |
| 6 | `pfmea` | PFMEA |
| 7 | `control_plan` | Control Plan |
| 8 | `msa_studies` | MSA Studies |
| 9 | `dimensional_results` | Dimensional Results |
| 10 | `material_test_results` | Material / Performance Test Results |
| 11 | `initial_process_studies` | Initial Process Studies |
| 12 | `laboratory_documentation` | Qualified Laboratory Documentation |
| 13 | `appearance_approval` | Appearance Approval Report |
| 14 | `sample_product` | Sample Product |
| 15 | `master_sample` | Master Sample |
| 16 | `checking_aids` | Checking Aids |
| 17 | `customer_specific_requirements` | Customer-Specific Requirements |
| 18 | `part_submission_warrant` | Part Submission Warrant |

### 要素状态

每项要素支持以下状态：

- `not_required`：客户不需要此要素
- `required`：客户需要，但尚未完成
- `missing`：未提供或未关联
- `draft_ready`：已有草案/产物
- `needs_review`：需要人工复核
- `approved`：已批准
- `blocked`：被阻断

### PPAP Package API

| 端点 | 功能 |
|------|------|
| `POST /api/projects/{id}/ppap-packages` | 创建 PPAP Package（自动初始化 18 项要素） |
| `GET /api/projects/{id}/ppap-packages` | 列出项目的所有 Package |
| `GET /api/ppap-packages/{id}` | 获取 Package 详情（包含要素清单、状态统计） |
| `GET /api/ppap-packages/{id}/elements` | 列出所有要素 |
| `GET /api/ppap-packages/{id}/elements/{eid}` | 获取单个要素详情 |
| `PATCH /api/ppap-packages/{id}/elements/{eid}` | 更新要素状态/备注 |
| `POST /api/ppap-packages/{id}/elements/{eid}/artifacts` | 将平台 Artifact 关联到要素 |
| `POST /api/ppap-packages/{id}/refresh-from-project` | 自动从项目已有 Artifact 填充 PFD/PFMEA/Control Plan |

### ready_for_submission 规则

Package 的 `ready_for_submission` 为 `True` 当且仅当：
1. 至少有一项要素被标记为 `approved`
2. 所有标记为 `required` 的要素都已 `approved`

### 自动关联 Artifact

`refresh-from-project` 会查找项目已有 runs 中的 `pfmea_xlsx` 和 `final_xlsx` 类型的 artifact，自动关联到 `process_flow_diagram`、`pfmea`、`control_plan` 三项要素，并将要素状态从 `missing` 更新为 `draft_ready`。

### 跨项目 Artifact 防护

关联 Artifact 时会验证 Artifact 所属 run 的 `project_id` 必须与 Package 所在项目的 `project_id` 一致；跨项目关联返回 409。

### 明确非目标

- 本阶段不做前端 UI、审批流、签核流。
- 不做完整的 PPAP 提交客户门户。
- Package 标记为 `submitted` / `approved` 不代表客户正式批准，只是内部状态跟踪。
