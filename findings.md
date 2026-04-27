# 当前主目标发现：AI 图纸驱动三表生成工具

- 用户真正需要的是从图纸自动生成 PFD/PFMEA/CP，不是完整 PPAP 18 项平台；因此主线应优先服务图纸识别、工艺路线推理、PFMEA 推理和 CP 生成。
- 图纸输入阶段必须先证据化页面，后续所有 AI 识别、PFD、PFMEA、CP 都要引用 `drawing_page_001` 这类 evidence ref，否则无法解释 AI 推理来源。
- 当前环境没有 PyMuPDF / pypdf / pdfplumber，只有 Pillow；因此图片输入可以先完整落地，PDF 渲染必须作为显式依赖边界，缺渲染器时直接失败。
- AI 图纸识别不能 fallback 成空结果或脚本猜测；非法 JSON、引用不存在证据、关键字段缺失都必须被质量门暴露。
- PFD/PFMEA/CP 第一版应默认保留 `ai_inferred`、`confidence`、`needs_confirmation`，避免把 AI 草案包装成正式工程结论。
- Codex 当前配置可作为 MINOS 第一版 AI 配置来源：读取 `config.toml` 的 Responses 模型和中转地址，读取 `auth.json` 或当前环境变量中的 key；诊断输出只能暴露来源和是否配置，不能输出密钥值。
- Codex 能正常使用 `https://allinai7.cloud` 并不代表 MINOS 的请求完全一致；实际日志显示 Codex 的 Responses 路径是 `responses`，且 provider 声明 `requires_openai_auth = true`，因此 MINOS 必须避免用旧的 `ARK_API_KEY` 或固定 `/v1/responses` 造成鉴权/路径偏差。
- 当前真实运行环境中，MINOS 已能解析 Codex 配置的中转地址和可用 API key；在当前中转上，`gpt-5.4` 已验证可走通标准 HTTP Responses 三表草案链路，而 `gpt-5.5` 暂不稳定。
- 桌面端之前必须先稳定后端闭环；`generate_three_tables_from_drawing(...)` 现在是桌面端应调用的业务入口，避免把图纸识别、质量门和导出逻辑散落到 UI。
- 桌面业务闭环 MVP 已落地后，桌面端的关键边界从“能打开界面”变成“通过服务层记录项目、run、export，并后台调用 core pipeline”；UI 不应复制三表生成逻辑。
- SQLite `out/desktop/minos_desktop.sqlite3` 只应保存桌面项目、设置、运行状态和导出记录，不应保存明文 API key。
- 桌面失败报告需要面向工程人员决策：保留原始错误，说明原因判断，并给出三种处理方案，其中必须包含“放弃任务”。
- 未经人工复核的 AI 草案可以导出 draft 三表包，但 final export 必须被质量门阻断，这是第一版最重要的工程边界。
- 严格三表一致性硬门必须区分适用对象：MINOS 新生成/人工编辑后的三表链路要硬阻断，历史 legacy fixture 和质量审计弱链接样本仍应由 audit 提醒，避免把旧数据迁移问题误判成核心 validate 失败。
- 桌面骨架第一版应直接调用 `minos_core.pipeline`，不要先接 `minos_platform` HTTP/项目状态机；否则会把本地桌面最短闭环复杂化。
- PySide6 必须是可选依赖，否则没有 Qt 的测试和后端部署环境会被桌面 UI 破坏。
- 下一阶段真实桌面试跑的重点不是新增能力，而是证明现有三表工具在真实 Windows 桌面环境里能安全跑完：AI 配置诊断、safe demo drawing、后端 CLI smoke、桌面人工验收、xlsx 可打开性和完整回归命令都要留下记录。
- demo 图纸必须坚持合成/脱敏/授权输入；不应为了验收效果提交真实客户图纸，否则会把工程验收变成数据合规风险。
- `ai-config`、`write-demo-drawing`、`generate-three-tables`、`accept-three-tables`、`minos_desktop.cli --smoke`、`unittest`/`pytest` 是当前最小验收命令集；真实桌面 UI 人工验收仍通过 `minos-desktop` 完成。
- xlsx 验收不能只看文件存在；当前实现先做 OpenXML zip 结构体检，真实 Excel 打开验证仍要靠人工桌面验收补齐。

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

## Phase 6 pilot 发现
- input_package fixture（evidence_bundle + review_patch）可以无缝接入 `generate_draft`，不需要新建生成路径。
- `build_review_patch_template` 生成模板时，所有 reviewer 身份、timestamp、reason、evidence_refs 都留空，保证模板不能被误当成已批准 patch。
- `apply_review_patch` 靠 `template_status` 字段检查拒绝未完成模板，这是最小、最可靠的边界保护，不需要额外的 flag 或枚举状态。
- `run_manifest` 的 `inputs`/`outputs` 收紧为 object 后，调用方（pipeline 里的 generate_draft、apply_review、export_draft_fixture）传的都是 dict，已经符合新格式，不需要额外适配。
- 脱敏真实项目模板 fixture 必须确认没有任何真实客户名称、供应商名称、人员姓名、联系方式、价格、精确产能、客户门户编号、未授权图纸页或完整专有规范片段；当前 fixture 已确认符合。
- `tests/test_phase6_pilot_workflow.py` 是端到端回归，必须覆盖完整链路和关键负向场景（模板不能 apply、未 review draft 不能 export）。

## 桌面业务闭环 MVP 发现
- 桌面端现在适合作为三表生成工具的本地业务入口，而不是平台项目管理层；它应优先服务“导入图纸、生成三表草案、复核、导出”这条最短路径。
- `DesktopSettingsStore`、`DesktopProjectStore` 和 `DesktopRunService` 把 UI、SQLite 和 core pipeline 隔离开，后续桌面交互变化不应反向污染 core。
- `DesktopRunState`、`DesktopRunRecord` 和 `DesktopExportRecord` 是桌面可追溯性的最小记录，不需要引入完整 PPAP Package 状态机。
- 设置页只显示 AI 配置状态和默认输出目录是正确边界；明文 key 继续由运行时配置读取，不进入数据库、日志或界面。
- PySide6 懒加载让桌面测试和 core/platform 测试可以分离，避免可选 UI 依赖破坏后端环境。
- README 中平台和 PPAP Package 内容应持续标明“可选平台层/历史兼容层”，否则读者容易误以为主线又回到完整 PPAP 平台。
- 桌面软件语言应在显示层中文化，而不是把内部 JSON/schema 字段名改成中文；否则 edit_patch、质量门和导出服务会被不必要地破坏。
- 表格列名、导出摘要和人工复核摘要是用户最常看的三处入口，不能直接把 `process_step_id`、`quality_gate`、`raw_count` 这类内部键暴露给工程用户。
- Excel 表头也是软件交付界面的一部分，用户打开后不应看到 `PFMEA ID`、`CP ID` 这类英文表头；标准缩写 PFMEA/CP 可保留，但字段说明应中文化。
- 只把表头改中文还不够；PFD/PFMEA/CP 草案里的工序名称、过程功能、失效模式、控制方法和 AI 推理说明同样是软件用户界面的一部分，必须默认中文。
- 为了兼顾工程逻辑和中文显示，工艺识别应保留内部 canonical key，但用户可见 `operation`、`process_function`、PFMEA 风险和 CP 控制文本必须输出中文。
- AI prompt 需要直接要求“用户可见业务内容必须中文”；否则真实模型即使返回合法 JSON，也可能继续生成英文草案。

## 真实桌面试跑与交付验收发现
- 桌面交付验收的第一层应该是本地 preflight，而不是默认发起真实 AI 生成；否则验收会被外网、模型额度、API key 和 Qt 环境混在一起。
- PySide6 未安装在无 Qt CI 或后端开发环境里是正常状态，应记录 warning，并把真实 UI 启动阻断留给 `minos-desktop` 常规启动路径。
- AI 配置验收只需要暴露 key 是否存在和来源；任何模型配置、auth 文件或环境变量中的 secret 都不应进入 JSON 报告。
- SQLite 写入检查在 Windows 上需要显式关闭连接，否则临时目录清理可能遇到文件占用。
- CLI `main()` 增加 argparse 后要兼容旧的单元测试直接调用方式；否则 unittest 自身参数会污染桌面 CLI 参数解析。

## 真实样本闭环验收与最小修复发现
- MINOS 复用 Codex 配置时，应该只复用鉴权和中转地址，不应默认继承 Codex 主模型；否则会出现 README 写 `gpt-5.4`，运行时却悄悄回到 `gpt-5.5` 的配置漂移。
- 对当前这条中转链路，`gpt-5.4` 已经被三类真实图纸样本验证可用，继续把它作为 MINOS 默认模型是当前最稳妥的选择。
- 真实 AI 调用偶发 `503 Service temporarily unavailable` 仍会出现，但在未改代码的情况下重试成功，说明这更像上游网关瞬时抖动，不是当前三表链路的必然逻辑错误。
- 三类真实图纸目前都能稳定产出 PFD/PFMEA/CP 和四个导出文件，但统一落在 `needs_review`，说明产品当前定位仍然是“工程草案生成器”，不是“可直接签发的正式工程文件生成器”。
- 当前最主要的质量问题不是“导不出”，而是人工复核量偏大；后续优化应优先减少明显可自动补足的字段缺失和弱推断，而不是去放宽质量门。
- `pip install -e ".[desktop]"` 在这台机上容易因为 `PySide6` 大包下载而表现成“超时但后台仍在跑”；直接单装 `PySide6` 更容易拿到真实安装结果，也更适合作为交付验收时的排障步骤。
- `PySide6` 已安装后，导入阶段仍可能因为极端环境变量状态失败，例如测试里把 `PATH` 清空；桌面 preflight 需要把这种情况当成可报告的失败检查，而不是直接异常退出。
- 桌面 smoke 现在可以给出清晰分层结论：`PySide6`、AI 配置、本地输出目录、SQLite、入口导入五项前置条件全部可独立判断，这对真实交付现场很有价值。

## 复核负担压缩发现
- 三类真实结果的 `manual_review.items` 最大噪音不是新风险，而是同一风险被多种格式重复表达：结构化 `AuditItem`、裸字符串、`failure_mode:` 前缀、`control_item:` 前缀会同时出现。
- 最安全的第一步不是降低置信度阈值或放宽质量门，而是在结果 envelope 层统一复核目标并去重，这样不会改变 `allow_user_export`。
- `PFD.special_characteristics` 为空不能默认等于问题。普通工序没有特殊特性是正常状态；只有工序自身待确认、或存在特殊特性未分配到工序时，才值得提示人工复核。
- 当前已实现的是低风险压缩：减少重复展示和普通空字段噪音。更深层压缩仍应继续保留工程边界，例如低置信度图纸识别、高风险 PFMEA、CP 关键控制缺规格/方法等不能自动消失。
- 真实样本离线重算显示，人工复核展示项可从 437 项降到 145 项，减少约三分之二，同时正式导出仍被质量门阻止。
- 特殊特性映射问题应该聚合表达：如果图纸识别出了顶层特殊特性，但 PFD 工序没有挂载对应特性，工程人员需要看到“哪些特性未分配”，而不是每个普通工序都收到一条空 `special_characteristics` 提示。

## AI 风险推理增强发现
- 人工复核负担不应靠删除风险来降低，而应靠 AI 先把 PFMEA/CP 主体内容写完整，再只突出高风险和不确定项。
- PFMEA 的价值在于“风险思考”，不是字段填充；每道工序至少需要覆盖功能失效、过程执行错误、工艺类型特有风险，以及特殊特性风险。
- PFMEA 风险条数不应被固定上限绑死；如果图纸和工艺推理得出 6 条有效风险，就应该保留 6 条，质量控制重点应放在去重、证据引用、AI 理由和人工复核边界。
- CP 的价值在于把 PFMEA 风险转成可执行控制；即使缺图纸直接规格，也应先给出草案控制意图、测量方法、频次和反应计划，并明确标记 AI 推理来源。
- `ai_inferred_items` 和 `manual_review.items` 需要分工：前者用于阻断 final export，后者用于减少工程人员真正要看的清单。普通 AI 草案不应逐条进入人工复核，但仍不能直接正式放行。

## Responses 流式与图纸预处理发现
- Codex 能用同一 `allinai7.cloud`，但 MINOS 直接请求失败，根因不是 base URL 或 key，而是请求形态没有带 Codex 配置中的 `store:false` 和 `reasoning.effort`。
- 真实图纸图片分析不适合纯同步等待；即使最终模型能返回，也需要 streaming 事件让调用方知道请求仍在进行，并能在失败时保留上游事件。
- 图纸类输入不应该长期依赖“整页图片一次性丢给 VLM”。后续应增加本地预处理 adapter：先做 OCR、版面/表格/图框切分和标题栏抽取，再让 VLM 针对关键区域推理。
- PaddleOCR/PP-Structure 更适合做布局分析、表格识别和 OCR；Docling 更适合把 PDF/图片转成结构化文档表示。这两类都可以作为 VLM 前的降噪层，而不是替代最终工程推理。

## 中文交付与复核清单发现
- 输出给工程人员的内容必须默认中文，尤其是 warning、人工复核摘要、失败原因和处理建议；英文状态码可以保留给机器字段，但不能作为主说明。
- “100 多条人工复核项”本质上是质量门明细，不适合直接作为用户第一眼看到的清单；应该先按图纸识别、PFD、PFMEA、CP 和草案确认聚合。
- 聚合复核项不能删除明细。正确做法是 `items` 展示少量中文摘要，`raw_items` 保留完整对象，既降低阅读负担，也保证审计追溯。
- 复核项减少展示数量不等于放宽质量门；正式导出仍必须等待人工确认 AI 草案和高风险项。
- 桌面端和 Excel 是用户最容易看到“100 多项”的地方，因此它们也要默认读 `manual_review.items` 聚合摘要；`raw_items` 只能作为结果 JSON 的审计明细存在。

## 人机协同三表编辑器发现
- MINOS 的产品核心不是“一键生成正式三表”，而是 AI 生成草案后，由工程人员在软件内删改增补并逐行确认。
- `edit_patch` 应独立于 `review_patch`：前者表达表格内容编辑，后者表达复核确认；两者都不能覆盖原始 AI 草案。
- 软删除比物理删除更适合工程审计：导出时过滤，审计时仍能看到 AI 生成过什么、人工删除了什么。
- 正式导出必须依赖逐行确认，而不是只看质量门结构是否通过；否则 AI 草案可能在字段完整但未经人工确认时被误放行。

## Core 三表联动发现
- PFD 必须成为 PFMEA 的唯一工序来源；否则 PFMEA 会出现看似完整但无法追溯到流程图的孤儿工序。
- PFMEA 继承的不只是工序号，还包括工序名称、功能、产品特性、过程特性和特殊特性；这些字段是后续 CP 判断控制对象的上下文。
- CP 只保存 `pfmea_id` 不够，仍需保留 PFMEA 的失效原因、预防/探测控制、特殊特性和高风险来源，方便质量门判断“有 CP 行”和“有有效控制”。
- “特殊特性贯穿”应作为三表一致性硬检查：PFD 识别到的特殊特性如果没有进入 PFMEA 和 CP，导出的三表结构再完整也不可信。
- CP 的检具/测量方法、频率和反应计划是控制计划最低可执行性字段，缺失时应直接暴露为 validate/quality gate 问题。
- PFMEA/CP 表格只显示自身字段会让工程人员失去上下文：PFMEA 需要看到 PFD 的工序名称、过程功能和特性；CP 需要看到 PFMEA 来源和失效模式。
- 继承显示值不能被当成用户修改直接写回，否则打开表格再保存就会生成噪音 `update`；显示层应把继承值纳入当前行模型的原始值，只在人工真的改动时生成 patch。
- 空 `edit_patch` 不应送到 core apply 入口；这不是一次有效人工编辑，桌面端直接提示“无需保存”更符合工程人员预期。

## MINOS-CORE v1.5 AIAG-VDA PFMEA 专业化增强发现
- AIAG-VDA 专业门和三表一致性门不能混用同一个开关。`strict_three_table_linkage` 适合表达 PFD/PFMEA/CP 断链检查；AP 措施闭环、知识库推荐和变更影响需要独立的 `strict_aiag_vda_pfmea_gate`，否则旧 fixture/legacy 导出会被新规则误伤。
- AP 应作为正式质量门的主依据，RPN 只能做辅助显示；否则用户会在 AIAG-VDA 语义和传统 RPN 语义之间来回摇摆。
- 措施闭环不能只看“有没有推荐措施”。高 AP 至少需要推荐措施、责任人、目标日期；措施完成后还必须补措施后 S/O/D/AP，否则风险是否真正降低不可判断。
- 知识库推荐的正确位置是“待人工处理的建议”，不是自动写入正式字段。采纳和忽略都必须留下 patch，忽略高相似建议时必须有原因。
- 变更管理第一版不需要审批流，但字段级 before/after、变更原因和下游影响项必须保留；否则 PFD 改了以后 PFMEA/CP 是否同步无法追溯。
- 用户可见复核摘要不能因为新增知识库推荐而扩成更多类别。更好的做法是把知识库推荐归并进 PFMEA/CP 复核摘要，`raw_items` 保留完整明细。
- AIAG-VDA 的 `function_requirement` 不能直接当作 CP 的正式规格使用；如果图纸没有明确规格，CP 应展示中文“草案控制意图”，提醒用户这是待确认控制意图。
- v1.5 严格门应只作用于 MINOS 新三表生成和人工编辑闭环；旧样例、legacy Excel 转换和已有标准 fixture 仍应维持原有兼容导出能力。

## MINOS v1.6 桌面专业闭环发现
- v1.5 的专业门只有接到桌面页面才算真正可用；否则 AP 措施闭环、变更影响和知识库推荐只是后端阻断原因，工程人员很难直接处理。
- 措施管理适合做成 PFMEA 的集中视图，而不是重新发明一张独立表；它显示同一批 PFMEA 行的责任人、日期、状态和措施后评价即可。
- 推荐和变更影响都应通过 `edit_patch` 记录，而不是在桌面数据库里单独维护一套“处理状态”；这样正式导出、审计历史和恢复编辑状态可以共用 core 规则。
- 桌面运行记录必须累计 patch。只保存最后一次 patch 会让用户关闭软件后丢失之前的处理痕迹，特别是推荐忽略和变更影响处理。
- 本地知识库第一版用 SQLite 比 JSON 更适合桌面软件，因为它可以和项目/run 数据放在同一个本地数据库里，并支持启用/停用和后续编辑。
- PFMEA 筛选的价值在于快速定位要处理的行；筛选结果不能改变底层数据，保存仍应基于完整表格模型和 patch。
- “沉淀为知识库”第一版只需要把当前推荐转成本地规则，后续再做更细的工序/失效模式/检具分类编辑。

## MINOS v1.7 导出与验收发现
- 导出文件是工程交付的最后一道可见边界；即使 JSON 里有质量门和 edit_history，正式 Excel 里没有审计摘要也会让验收人员难以判断文件是否真的经过人工确认。
- 草案标记不能只藏在一个独立 sheet；拆分出来的 PFD/PFMEA/CP 文件也要在首行直接说明 `draft_only`、需要工程复核、不能提交客户。
- PFMEA 列顺序应跟审核思路一致：先看过程结构和功能要求，再看失效/后果/原因，再看 S/O/D/AP/RPN，最后看措施闭环和证据。
- 软删除不是丢弃数据。导出时可以过滤正式表格行，但正式审计页必须告诉用户有多少行被软删除、分别属于哪张表。
- Excel 可打开测试至少要验证 xlsx zip 包、workbook.xml 和工作表 XML 存在；这比只判断文件存在更能防止损坏导出流入验收。
