# MINOS-CORE 重建发现

## 任务 2 发现
- 草案入口应复用现有 generated pipeline，而不是新增第二套生成逻辑；否则质量门、证据追溯和人工复核口径会分裂。
- `generate-draft` 的核心语义是“可审阅草案”，不是 `export` 的替代品；因此结果必须显式写出 `draft_is_formal_export=False` 和草案声明。
- 对含待确认证据的 generated draft，`validate` gate 可以 `can_continue=True`，但 `allow_user_export=False`，这正是草案入口需要暴露的状态。
- CLI 输出应是完整 JSON envelope，方便上层系统读取 quality gate、manual review 和 draft，而不是只打印路径或摘要。
- `run-pipeline` 适合作为 `generate-draft` 的兼容别名，但正式语义仍应优先使用 `generate-draft`。

## 第十二阶段发现
- AI analyze 的核心风险不是“抽不出来”，而是把 AI 猜测当成事实；因此 AI 只能补候选线索，不能作为正式 route 依据。
- 规则抽取仍应优先，AI 结果只做补充，不覆盖已有确定证据。
- 所有 AI 线索必须能追溯到已有 Evidence，不能凭空生成 `process_step_id` 或 source。
- `needs_confirmation` 和 `ai_inferred` 必须分开表达：前者是人工复核状态，后者是来源属性。
- analyze 阶段仍不允许用户导出，AI 输出必须继续经过 quality gate 与人工复核。

## 第十一阶段发现
- 生成链路最容易走偏的点不是 PFMEA 字段怎么填，而是把“上游待复核字段”误当成“本阶段硬阻断”。这次已拆成 `pending_fields` 和 `blocking_pending_fields` 两层语义。
- `brainstorm_failure_modes` 的预检不能完全等同 `generate_pfd` 的质量门：PFD 阶段缺 `operation` 应阻断，但 brainstorm 阶段需要让候选生成器运行，才能准确报告“某工序没有失效模式候选”。
- PFMEA 和控制计划生成当前应保持薄规则，输出工程确认占位与 `needs_confirmation`，不能假装已经完成正式工程评审。
- AI-only evidence、缺失 evidence ref、缺关键本体字段仍然必须阻断；否则会破坏“证据可追溯、AI 不越权”的核心边界。

## 第二阶段发现
- 三个真实 workbook 都能清楚映射到三类标准 fixture：过程流程图、PFMEA、控制计划。
- 真实迁移的关键不是 sheet 名，而是合并单元格和空白行的继承语义：工序编号、过程功能、PFMEA 原因、控制计划特性经常只在上方行出现。
- Excel 的 XML dimension 可能包含大量样式残留，adapter 不应按维度终点判断有效数据区，应按实际非空单元格和业务表头判断。
- 真实样本迁移必须先通过 core validation，再允许导出 workbook；不能为了导出 Excel 而绕过 PFD/PFMEA/CP 追溯校验。
- OCR/LLM 暂时不接回 core。它们后续只能作为 adapter 输出标准 fixture，与 legacy Excel adapter 走同一条验收链。

## 关键发现
- 当前仓库处在多人并行重建状态，测试和文档必须只约束公开契约，不能假设核心实现已经完成。
- sample config 之前混入了本地源路径、seed 文件路径、工艺关键字、规格值和特殊特性；这些内容属于数据源、规则或知识库，不应放在样本元数据配置里。
- APQP 三表 fixture 必须保留真实追溯关系，否则 validation 和 exporter 测试只能验证格式，不能验证链路。
- mandatory PFMEA 到 CP 的覆盖关系是重建验收的硬约束：高严重度、特殊特性或明确标为 mandatory 的 PFMEA 行，不能没有控制计划行。
- xlsx 导出风险不只在内容，还在文件结构：重复 sheet 名、非法字符、31 字符截断冲突、缺少 workbook relationship 都可能让 Excel 进入修复模式。
- CLI 测试必须覆盖实际命令，而不只测 Python 函数；否则最终交付入口可能与库接口脱节。

## 对核心代码 worker 的契约建议
- `minos_core.domain` 应暴露 `load_apqp_chain(path)`，读取包含 `process_flow.json`、`pfmea.json`、`control_plan.json` 的目录。
- domain loader 返回值可以是 dict、dataclass 或 Pydantic model，但必须能稳定访问 `process_flow`、`pfmea`、`control_plan`。
- `minos_core.validation` 应暴露 `validate_apqp_chain(chain)`，返回 bool、包含 `ok/valid` 的对象或 dict 均可，但失败信息中应包含缺失的 PFMEA id。
- CLI 建议固定为：
  - `python -m minos_core.cli list --samples-dir configs/samples`
  - `python -m minos_core.cli validate --input tests/fixtures/apqp_chain`
  - `python -m minos_core.cli export --input tests/fixtures/apqp_chain --output out.xlsx`

## 对 exporter worker 的契约建议
- xlsx writer 应在底层统一处理 sheet 名非法字符、31 字符限制和大小写不敏感去重。
- APQP 总工作簿 sheet 顺序固定为：摘要、过程流程图、PFMEA、控制计划、三表追溯矩阵。
- `.xlsx` 必须是标准 zip 包，至少包含 `[Content_Types].xml`、`_rels/.rels`、`xl/workbook.xml`、`xl/_rels/workbook.xml.rels` 和 worksheet XML。

## 对 legacy Excel adapter worker 的契约建议
- 暴露 `convert_legacy_workbook(workbook_path, fixture_dir)`。
- 输出目录必须包含 `process_flow.json`、`pfmea.json`、`control_plan.json`。
- 门铰链、冲压件、限位器都必须在 tempfile 目录中完成转换，不写固定 `output/`。
- 转换时需要处理合并单元格和向下继承，保证每条 PFMEA、控制计划行都能追溯到标准 `process_step_id`。
- 生成的 mandatory/high-risk PFMEA 行必须能被控制计划覆盖，否则 `validate_chain` 应失败。

## 当前限制
- 本轮没有实现 adapter，也没有改 core/exporter。
- 当前新增测试是第二阶段契约测试；如果 adapter 尚未落地，运行测试会暴露 import 或接口缺失。
- 没有删除任何文件，也没有改动允许范围外文件。

## 第三阶段发现
- 第三阶段质量审计必须和 validation 分层：validation 是硬门槛，负责判断链路是否闭环；audit 是质量审计，负责指出闭环内容是否可靠。
- 一个样本可以满足 PFD/PFMEA/CP 追溯闭环，但仍存在内容弱点，例如控制计划没有规格、测量方法过于主观、抽样频次缺失、反应计划为空。
- 这些弱点不应该直接变成 validate 失败，否则会把“结构不完整”和“内容需要人工判断”混在一起，导致用户不知道该修链路还是复核工程判断。
- audit report 至少需要稳定暴露两个面向后续 CLI 和文档的字段：`counts` 与 `manual_review_items`。
- `counts` 用于给管理层或 CLI 摘要说明风险数量；`manual_review_items` 用于交给工程人员逐条复核。
- 最小弱链接样本应保持结构闭环：PFMEA 行存在对应 PFD 工序和 CP 行，且 mandatory/high-risk 覆盖关系成立；这样才能证明 audit 发现的是质量风险，不是 validation 已经能发现的断链。

## 对 audit worker 的契约建议
- 暴露 `audit_chain(chain)`；兼容别名可以是 `audit_apqp_chain` 或 `run_quality_audit`。
- 输入应接受与 `validate_chain` 相同的 fixture bundle：包含 `process_flow`、`pfmea`、`control_plan`。
- 返回值可以是 dict、dataclass 或 Pydantic model，但必须能稳定访问 `counts` 和 `manual_review_items`。
- 对内容薄弱的机械控制项，报告文本或结构化字段中应能表达 mechanical、weak、manual review 三类语义。
- audit 不应通过修改 `validate_chain` 来表达质量问题；validate 仍只做结构闭环和必控覆盖的硬校验。

## 第三阶段限制
- 本轮没有实现 `minos_core/audit.py`，也没有修改 CLI。
- 当前新增测试是第三阶段契约测试；如果 audit worker 尚未落地，运行测试会暴露 import 或接口缺失。
- 按用户指定写入范围，本轮没有更新 `project_flow.mmd`。

## 第四阶段发现
- limiter 的主要问题不是 validation 断链，而是链接质量弱：旧转换器把多条 PFMEA 粗略挂到同一个 CP，或让 CP 的单值 `pfmea_id` 指向了不够匹配的 PFMEA。
- 单纯“同工序 + 文本 overlap”不适合限位器这类工艺文本，因为 PFMEA 常写“设备压力超差、位置不正确、力矩误判”，CP 常写“注油压力 5-10Mpa、注油泵位置 5.9±0.5mm、限位器功能力矩”。两边语义一致，但字面不一定重合。
- `SC/CC` 特殊特性分类是强匹配信号，应优先于普通文本 overlap；禁用物质、功能力矩这类控制还可能跨工序出现。
- CP 反向 `pfmea_id` 是单值，无法完整表达“一个粗粒度 CP 覆盖多条 PFMEA”。为了降低 mechanical links，本阶段对必要的一对多关系派生控制行，并保留 `derived_from_control_plan_id` 说明来源。
- audit 不能只用原始中文分块判断 weak link，否则会把“压力/注油压力/Mpa”“力矩/Nm”“位置/距离/mm”等同义工程控制误判为弱链接。

## 第四阶段结果
- limiter 审计指标已明显改善：`mechanical_links=0`、`weak_links=1`、`manual_review_items=4`。
- 仍保留 1 条 weak link 和 3 条 CP 字段缺失复核项，符合本阶段“明显变好，不追求完美”的目标。

## 第五阶段发现
- MINOS-CORE 的核心边界应先靠依赖方向保证，而不是靠大规模移动文件。当前更安全的做法是保留 `minos_core.validation`、`minos_core.audit`、`minos_core.domain.load_apqp_chain` 这些公开入口，同时把实际职责收回到正确层。
- Domain Core 不能知道 JSON 文件、目录结构和编码；这些属于文件系统 Adapter。保留兼容 wrapper 可以避免旧测试和旧调用方断裂。
- Pipeline 应声明固定阶段顺序，后续 OCR/LLM 图纸推理只应该接到 `ingest/analyze/generate_*` 这些编排点，不应直接写进 Domain Core。
- Quality Gates 需要同时表达硬门禁和软门禁：validation 决定是否能继续，audit 决定哪些内容需要人工复核，stage gate 汇总证据、待确认字段、AI 推断和导出许可。
- legacy adapter 和 audit 使用同一套质量工程文本匹配规则很关键，否则转换器建立的链接可能在审计阶段被另一套词库误判。

## 第六阶段发现
- StageResult 应作为 pipeline 外壳而不是替换旧 API；保留 `validate_fixture` 返回 validation result、`export_fixture` 返回 `Path`，可以避免破坏现有调用方。
- `Evidence` 本体应保持链级集中存储，PFD/PFMEA/CP/TraceLink 只保存 `evidence_refs`，避免嵌套重复和后续导出膨胀。
- Excel 交付不应只有三表，`质量门状态` 与 `人工复核清单` 是让用户判断“是否可信、哪里要复核”的必要交付页。
- OCR/LLM 现阶段只能作为 adapter 边界占位，不应出现 API key、SDK 或真实网络调用；真实结果以后应先进入 Evidence，再由 Quality Gates 判断是否可进入下一阶段。

## 第七阶段发现
- Evidence 文件化必须兼容旧 fixture：如果没有 `evidence.json`，不能让 door_hinge、stamping、limiter 这些历史样本突然失败。
- 一旦 fixture 明确提供 evidence 池，质量门就应该严格检查覆盖、缺失引用、AI 推断和待确认证据，否则 evidence_refs 只是装饰字段。
- AI 推断证据可以进入 Evidence，但不能直接作为可导出的正式依据；它应该阻断阶段流转并进入人工复核。
- Excel 中的证据覆盖率比单纯 `evidence_sufficient` 更有用，用户能直接看到覆盖对象数、缺失引用数和待确认风险。

## 第八阶段发现
- ingest 阶段不能复用 validate/export 的完整三表质量门；它的职责是判断“是否有足够原始证据进入 analyze”，不是判断三表是否可导出。
- `run_stage(stage="ingest")` 必须在构造 APQPChain 前提前返回，否则 manual JSON、OCR text、evidence-only bundle 会被错误当成 APQP 三表。
- 在 ingest 阶段，部分 AI 推断证据和待确认证据可以作为提示进入后续分析；但如果全部证据都是 AI 推断，就不能进入 analyze。
- FakeOCRAdapter 的价值是先验证 OCR 边界和 Evidence 落点，不引入真实 OCR 依赖。

## 第九阶段发现
- analyze 阶段必须保持“宁可少抽，不乱猜”：它只整理 drawing、characteristic、process clues，不推断 PFMEA/CP。
- `analysis_bundle` 不是 APQPChain；因此需要专用 `evaluate_analysis_bundle_gate`，不能把分析结果硬塞进现有三表质量门。
- 当前规则抽取能覆盖 fixture 中的 material thickness、rivet height、push-out force、barcode、pack quantity 和 P10/P20/P30 工序线索。
- 如果证据中明确写了 `Rev A/B/C`，系统可以抽出 revision；这种情况下不应再把 revision 标为 pending。
- analyze 阶段仍不允许用户导出，只能表示是否可以进入 `generate_pfd`。

## 第十阶段发现
- PFD gate 不能把 analyze 阶段遗留的 drawing/revision 待确认字段当成 PFD 结构阻断；否则已经生成有效 P10/P20/P30 的 PFD 会被误判 blocked。
- PFD 结构阻断应只看自身：step 数量、link 数量、step id、operation、evidence_refs、link from/to 是否有效。
- AI-only route evidence 必须阻断；但 OCR `needs_confirmation=True` 只进入人工复核，不应阻断 PFD 进入下一阶段。
- 生成 PFD 时不能照抄现有 fixture 的 process_flow；应从 Evidence -> Analyze 结果生成，保证路线来自证据链。
- `output_refs` 必须保持空列表，不能提前生成 PFMEA/CP 引用。

## 第十阶段前向筛查发现与修复
- 已修复 PFD gate 不检查 step/link `evidence_refs` 是否真实存在的问题；现在缺失顶层 evidence 会阻断。
- 已修复 link 缺少 `evidence_refs` 仍可能通过的问题；现在 link 证据链和 step 一样严格。
- 已修复 AI-only route 时 `evidence_sufficient` 语义不一致的问题；现在 AI-only 或 missing refs 会让 `evidence_sufficient=False`。
- 已把 `process_function` 和 `special_characteristics` 空值暴露为 review-only 项，避免伪造内容，也不阻断进入 brainstorm。
- 已新增 `brainstorm_failure_modes` 前置分支，避免下一阶段误走完整 APQPChain 校验路径。

## 第十阶段二次前向筛查发现与修复
- 已修复 analyze gate 把 phrase-only process clue 计为可进入 PFD 的问题；现在必须至少有 2 个合法 `Pxx` route clue。
- 已修复同一 evidence 同时输出 Pxx clue 和完全重复 phrase-only clue 的噪音。
- 已修复 OCR 待确认被误标为 AI 推断的问题；`needs_confirmation` 与 `ai_inferred` 已分开。
- 已修复 analysis bundle 中 `process_clues.source_ref` 可指向不存在 evidence 的漏洞。
- 已修复字符串形式 `pending_fields` 被静默丢弃的问题。
- 已修复 PFD/brainstorm gate 不检查 `link_type` 的问题。
- 已修复 brainstorm preflight report 仍显示 `stage_mode=generate_pfd` 的语义问题。
