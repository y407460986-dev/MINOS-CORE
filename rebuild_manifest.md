# MINOS-CORE 重建交付清单

## 第十二阶段新增
本阶段新增 AI analyze 增强入口。AI 只参与 `analysis_bundle` 候选增强，不生成 PFD/PFMEA/控制计划，不接真实外部服务。

更新文件：
- `README.md`
- `minos_core/analyze.py`
- `minos_core/quality_gates.py`
- `minos_core/__init__.py`
- `tests/test_analyze_stage.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `project_flow.mmd`
- `rebuild_manifest.md`

第十二阶段测试契约：
- keyword-only analyze 路径不退化。
- `analyze_evidence_bundle_with_ai` 输出合法 `analysis_bundle`。
- AI 结果必须进入 `ai_inferred_items`，并标记 `needs_confirmation`。
- AI 输出非法 JSON、未知块、缺失 `source_ref`、引用不存在 evidence 时直接失败。
- AI process clue 不能单独满足 analyze gate 的有效 Pxx route clue。
- validate/export 旧链路不退化。

第十二阶段验收命令：
/// 1. `python -m unittest tests.test_analyze_stage -v`
/// 2. `python -m unittest discover -s tests -v`
/// 3. `python -m minos_core.cli validate --input tests\fixtures\apqp_chain`
/// 4. `python -m minos_core.cli audit --input tests\fixtures\apqp_chain`

## 第十一阶段新增
本阶段接通 `brainstorm_failure_modes -> generate_pfmea -> generate_control_plan`，继续保持当前平铺结构，不做目录迁移，不接真实 LLM/OCR 服务。

新增文件：
- `README.md`
- `minos_core/generate_pfmea.py`
- `minos_core/generate_control_plan.py`
- `tests/test_generate_pfmea_stage.py`
- `tests/test_generate_control_plan_stage.py`

更新文件：
- `minos_core/stage.py`
- `minos_core/quality_gates.py`
- `minos_core/__init__.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `project_flow.mmd`
- `rebuild_manifest.md`

第十一阶段测试契约：
- `run_stage(..., stage="generate_pfmea")` 必须返回 `pfmea` bundle。
- `run_stage(..., stage="generate_control_plan")` 必须返回 `control_plan` bundle。
- PFMEA row 和控制计划 row 必须保留 `evidence_refs`。
- 缺失 evidence ref、AI-only evidence、缺本阶段关键字段必须 blocked。
- 上游 pending 字段只作为待复核信息保留，不阻断下游草案生成。
- `brainstorm_failure_modes` 预检不能提前吞掉“某工序无候选项”的本阶段错误。

第十一阶段验收命令：
/// 1. `python -m unittest discover -s tests -v`
/// 2. `python -m minos_core.cli validate --input tests\fixtures\apqp_chain`
/// 3. `python -m minos_core.cli audit --input tests\fixtures\apqp_chain`
/// 4. `python -m minos_core.cli export --input tests\fixtures\apqp_chain --output <temp>\minos-core-smoke-apqp.xlsx`

## 第二阶段新增
本阶段新增真实样本迁移验收，不实现 adapter，只用测试约束 adapter 输出必须进入 MINOS-CORE 标准链路。

新增文件：
- `tests/test_legacy_excel_adapter.py`

更新文档：
- `task_plan.md`
- `progress.md`
- `findings.md`
- `rebuild_manifest.md`

真实源路径：
- `C:\Users\fgtan\Desktop\知识库种子\门铰链\JLH01000300-门铰链.xlsx`
- `C:\Users\fgtan\Desktop\知识库种子\冲压件\1004258-冲压件.xlsx`
- `C:\Users\fgtan\Desktop\知识库种子\限位器\XWQ01000100-限位器.xlsx`

新增测试契约：
- `convert_legacy_workbook(workbook_path, fixture_dir)` 将真实 workbook 转为标准 fixture 目录。
- fixture 目录必须包含 `process_flow.json`、`pfmea.json`、`control_plan.json`。
- 每套 fixture 必须通过 `load_apqp_chain` 和 `validate_chain`。
- 每套 fixture 必须能用 `export_fixture` 导出中文 APQP workbook。
- workbook 必须包含固定 5 张 sheet：摘要、过程流程图、PFMEA、控制计划、三表追溯矩阵。
- 所有测试输出写入 `tempfile`，不写固定 `output/`。

## 本轮范围
本轮只交付 fixture、测试和文档资产，供并行的核心代码与 exporter worker 对齐。未写入 `minos_core` 实现代码，未删除文件。

## Fixture
- `tests/fixtures/apqp_chain/process_flow.json`
- `tests/fixtures/apqp_chain/pfmea.json`
- `tests/fixtures/apqp_chain/control_plan.json`

fixture 表达一条最小但完整的 APQP 链：
- 3 个过程流程步骤。
- 4 条 PFMEA 行。
- 4 条控制计划行。
- PFD、PFMEA、CP 通过 `process_step_id`、`pfmea_id`、`control_plan_id` 追溯。

## Sample Configs
- `configs/samples/door_hinge.json`
- `configs/samples/limiter.json`
- `configs/samples/stamping.json`

这些文件现在只保留元数据：样本 id、显示名、产品族、APQP 阶段、语言、默认交付文件名和说明。不再保留本地路径、seed xlsx 路径、工艺关键字、特殊特性或规格值。

## Tests
- `tests/test_apqp_rebuild_contract.py`
- `tests/test_legacy_excel_adapter.py`

覆盖内容：
- domain loader 读取完整 APQP fixture。
- validation 接受完整链路。
- validation 拒绝 mandatory PFMEA 缺少 CP 覆盖。
- xlsx writer sheet 名清洗、截断、去重。
- xlsx zip 结构完整性。
- APQP workbook 固定 5 张 sheet。
- CLI `list` / `validate` / `export`。
- 三个真实 legacy Excel workbook 转标准 fixture。
- 真实转换结果通过 validation 后导出 5 sheet workbook。

## Docs
- `task_plan.md`
- `progress.md`
- `findings.md`
- `project_flow.mmd`
- `rebuild_manifest.md`

## 验收命令
/// 1. JSON 解析检查：确认 fixture 和 sample configs 没有乱码或语法错误。
/// 2. unittest discovery：确认测试文件能被发现。
/// 3. 完整测试：核心代码和 exporter 就绪后运行 `python -m unittest discover -s tests -v`。
/// 4. adapter 就绪后运行 `python -m unittest tests.test_legacy_excel_adapter -v`。

## 注意
如果核心代码尚未提供 `minos_core.domain`、`minos_core.validation`、`minos_core.exporters`、`minos_core.cli`，完整测试会失败。这不是 fixture/测试任务的绕行点，而是重建契约尚未被实现的明确信号。
如果 legacy Excel adapter 尚未提供 `convert_legacy_workbook`，第二阶段真实样本测试会失败；这代表 adapter 契约未完成，不应通过测试绕行。

## 第三阶段新增
本阶段新增质量审计验收，不实现 audit/CLI，只用测试约束 audit 输出必须区分“结构闭环”和“内容可靠”。

新增文件：
- `tests/test_quality_audit.py`

更新文档：
- `task_plan.md`
- `progress.md`
- `findings.md`
- `rebuild_manifest.md`

第三阶段测试契约：
- `audit_chain(chain)` 能对四套 fixture 运行：
  - `tests/fixtures/apqp_chain`
  - `tests/fixtures/door_hinge`
  - `tests/fixtures/stamping`
  - `tests/fixtures/limiter`
- audit report 必须包含 `counts`。
- audit report 必须包含 `manual_review_items`。
- 最小弱链接样本仍应通过 `validate_chain`。
- 同一个最小弱链接样本必须被 audit 标记为 mechanical / weak / manual review 风险。

## 第三阶段文档结论
第三阶段是质量审计，不是硬校验。它的目的不是替代 validation，而是在结构闭环之后继续判断内容是否可靠：

- `validate_chain`：判断 APQP 链路是否完整、必控项是否覆盖。
- `audit_chain`：判断控制内容是否薄弱、机械逻辑是否可疑、哪些项需要人工复核。

## 第三阶段验收命令
/// 1. audit worker 完成后运行：`python -m unittest tests.test_quality_audit -v`。
/// 2. 完整回归时运行：`python -m unittest discover -s tests -v`。
/// 3. 若 `tests.test_quality_audit` 因 `minos_core.audit` 缺失失败，代表 audit worker 尚未完成，不应在测试侧绕行。

## 第三阶段范围说明
本轮没有写入 `minos_core/audit.py`，没有修改 CLI，也没有更新 `project_flow.mmd`。`project_flow.mmd` 未更新的原因是用户本轮明确限定写入范围，且该文件不在允许列表内。

## 第四阶段新增
本阶段只针对 limiter 的 legacy PFMEA/CP 链接质量做收口，并补上审计回归门槛。

更新文件：
- `minos_core/adapters/legacy_excel.py`
- `minos_core/audit.py`
- `tests/fixtures/limiter/pfmea.json`
- `tests/fixtures/limiter/control_plan.json`
- `tests/test_quality_audit.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `project_flow.mmd`
- `rebuild_manifest.md`

第四阶段测试契约：
- `tests/test_quality_audit.py` 中 limiter 必须满足：
  - `mechanical_links <= 3`
  - `weak_links <= 10`
  - `manual_review_items <= 18`

第四阶段结果：
- `mechanical_links`：10 -> 0。
- `weak_links`：22 -> 1。
- `manual_review_items`：35 -> 4。

第四阶段验收命令：
/// 1. `python -m minos_core.cli validate --input tests\fixtures\limiter`
/// 2. `python -m minos_core.cli audit --input tests\fixtures\limiter`
/// 3. `python -m unittest discover -s tests -v`

## 第五阶段新增
本阶段将 MINOS-CORE 的架构边界落为四层：Domain Core、Pipeline、Adapters、Quality Gates。

新增文件：
- `minos_core/adapters/fixture_json.py`
- `minos_core/quality_matching.py`
- `minos_core/quality_gates.py`

更新文件：
- `minos_core/domain.py`
- `minos_core/pipeline.py`
- `minos_core/cli.py`
- `minos_core/audit.py`
- `minos_core/adapters/legacy_excel.py`
- `minos_core/adapters/__init__.py`
- `minos_core/__init__.py`
- `tests/test_apqp_rebuild_contract.py`
- `tests/test_quality_audit.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `project_flow.mmd`
- `rebuild_manifest.md`

第五阶段测试契约：
- Domain Core 暴露 `Product`、`Drawing`、`Characteristic`、`ProcessStep`、`FailureMode`、`ControlItem`、`Evidence`、`TraceLink`。
- Domain Core 不拥有 `_read_json` 文件 IO。
- `minos_core.adapters.fixture_json` 负责标准 fixture 文件读取。
- `pipeline.PIPELINE_STAGES` 固定为八阶段流程。
- `quality_gates.evaluate_stage_gate` 返回证据、待确认字段、AI 推断、是否可继续、是否可导出的阶段门结果。

## 第六阶段新增
本阶段新增阶段流转、证据引用、导出质量门 sheet，以及 OCR/LLM adapter 占位接口。

新增文件：
- `minos_core/stage.py`
- `minos_core/adapters/ocr.py`
- `minos_core/adapters/llm.py`
- `tests/test_stage_result.py`
- `tests/test_ocr_llm_adapters.py`

更新文件：
- `minos_core/domain.py`
- `minos_core/exporters/apqp_workbook.py`
- `minos_core/__init__.py`
- `tests/test_apqp_rebuild_contract.py`
- `tests/test_legacy_excel_adapter.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `rebuild_manifest.md`

第六阶段测试契约：
- `StageResult` 必须暴露 `stage/status/output/evidence/pending_fields/ai_inferred_items/quality_gate`。
- `ProcessStep`、`FailureMode`、`ControlItem`、`TraceLink` 必须保留 `evidence_refs`。
- APQP workbook 必须包含 7 张 sheet：`摘要`、`质量门状态`、`过程流程图`、`PFMEA`、`控制计划`、`三表追溯矩阵`、`人工复核清单`。
- OCR/LLM adapter 只允许 fake 和 not-configured 占位，不允许接真实外部服务。

## 第七阶段新增
本阶段新增 Evidence 文件化和证据覆盖质量门。

新增文件：
- `tests/fixtures/apqp_chain/evidence.json`

更新文件：
- `minos_core/adapters/fixture_json.py`
- `minos_core/quality_gates.py`
- `minos_core/exporters/apqp_workbook.py`
- `tests/fixtures/apqp_chain/process_flow.json`
- `tests/fixtures/apqp_chain/pfmea.json`
- `tests/fixtures/apqp_chain/control_plan.json`
- `tests/test_apqp_rebuild_contract.py`
- `tests/test_quality_audit.py`
- `tests/test_stage_result.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `project_flow.mmd`
- `rebuild_manifest.md`

第七阶段测试契约：
- `fixture_json` 必须能读取可选 `evidence.json`。
- 没有 `evidence.json` 的旧 fixture 目录必须继续可读。
- 有 evidence 池时，缺失 `evidence_refs`、引用不存在的 evidence、引用 AI 推断证据或待确认证据都不能通过阶段质量门。
- Excel `质量门状态` sheet 必须显示证据覆盖率、缺失证据引用数和待确认证据数。

## 第八阶段新增
本阶段新增 ingest 阶段真实入口，把输入资料统一转成 Evidence bundle。

新增文件：
- `minos_core/ingest.py`
- `tests/test_ingest_stage.py`

更新文件：
- `minos_core/stage.py`
- `minos_core/quality_gates.py`
- `minos_core/__init__.py`
- `tests/test_stage_result.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `project_flow.mmd`
- `rebuild_manifest.md`

第八阶段测试契约：
- `run_stage(..., stage="ingest")` 必须返回 `evidence_bundle`。
- manual JSON、OCR text、FakeOCRAdapter 和 fixture evidence 都能进入 `StageResult.evidence`。
- ingest 阶段 `can_continue=True` 表示可进入 analyze，且永远不允许用户导出。
- 空 evidence 和全部 AI 推断 evidence 必须阻断 ingest。
- validate/export 仍保持原来的 APQP 三表 evidence_refs 覆盖质量门。

## 第九阶段新增
本阶段新增 analyze 阶段，把 Evidence bundle 转成结构化分析结果。

新增文件：
- `minos_core/analyze.py`
- `tests/test_analyze_stage.py`

更新文件：
- `minos_core/stage.py`
- `minos_core/quality_gates.py`
- `minos_core/__init__.py`
- `tests/test_stage_result.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `project_flow.mmd`
- `rebuild_manifest.md`

第九阶段测试契约：
- `run_stage(..., stage="analyze")` 必须返回 `analysis_bundle`。
- analysis bundle 必须包含 `evidence`、`drawings`、`characteristics`、`process_clues`、`pending_fields`、`ai_inferred_items`。
- `tests/fixtures/apqp_chain` 至少能抽出 1 个 drawing、2 个 characteristic、2 个 process clue。
- manual JSON 和 OCR text 可以直接进入 analyze。
- analyze 阶段不允许用户导出，但可在质量门通过时进入 `generate_pfd`。
- validate/export 旧链路不退化。

## 第十阶段新增
本阶段新增 `generate_pfd` 阶段，把 analysis bundle 转成正式 process flow。

新增文件：
- `minos_core/generate_pfd.py`
- `tests/test_generate_pfd_stage.py`

更新文件：
- `minos_core/stage.py`
- `minos_core/quality_gates.py`
- `minos_core/__init__.py`
- `tests/test_stage_result.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `project_flow.mmd`
- `rebuild_manifest.md`

第十阶段测试契约：
- `run_stage(..., stage="generate_pfd")` 必须返回 `process_flow`。
- fixture evidence 必须能生成 P10/P20/P30 和 P10 -> P20、P20 -> P30。
- 每个 generated step 和 link 必须包含 `evidence_refs`。
- 无明确 `process_step_id` 的 process clue 必须进入 pending，不得猜编号。
- generate_pfd 输出不得包含 PFMEA/CP 下游文档。
- AI-only route evidence 必须阻断；OCR 待确认证据只提示，不阻断 PFD 生成。
- validate/export 旧链路不退化。

## 第十阶段下阶段前修复新增
进入第十一阶段前补强 PFD gate 与 `brainstorm_failure_modes` 衔接。

更新文件：
- `minos_core/quality_gates.py`
- `minos_core/stage.py`
- `minos_core/__init__.py`
- `tests/test_generate_pfd_stage.py`
- `progress.md`
- `findings.md`
- `rebuild_manifest.md`
- `project_flow.mmd`

新增测试契约：
- step `evidence_refs` 引用不存在 evidence 时必须 blocked。
- link 缺少 `evidence_refs` 或引用不存在 evidence 时必须 blocked。
- AI-only referenced evidence 必须 blocked，且 `evidence_sufficient=False`。
- `process_function` / `special_characteristics` 为空只进入 review，不阻断。
- `run_stage(..., stage="brainstorm_failure_modes")` 必须接受 `process_flow` 并复用 PFD gate，不能误走完整 APQPChain 校验。

## 第十阶段二次前向筛查修复新增
进入第十一阶段前再次补强 analyze/PFD/brainstorm gate。

更新文件：
- `minos_core/analyze.py`
- `minos_core/quality_gates.py`
- `tests/test_analyze_stage.py`
- `tests/test_generate_pfd_stage.py`
- `progress.md`
- `findings.md`
- `rebuild_manifest.md`

新增测试契约：
- analyze 至少需要 2 个合法 `Pxx` route clue 才可进入 `generate_pfd`。
- phrase-only route clue 不计入合法 Pxx route clue。
- 同一 evidence 已被 Pxx 识别的 operation 不再重复输出 phrase-only clue。
- `needs_confirmation` 不得进入 `ai_inferred_items`。
- `process_clues.source_ref` 引用不存在 evidence 时 analyze gate 必须 blocked。
- PFD/brainstorm gate 必须保留字符串形式 `pending_fields`。
- PFD/brainstorm gate 必须检查 `link_type`。
- brainstorm preflight report 必须使用 `stage_mode=brainstorm_failure_modes_preflight`。
