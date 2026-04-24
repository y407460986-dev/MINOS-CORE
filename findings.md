# MINOS-CORE 重建发现

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
