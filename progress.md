# MINOS-CORE 重建进度

## 当前状态
第二阶段已开始：真实样本迁移的测试与文档已按允许范围更新。adapter 实现由另一个 worker 负责，本轮只约束公开契约并保留验收入口。

## 已完成
- 已确认当前工作树存在并行改动风险，未回退、未覆盖允许范围外文件。
- 已新增 `tests/test_legacy_excel_adapter.py`，覆盖三个真实 Excel 源：
  - 门铰链：`JLH01000300-门铰链.xlsx`
  - 冲压件：`1004258-冲压件.xlsx`
  - 限位器：`XWQ01000100-限位器.xlsx`
- 测试会对每个样本执行：`convert_legacy_workbook` 转 tempfile fixture、JSON 解析、`load_apqp_chain`、`validate_chain`、`export_fixture`、xlsx zip 结构检查和 5 sheet 顺序检查。
- 已更新 `task_plan.md`，明确第二阶段目标：真实样本转标准 fixture，OCR/LLM 仍保持 adapter 外挂。
- 已更新 `findings.md`，补充真实样本 workbook 迁移风险和验收重点。
- 已更新 `rebuild_manifest.md`，记录新增测试和第二阶段文档变更。

## 当前待验证
/// 1. adapter worker 暴露 `minos_core.adapters.legacy_excel.convert_legacy_workbook` 或 `minos_core.adapters.legacy.convert_legacy_workbook`。
/// 2. 运行 `python -m unittest tests.test_legacy_excel_adapter -v`。
/// 3. 如果测试失败，按原始错误判断是源文件缺失、adapter 接口缺失、转换字段缺失、validation 不通过还是 xlsx 打开性问题。
/// 4. 用 git status 审核修改范围是否仅限本轮允许的 5 个文件。

## 风险
- 本轮没有写 adapter，因此在 adapter worker 完成前，真实样本测试会因 `convert_legacy_workbook` 缺失而失败。
- 三个真实 workbook 都存在大量合并单元格和向下继承语义，adapter 若只读显式单元格值，可能丢失工序编号、PFMEA 行归属或控制计划归属。
- validation 是硬门槛：mandatory/high-risk PFMEA 必须进入控制计划，否则不能把转换结果视为成功。

## 下一步
- 等 adapter worker 完成后，优先跑新增真实样本测试。
- 若三个样本中某个 validation 不通过，先修 adapter 的映射和继承规则，不把失败隐藏在 core 或 exporter 里。
- 真实样本通过后，再考虑把转换出的 fixture 固化为回归样本；当前测试仍保持 tempfile 输出。

## 第三阶段当前状态
第三阶段已开始：质量审计的测试与文档已按允许范围更新。audit/CLI 实现由另一个 worker 负责，本轮只约束公开契约并保留验收入口。

## 第三阶段已完成
- 已新增 `tests/test_quality_audit.py`。
- 测试覆盖四套标准 fixture：
  - `tests/fixtures/apqp_chain`
  - `tests/fixtures/door_hinge`
  - `tests/fixtures/stamping`
  - `tests/fixtures/limiter`
- 测试要求 `audit_chain` 对每套 fixture 能运行，并且报告包含 `counts` 与 `manual_review_items`。
- 已构造最小弱链接样本：PFD/PFMEA/CP 结构仍闭环，但控制计划规格、测量方法、抽样频次和反应计划明显偏弱。
- 已验证测试意图：弱链接样本应通过 `validate_chain`，同时由 `audit_chain` 识别 mechanical / weak / manual review 风险。
- 已更新 `task_plan.md`，明确第三阶段是质量审计，不是硬校验。
- 已更新 `findings.md`，记录“结构闭环”和“内容可靠”的边界。
- 已更新 `rebuild_manifest.md`，记录新增测试和第三阶段文档变更。

## 第三阶段当前待验证
/// 1. audit worker 暴露 `minos_core.audit.audit_chain`，或兼容别名 `audit_apqp_chain` / `run_quality_audit`。
/// 2. audit report 暴露 `counts`。
/// 3. audit report 暴露 `manual_review_items`。
/// 4. 运行 `python -m unittest tests.test_quality_audit -v`。
/// 5. 用 git status 审核修改范围是否仅限本轮允许的 5 个文件。

## 第三阶段风险
- 当前只负责测试和文档；在 audit worker 完成前，`tests/test_quality_audit.py` 会因为 audit 模块缺失而失败。
- 如果 audit 把弱链接直接变成 validate 失败，就会混淆第三阶段边界：validate 管结构闭环，audit 管内容可靠。
- 按工作范围限制，本轮未更新 `project_flow.mmd`，避免触碰用户未授权写入的文件。

## 第四阶段当前状态
第四阶段已完成：只针对 `limiter` 样本收口 legacy PFMEA/CP 链接质量，并补上审计回归门槛。

## 第四阶段已完成
- 已读取 `tests/fixtures/limiter/pfmea.json` 和 `tests/fixtures/limiter/control_plan.json`，并对照 `audit --input tests\fixtures\limiter` 输出定位问题。
- 已确认原始问题主要是：多个 PFMEA 被机械挂到同一个 CP、CP 反向 `pfmea_id` 错挂、文本 overlap 不理解“压力/位置/力矩/禁用物质”等质量工程词。
- 已改进 `minos_core/adapters/legacy_excel.py`：加入质量工程业务词、特殊特性分类优先、同工序全局匹配、必要的一对多派生控制行。
- 已改进 `minos_core/audit.py`：audit 的文本重合判定同步使用质量工程业务词，减少同义不同字面的误判。
- 已只重新生成 `tests/fixtures/limiter`，未重建 `door_hinge` 和 `stamping`。
- 已在 `tests/test_quality_audit.py` 增加 limiter 第四阶段回归门槛。

## 第四阶段指标结果
- `mechanical_links`：10 -> 0，目标 `<= 3`，已达成。
- `weak_links`：22 -> 1，目标 `<= 10`，已达成。
- `manual_review_items`：35 -> 4，目标 `<= 18`，已达成。

## 第四阶段待验证
/// 1. 运行 `python -m minos_core.cli validate --input tests\fixtures\limiter`。
/// 2. 运行 `python -m minos_core.cli audit --input tests\fixtures\limiter`。
/// 3. 运行 `python -m unittest discover -s tests -v`。
/// 4. 审核 git diff，确认改动聚焦 limiter 链接质量和回归门槛。

## 第五阶段当前状态
第五阶段已完成代码落地：MINOS-CORE 已按 Domain Core、Pipeline、Adapters、Quality Gates 四层拆清依赖方向。

## 第五阶段已完成
- Domain Core 已补齐业务对象：`Drawing`、`Characteristic`、`Evidence`，并保留原有 `Product`、`ProcessStep`、`FailureMode`、`ControlItem`、`TraceLink`。
- Domain Core 不再拥有 `_read_json` 文件读取；旧的 `load_apqp_chain` 仅作为兼容 wrapper 转发到 Adapter。
- 新增 `minos_core/adapters/fixture_json.py`，统一负责标准 fixture JSON / 目录读取。
- `pipeline.py` 新增固定 `PIPELINE_STAGES`，并统一调用 fixture adapter。
- `cli.py` 删除重复 fixture loader，改用 fixture adapter。
- 新增 `minos_core/quality_matching.py`，让 legacy adapter 与 audit 共用同一套质量工程文本匹配规则。
- 新增 `minos_core/quality_gates.py`，暴露阶段质量门 `evaluate_stage_gate` 和 `StageQualityGate`。
- 已补测试锁住：Domain Core 无文件 IO、fixture adapter 负责读取、Pipeline 阶段顺序、Quality Gate 阶段准入。

## 第五阶段待验证
/// 1. 运行 `python -m unittest discover -s tests -v`。
/// 2. 运行 CLI validate/export/audit smoke，确认旧入口仍可用。
/// 3. 审核 git diff，确认没有把 OCR/LLM 接进 Domain Core。

## 第六阶段当前状态
第六阶段已完成代码落地：阶段流转、证据引用、导出质量门 sheet、OCR/LLM adapter 占位接口均已实现。

## 第六阶段已完成
- 新增 `minos_core/stage.py`，提供 `StageContext`、`StageResult`、`build_stage_context`、`build_stage_result`、`run_stage`。
- `StageResult` 已包含 `stage/status/output/evidence/pending_fields/ai_inferred_items/quality_gate`。
- `ProcessStep`、`FailureMode`、`ControlItem`、`TraceLink` 已新增 `evidence_refs`，旧 fixture 默认 `[]`。
- APQP workbook 已从 5 张 sheet 扩展为 7 张：新增 `质量门状态` 与 `人工复核清单`。
- 新增 `minos_core/adapters/ocr.py` 和 `minos_core/adapters/llm.py`，只定义协议、结果对象、fake adapter 和 not-configured adapter。
- 已新增 `tests/test_stage_result.py` 和 `tests/test_ocr_llm_adapters.py`。
- 完整 unittest 已扩展到 26 项并全部通过。

## 第六阶段待验证
/// 1. 运行 CLI validate/audit/export smoke。
/// 2. 审核 git diff。
/// 3. 提交第六阶段改动。

## 第七阶段当前状态
第七阶段已完成代码落地：Evidence 已文件化，apqp_chain fixture 已补证据引用，Quality Gate 已能检查证据覆盖。

## 第七阶段已完成
- `fixture_json` 已支持目录下可选 `evidence.json`。
- `tests/fixtures/apqp_chain/evidence.json` 已新增 6 条证据。
- `process_flow.json`、`pfmea.json`、`control_plan.json` 已写入 `evidence_refs`。
- `StageQualityGate` 已新增 evidence coverage 输出：覆盖率、缺失引用、未覆盖对象、待确认证据。
- 有 evidence 池时，质量门会阻断未覆盖对象、缺失 evidence id、被引用 AI 推断证据和待确认证据。
- 无 evidence 池的旧 fixture 保持兼容，仍按三表结构存在判断证据充分。
- Excel `质量门状态` sheet 已显示证据覆盖率和证据问题数量。
- 完整 unittest 已扩展到 29 项并全部通过。

## 第七阶段待验证
/// 1. 运行 CLI validate/audit/export smoke。
/// 2. 审核 git diff。
/// 3. 提交第七阶段改动。
