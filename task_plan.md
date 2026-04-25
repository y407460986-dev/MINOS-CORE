# MINOS-CORE 重建任务计划

## 任务 2：generate-draft CLI/API 入口
本阶段目标是在现有 Evidence -> generated pipeline 基础上，新增一个明确的草案入口。入口只生成 APQPChain draft JSON，并同时输出质量门和人工复核信息；它不等同正式导出，不写 Excel，不绕过 export gate。

## 任务 2 执行流程
/// 1. 复用现有 `ingest -> analyze -> generate_pfd -> brainstorm_failure_modes -> generate_pfmea -> generate_control_plan -> assemble_generated_apqp_chain -> validate` 阶段。
/// 2. 在 `pipeline.py` 暴露 `generate_draft(evidence, output_path=None)` API，返回 draft envelope。
/// 3. draft envelope 必须包含 `draft_is_formal_export=False`、草案声明、APQPChain draft、quality gate、manual review 和 stage results。
/// 4. 在 `cli.py` 新增 `generate-draft` 子命令，并保留 `run-pipeline` 别名，不影响已有 list/validate/audit/export/convert-legacy。
/// 5. 在 `stage.py` 支持 `run_stage(..., stage="generate_draft")`，作为 API 外壳入口。
/// 6. 补 CLI/API 针对性测试，覆盖 JSON 输出、保存文件、别名和“草案不等同正式导出”声明。

## 任务 2 OpenSpec 四步闭环
1. Define：新增草案生成入口，不新增正式导出入口。
2. Specify：草案结果必须显式携带质量门和人工复核信息，且 `allow_user_export` 可为 false 时仍能返回 draft。
3. Implement：只复用 pipeline/stage 现有生成链路，不引入外部依赖，不安装依赖。
4. Verify：运行 targeted unittest 和 CLI smoke，确认旧 CLI 命令兼容。

## 第十二阶段：AI analyze 增强
本阶段目标是在 `analyze` 阶段接入可选 LLM adapter，把 Evidence bundle 增强为更完整的 `analysis_bundle`。本阶段不接真实外部服务，不生成下游 APQP 三表。

## 第十二阶段执行流程
/// 1. 保留 `keyword_rules` 作为默认基础路径。
/// 2. 通过 LLM adapter 生成 drawing / characteristic / process_clue 候选。
/// 3. AI 结果必须引用已有 evidence，并标记 `ai_inferred` 和 `needs_confirmation`。
/// 4. 合并规则结果与 AI 结果，不覆盖确定证据。
/// 5. analyze gate 继续检查 source_ref、AI-only、有效 Pxx route clue。
/// 6. 补测试并跑完整 unittest 与 CLI smoke。

## 第十二阶段 OpenSpec 四步闭环
1. Define：增强 analyze，不生成下游 APQP 三表。
2. Specify：analysis bundle 字段不破坏旧契约，新增 metadata 标记 AI 使用情况。
3. Implement：只通过 adapter 边界接入，不把 SDK/key 写进 core。
4. Verify：旧 keyword 测试不退化，AI-only 仍不能作为正式放行依据。

## 第十一阶段：PFMEA 与控制计划生成闭环
本阶段目标是在不搬目录、不接 LLM 的前提下，把 `brainstorm_failure_modes -> generate_pfmea -> generate_control_plan` 接通。

## 第十一阶段执行流程
/// 1. 新增薄规则 `generate_pfmea_from_candidates`，把失效模式候选转成正式 PFMEA bundle。
/// 2. 新增薄规则 `generate_control_plan_from_pfmea`，把 PFMEA row 转成控制计划 bundle。
/// 3. 在 `stage.py` 接入 `generate_pfmea` 和 `generate_control_plan`，保持旧 `validate/export` API 不变。
/// 4. 在 `quality_gates.py` 增加 PFMEA bundle 与控制计划 bundle 质量门。
/// 5. 区分上游待复核字段和本阶段硬缺字段：上游 pending 可继续生成草案，但本阶段缺证据、缺关键字段、AI-only 仍阻断。
/// 6. 补阶段契约测试并运行完整 unittest 与 CLI smoke。

## 第十一阶段 OpenSpec 四步闭环
1. Define：目标是补齐 APQP 生成链路，不做目录迁移。
2. Specify：用 unittest 固定 PFMEA/控制计划阶段的输入输出、证据引用和阻断行为。
3. Implement：新增两个 generator，接入 stage 和 quality gate。
4. Verify：运行 `python -m unittest discover -s tests -v`、CLI validate/audit/export smoke。

## 第二阶段：真实样本迁移
本阶段目标是把三个真实 Excel 源转换为 MINOS-CORE 标准 fixture，并用同一条核心链路验收：

- legacy Excel adapter 只负责读取旧 workbook 并输出标准 `process_flow.json`、`pfmea.json`、`control_plan.json`。
- core 仍只认标准 fixture/domain，不直接依赖 Excel、OCR、LLM 或本地知识库路径。
- OCR/LLM 后续继续作为 adapter 外挂，输出同样的标准 fixture，不进入 `domain`、`validation`、`exporters` 的核心边界。
- 测试输出必须写入 `tempfile`，不得恢复旧的固定 `output/` 目录。

真实源：
- `C:\Users\fgtan\Desktop\知识库种子\门铰链\JLH01000300-门铰链.xlsx`
- `C:\Users\fgtan\Desktop\知识库种子\冲压件\1004258-冲压件.xlsx`
- `C:\Users\fgtan\Desktop\知识库种子\限位器\XWQ01000100-限位器.xlsx`

## 当前职责
本轮只负责真实样本迁移的测试和文档，不写 `minos_core` adapter 或业务代码，不删除文件，不回退其他 worker 的改动。

允许写入范围：
- `tests/test_legacy_excel_adapter.py`
- `rebuild_manifest.md`
- `task_plan.md`
- `progress.md`
- `findings.md`

## 目标
在 clean baseline 之后增加真实样本验收门，让 adapter worker 输出的 fixture 必须能进入现有 validation 和 exporter 链路。

本轮交付内容：
- 新增 `tests/test_legacy_excel_adapter.py`。
- 测试 `convert_legacy_workbook(workbook_path, fixture_dir)` 能把三个真实 Excel 源转换为临时 fixture 目录。
- 每套转换后的 fixture 必须通过 `minos_core.validation.validate_chain`。
- 每套 fixture 必须能通过 `minos_core.pipeline.export_fixture` 导出 5 张固定 sheet 的中文 APQP workbook。
- 更新文档说明第二阶段目标和 adapter 边界。

## 成功标准
- 测试只写 `TemporaryDirectory`，不写固定输出目录。
- 三个真实样本都生成 `process_flow.json`、`pfmea.json`、`control_plan.json`。
- 三类 fixture JSON 都可解析，并且每类至少包含有效行。
- `validate_chain` 对三个真实样本全部通过。
- 导出的 workbook zip 结构完整，sheet 顺序固定为：摘要、过程流程图、PFMEA、控制计划、三表追溯矩阵。

## 执行流程
/// 1. 只读扫描现有 unittest、domain、validation、pipeline、exporter 接口。
/// 2. 编写真实 Excel adapter 契约测试，只依赖 `convert_legacy_workbook` 公开函数。
/// 3. 对每个真实样本使用 tempfile 生成 fixture。
/// 4. 对转换结果执行 JSON 解析、domain loader、validation、export 和 xlsx 打开性检查。
/// 5. 更新 `task_plan.md`、`progress.md`、`findings.md`、`rebuild_manifest.md`。
/// 6. 审核写入范围，确认未触碰 adapter 实现和其他 worker 文件。

## OpenSpec 四步闭环
1. Define：第二阶段验收对象是真实 Excel 样本转标准 fixture。
2. Specify：用 unittest 明确 adapter、validation、exporter 的公开契约。
3. Implement：只新增测试和文档，不实现 adapter。
4. Verify：adapter 就绪后运行真实样本测试；如 adapter 未就绪，测试应清楚暴露缺失接口。

## 非目标
- 不实现 `minos_core.adapters`。
- 不改变 domain、validation、pipeline、exporter。
- 不删除旧文件。
- 不把 OCR/LLM 逻辑接进 core。
- 不把真实样本输出写入固定 `output/`。

## 当前假设
- adapter worker 会暴露 `convert_legacy_workbook(workbook_path, fixture_dir)`。
- `convert_legacy_workbook` 返回值可以是 fixture 路径、包含 `fixture_dir` 的对象/dict，或 `None`；测试会以传入的 `fixture_dir` 作为默认结果目录。
- 当前 core 已暴露 `load_apqp_chain`、`validate_chain`、`export_fixture`。

## 第三阶段：质量审计
本阶段目标不是再增加硬校验，而是在 validation 已能确认结构闭环之后，继续识别内容可靠性风险。换句话说：

- validation 回答“PFD、PFMEA、CP 是否闭环，必控项是否有控制计划覆盖”。
- quality audit 回答“闭环内容是否可信，是否存在机械逻辑薄弱、控制方法太弱、需要人工复核的问题”。
- audit 发现问题不等同于 validate 失败；它应输出审计报告和人工复核项，帮助区分“结构闭环”和“内容可靠”。

## 第三阶段当前职责
本轮只负责质量审计的测试和文档，不写 `minos_core/audit.py`，不写 CLI，不删除文件，不回退其他 worker 的改动。

允许写入范围：
- `tests/test_quality_audit.py`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `rebuild_manifest.md`

## 第三阶段目标
新增 unittest，约束 audit worker 的公开契约：

- `audit_chain` 能对 `tests/fixtures/apqp_chain`、`door_hinge`、`stamping`、`limiter` 运行。
- audit report 必须包含 `counts`。
- audit report 必须包含 `manual_review_items`。
- 构造最小弱链接样本，验证 audit 能发现 mechanical / weak / manual review 问题。
- 同一个最小弱链接样本仍应通过 `validate_chain`，证明 audit 是质量审计，不是硬校验替代品。

## 第三阶段执行流程
/// 1. 只读扫描现有 fixture、validation、domain、CLI 和当前 audit 状态。
/// 2. 新增 `tests/test_quality_audit.py`，只依赖未来 audit worker 的公开 `audit_chain` 契约。
/// 3. 对四套标准 fixture 执行 audit smoke contract，检查报告包含 `counts` 和 `manual_review_items`。
/// 4. 构造最小弱链接链路：PFD/PFMEA/CP 仍闭环，但控制规格、方法、频次、反应计划明显不足。
/// 5. 同时运行 `validate_chain` 与 `audit_chain`：validate 必须通过，audit 必须提出 manual review。
/// 6. 更新 `task_plan.md`、`progress.md`、`findings.md`、`rebuild_manifest.md`。
/// 7. 审核写入范围，确认未触碰 `minos_core/audit.py`、CLI 或其他 worker 文件。

## 第三阶段 OpenSpec 四步闭环
1. Define：第三阶段验收对象是质量审计报告，不是结构硬校验。
2. Specify：用 unittest 固定 `audit_chain` 的报告字段和弱链接识别行为。
3. Implement：本轮只新增测试和文档；audit/CLI 实现由另一个 worker 完成。
4. Verify：audit worker 就绪后运行 `python -m unittest tests.test_quality_audit -v`。

## 第三阶段非目标
- 不实现 `minos_core/audit.py`。
- 不实现或修改 CLI audit 命令。
- 不改变 `validation.py` 的硬校验语义。
- 不把 audit 问题伪装成 validate 失败。
- 不更新 `project_flow.mmd`，因为本轮用户限定的写入范围不包含该文件。

## 第四阶段：限位器 legacy 链接质量收口
本阶段目标是只针对 `limiter` 真实样本降低机械挂接和弱链接数量，不扩大到 `door_hinge`、`stamping`，也不改变 core 的硬校验语义。

## 第四阶段目标
- 读取并对照 `tests/fixtures/limiter/pfmea.json`、`tests/fixtures/limiter/control_plan.json` 与 `audit --input tests\fixtures\limiter` 输出。
- 改进 legacy 转换器的 PFMEA/CP 匹配规则，减少只靠 `linked_control_plan_id` 的机械覆盖。
- 只重新生成 `tests/fixtures/limiter`。
- 补 limiter 审计回归门槛：`mechanical_links <= 3`、`weak_links <= 10`、`manual_review_items <= 18`。

## 第四阶段执行流程
/// 1. 只读定位 limiter 的 mechanical links、weak links 和反向 `pfmea_id` 错挂模式。
/// 2. 在 legacy adapter 中加入质量工程业务词、特殊特性优先、同工序多 CP 分配和必要的一对多派生控制行。
/// 3. 在 audit 文本判定中使用相同的质量工程业务词，避免“同义但字面不同”的有效控制被误判为 weak。
/// 4. 只运行 `convert-legacy --profile limiter` 重建 `tests/fixtures/limiter`。
/// 5. 运行 limiter validate、limiter audit 和完整 unittest。
/// 6. 更新流程图和重建文档，提交第四阶段改动。

## 第四阶段 OpenSpec 四步闭环
1. Define：第四阶段验收对象是 limiter 的 PFMEA/CP 链接质量，不是全样本重构。
2. Specify：用 `tests/test_quality_audit.py` 固定 limiter 阶段性审计门槛。
3. Implement：改 legacy 链接规则、audit 业务词判定，并只重建 limiter fixture。
4. Verify：运行 `python -m minos_core.cli validate --input tests\fixtures\limiter`、`python -m minos_core.cli audit --input tests\fixtures\limiter`、`python -m unittest discover -s tests -v`。

## 第四阶段非目标
- 不重建 `door_hinge` 和 `stamping` fixture。
- 不把质量审计问题变成 validation 硬失败。
- 不接入 OCR/LLM。
- 不追求 limiter 审计零问题，本阶段只要求明显变好并守住回归门槛。

## 第五阶段：四层架构边界落地
本阶段目标是把 MINOS-CORE 明确分成四层，并先用最小改动修正依赖方向，不做大规模搬目录。

四层定义：
- Domain Core：只管业务对象，包括 `Product`、`Drawing`、`Characteristic`、`ProcessStep`、`FailureMode`、`ControlItem`、`Evidence`、`TraceLink`。
- Pipeline：只管流程，包括 `ingest`、`analyze`、`generate_pfd`、`brainstorm_failure_modes`、`generate_pfmea`、`generate_control_plan`、`validate`、`export`。
- Adapters：只管外部依赖，包括 OCR、LLM、Excel 读取、Excel 导出、文件系统。
- Quality Gates：每一步判断证据是否足够、字段是否待确认、内容是否来自 AI 推断、是否能进入下一阶段、是否允许导出给用户。

## 第五阶段执行流程
/// 1. 把 fixture JSON 文件读取移出 `domain.py`，由 `minos_core.adapters.fixture_json` 承担。
/// 2. 保留 `domain.load_apqp_chain` 兼容 wrapper，但 Domain Core 不再拥有 `_read_json` 文件 IO。
/// 3. 在 `pipeline.py` 暴露固定 `PIPELINE_STAGES`，并统一调用 fixture adapter 读取输入。
/// 4. 抽出 `quality_matching.py`，让 legacy adapter 和 audit 使用同一套质量工程业务词。
/// 5. 新增 `quality_gates.py`，表达阶段质量门：证据、待确认字段、AI 推断、是否可继续、是否可导出。
/// 6. 补回归测试，锁住四层边界。

## 第五阶段 OpenSpec 四步闭环
1. Define：目标是架构边界和依赖方向，不是新增业务生成能力。
2. Specify：用测试约束 Domain Core 无文件 IO、Pipeline 阶段顺序、Adapter 负责 fixture IO、Quality Gate 暴露阶段准入。
3. Implement：新增 `fixture_json.py`、`quality_matching.py`、`quality_gates.py`，并最小调整现有导入。
4. Verify：运行完整 unittest，确认 legacy 转换、limiter gate、CLI、导出均保持可用。

## 第六阶段：阶段流转、证据追溯与交付增强
本阶段目标是在四层边界稳定后，把 pipeline 从普通函数调用升级为可追踪的阶段结果，同时让证据引用进入核心对象，并让导出的 Excel 带上质量门状态和人工复核清单。

## 第六阶段执行流程
/// 1. 新增 `StageContext` / `StageResult`，保留旧 `validate_fixture` / `export_fixture` 返回契约不变。
/// 2. 给 `ProcessStep`、`FailureMode`、`ControlItem`、`TraceLink` 增加 `evidence_refs`，兼容旧 fixture 缺省为空列表。
/// 3. APQP workbook 从 5 张 sheet 扩展为 7 张，新增 `质量门状态` 和 `人工复核清单`。
/// 4. 新增 OCR / LLM adapter 占位协议、fake adapter 和 not-configured adapter，不接真实外部服务。
/// 5. 增加回归测试，覆盖阶段结果、证据引用、导出 sheet、adapter 边界。
/// 6. 运行完整 unittest、CLI validate/audit/export smoke 后提交。

## 第六阶段 OpenSpec 四步闭环
1. Define：目标是可追溯阶段流转和可复核交付，不是接入真实 AI 服务。
2. Specify：StageResult 必须包含 `stage/status/output/evidence/pending_fields/ai_inferred_items/quality_gate`。
3. Implement：新增 `stage.py`、`adapters/ocr.py`、`adapters/llm.py`，并增强 domain/exporter。
4. Verify：完整测试必须通过，导出 workbook 必须包含 7 张固定 sheet。

## 第七阶段：Evidence 文件化与证据覆盖质量门
本阶段目标是把证据从内存 payload 推进到标准 fixture 文件，并让 Quality Gate 真正检查证据覆盖，而不是只检查三表结构存在。

## 第七阶段执行流程
/// 1. `fixture_json` 目录加载时可选读取 `evidence.json`，旧三文件 fixture 不受影响。
/// 2. 为 `tests/fixtures/apqp_chain` 新增 `evidence.json`，并给 PFD/PFMEA/CP 写入 `evidence_refs`。
/// 3. `quality_gates.py` 增加 evidence coverage report，检查未覆盖对象、缺失引用、AI 推断证据、待确认证据。
/// 4. Excel `质量门状态` sheet 增加证据覆盖率、未覆盖对象、缺失引用、AI 推断和待确认证据统计。
/// 5. 增加回归测试，确认新 fixture 有证据覆盖、旧 fixture 兼容、缺失/AI 证据会阻断阶段流转。

## 第七阶段 OpenSpec 四步闭环
1. Define：目标是 Evidence 闭环，不是 OCR/LLM 接入。
2. Specify：有 `evidence.json` 时，所有 PFD/PFMEA/CP 对象必须引用有效证据；AI 推断或待确认证据不能直接放行。
3. Implement：新增 fixture 证据文件、证据引用和 coverage gate。
4. Verify：完整 unittest、CLI validate/audit/export smoke 必须通过。

## 第八阶段：ingest 阶段落地
本阶段目标是把 `ingest` 从 pipeline 阶段名落成真实入口，让文件、manual JSON、fixture evidence 和 fake OCR 文本统一进入 Evidence bundle。

## 第八阶段执行流程
/// 1. 新增 `minos_core/ingest.py`，统一把输入资料归一化为 `evidence_bundle`。
/// 2. `run_stage(..., stage="ingest")` 提前执行 ingest，不要求输入已经是完整 APQPChain。
/// 3. 支持 `evidence_bundle` JSON、manual `content/text` JSON、fixture 目录 `evidence.json`、只有 `evidence.json` 的目录、fake OCR 文本和 FakeOCRAdapter。
/// 4. `quality_gates.py` 增加 stage-aware 策略：`ingest/analyze` 使用轻量 Evidence 入口门，`validate/export` 保持三表 evidence_refs 覆盖门。
/// 5. 增加 `tests/test_ingest_stage.py`，覆盖正向 ingest、AI-only 阻断、空 evidence 阻断、mixed AI/待确认提示。
/// 6. 运行完整 unittest、CLI validate/audit/export smoke 后提交。

## 第八阶段 OpenSpec 四步闭环
1. Define：目标是输入资料进入 Evidence，不生成 PFD/PFMEA/CP。
2. Specify：ingest 的 `StageResult.output` 必须是 `evidence_bundle`，`can_continue` 表示可进入 analyze。
3. Implement：新增 ingest 模块、stage 分支和 ingest/analyze 轻量质量门。
4. Verify：完整 unittest 必须通过，validate/export 行为不得退化。

## 第九阶段：analyze 阶段落地
本阶段目标是把 Evidence bundle 转成结构化分析结果，为后续 `generate_pfd` 提供输入线索，但不生成正式 PFD/PFMEA/CP。

## 第九阶段执行流程
/// 1. 新增 `minos_core/analyze.py`，用稳定关键词规则抽取 drawing、characteristic、process_clue、pending field 和 AI/待确认项。
/// 2. `run_stage(..., stage="analyze")` 支持 evidence_bundle、fixture dir、manual JSON、OCR text，必要时先执行 ingest。
/// 3. 新增 `evaluate_analysis_bundle_gate`，判断 analysis bundle 是否可进入 `generate_pfd`。
/// 4. analyze 质量门不允许用户导出，只表达是否可进入下一阶段。
/// 5. 增加 `tests/test_analyze_stage.py`，覆盖 fixture、manual JSON、OCR text、AI/待确认项、pending fields、validate/export 不退化。
/// 6. 运行完整 unittest、CLI validate/audit/export smoke 后提交。

## 第九阶段 OpenSpec 四步闭环
1. Define：目标是证据理解层，不是三表生成层。
2. Specify：analysis bundle 必须包含 `drawings`、`characteristics`、`process_clues`、`pending_fields`、`ai_inferred_items`。
3. Implement：只用规则抽取，不接 LLM，不猜 PFMEA/CP。
4. Verify：完整 unittest 必须通过，apqp_chain 可抽出至少 1 个 drawing、2 个 characteristic、2 个 process clue。

## 第十阶段：generate_pfd 阶段落地
本阶段目标是把 `analysis_bundle.process_clues` 转成正式 `process_flow`，形成可追溯的 PFD 基础，但不生成 PFMEA/CP。

## 第十阶段执行流程
/// 1. 新增 `minos_core/generate_pfd.py`，从 analysis bundle 生成 `process_flow`。
/// 2. 有明确 `Pxx` 的 process clue 才生成 `ProcessStep`，无 step id 的 clue 进入 `pending_fields`，不猜编号。
/// 3. 按 P 后数字排序生成步骤，并按相邻步骤生成 `TraceLink`。
/// 4. 每个 step/link 保留 `evidence_refs`，不填 PFMEA/CP output refs。
/// 5. 新增 `evaluate_pfd_bundle_gate`，判断是否可进入 `brainstorm_failure_modes`。
/// 6. `run_stage(..., stage="generate_pfd")` 支持 analysis bundle、evidence bundle、fixture、manual JSON、OCR text。
/// 7. 增加 `tests/test_generate_pfd_stage.py`，覆盖 P10/P20/P30、links、evidence_refs、manual/OCR 输入、AI-only 阻断、validate/export 不退化。

## 第十阶段 OpenSpec 四步闭环
1. Define：目标是生成 PFD，不是生成 PFMEA/CP。
2. Specify：生成结果必须是 `process_flow`，包含 `steps`、`links`、`evidence_refs`。
3. Implement：只从明确 process clues 生成步骤和顺序，不猜工序编号。
4. Verify：完整 unittest、CLI validate/audit/export smoke 必须通过。
