## 当前主目标：AI 图纸驱动三表生成工具

- 已完成：将产品目标从“完整 PPAP 平台”收口为“AI 图纸驱动 PFD/PFMEA/CP 三表生成工具”，第一版不做完整 PPAP 18 项、不做客户门户、不做审批流。
- 已完成：新增 `minos_core/drawing_input.py`，支持 PDF/PNG/JPG 输入识别；PNG/JPG 可生成 `drawing_page_001` 证据，PDF 在未安装 PyMuPDF 时明确失败，不做假渲染。
- 已完成：新增 `minos_core/adapters/multimodal.py`，定义云端多模态图纸识别 adapter 边界和 fake adapter。
- 已完成：新增 `minos_core/ai_config.py`，MINOS 可复用 Codex 的 Responses 模型、中转地址和 auth 配置；密钥只在运行时读取，不写入仓库、不输出。
- 已修复：当 Codex provider 配置 `requires_openai_auth = true` 时，MINOS 不再误用当前环境中的 `ARK_API_KEY`，会优先使用 Codex auth；Responses endpoint 也按 Codex 的 `responses` 路径调用，避免中转 URL 被拼成不一致的 `/v1/responses`。
- 已完成：`python -m minos_core.cli ai-config` 可显示 AI 配置状态；当前推荐模型已收口为 `gpt-5.4`，并已用真实调用验证可在 Codex 配置的中转地址上完成三表草案生成。
- 已完成：新增 `analyze-drawing` CLI，支持用当前 OpenAI/Codex Responses 配置调用云端多模态 AI，输出 `drawing_analysis_bundle` JSON。
- 已完成：新增 `minos_core/drawing_analysis.py`，定义 `drawing_analysis_bundle`、AI JSON 解析、证据引用校验和图纸识别质量门。
- 已完成：新增 `minos_core/drawing_to_pfd.py`，从图纸识别的 manufacturing clues 推理 PFD 草案。
- 已完成：新增 `minos_core/pfd_to_pfmea_ai.py`，从 PFD 为每道工序生成 PFMEA 草案并保留 AI/复核标记。
- 已完成：增强 `generate_control_plan_from_pfmea`，CP 行保留 confidence、ai_inferred、ai_reasoning。
- 已完成：新增 `minos_core/exporters/three_table_workbooks.py`，支持统一三表工作簿和三份独立 Excel 导出。
- 已完成：新增 `generate_three_tables_from_drawing(...)` 后端闭环入口，串联图纸证据化、AI 图纸识别、PFD、PFMEA、CP、质量门、三表导出和 run manifest。
- 已完成：新增 `generate-three-tables` CLI，默认导出 draft 三表包；final export 在未复核 AI 草案时被质量门阻断。
- 已完成：新增 `minos_desktop` Windows 桌面业务闭环 MVP，PySide6 作为可选依赖，包含项目、图纸导入、AI 识别结果、PFD、PFMEA、CP、人工复核、导出、设置页面。
- 已完成：新增 `minos_desktop/services.py`，通过服务层管理桌面项目、设置、运行状态和 core pipeline 调用。
- 已完成：桌面端默认使用 SQLite `out/desktop/minos_desktop.sqlite3`，保存项目、run 记录和导出记录。
- 已完成：新增 `DesktopSettingsStore`、`DesktopProjectStore`、`DesktopRunService`，以及 `DesktopRunState`、`DesktopRunRecord`、`DesktopExportRecord`。
- 已完成：Qt UI 已通过服务层创建/更新项目，后台运行 `generate_three_tables_from_drawing(...)`，并刷新 AI/PFD/PFMEA/CP/复核/导出页。
- 已完成：设置页显示 AI 配置状态和默认输出目录，不显示、不保存明文 API key。
- 已完成：桌面失败报告包含原始错误、原因判断和三种处理方案，且包含“放弃任务”。
- 已完成：新增 `minos-desktop` 启动入口；未安装 PySide6 时会明确提示安装 `.[desktop]`，不破坏 core/platform 测试。
- 已完成：桌面端用户可见语言已收口为中文：三表表头、文件选择器、设置摘要、人工复核摘要、导出摘要、导出完成提示均使用中文显示；内部字段名仍保持英文以兼容 edit_patch 和服务层。
- 已完成：三表独立 Excel 中用户可见的 `PFMEA ID`、`CP ID` 已改为中文编号表头。
- 已完成：AI 识别 prompt 已要求模型返回中文业务内容；本地 PFD 工艺库、PFMEA 风险模板、CP 控制计划模板已改为中文，桌面表格中的草案工序、过程功能、失效模式、控制方法等不再默认生成英文。
- 已完成：新增中文工序归一化，AI 返回“落料/冲孔/注塑/装配”等中文工序时仍可识别工艺族并补齐三表。
- 已完成：第一层三表核心联动已收口：PFD 主数据字段扩展，PFMEA 继承 PFD 工序上下文，CP 保留 PFMEA 来源、风险与检具信息；严格三表一致性硬门仅对 MINOS 新生成/人工编辑链路启用，旧 fixture 和弱链接审计样本继续保持兼容。
- 已验证：`python -m unittest tests.test_desktop_shell tests.test_qt_app_helpers -v` 通过。
- 已验证：`python -m pytest tests/test_desktop_table_editor.py tests/test_qt_app_helpers.py tests/test_desktop_shell.py -q`：19 项通过。
- 已验证：`python -m pytest tests/test_ai_drawing_three_table_workflow.py tests/test_openai_multimodal_adapter.py tests/test_generate_control_plan_stage.py -q`：35 项通过。
- 已验证：`python -m pytest tests/test_desktop_table_editor.py tests/test_generate_control_plan_stage.py tests/test_ai_drawing_three_table_workflow.py -q`：35 项通过。
- 已验证：`python -m unittest discover -s tests -v`：284 项通过。
- 已验证：`python -m pytest tests/platform -q`：27 项通过。

## 桌面业务闭环 MVP 当前状态
桌面业务闭环 MVP 已落地。当前桌面端定位仍是 AI 图纸驱动 PFD/PFMEA/CP 三表生成工具的本地操作壳，不是完整 PPAP 平台。

## 桌面业务闭环 MVP 已完成
- `minos_desktop/services.py` 已承接桌面项目、设置、运行记录、导出记录和后台 run 服务。
- 默认数据库为 `out/desktop/minos_desktop.sqlite3`。
- Qt UI 已从直接界面骨架升级为通过服务层驱动 core pipeline，并把结果同步到 AI 识别、PFD、PFMEA、CP、人工复核和导出页面。
- AI 配置只展示状态和来源，不显示或持久化明文 key。
- PySide6 仍为可选依赖和懒加载，不影响无桌面依赖环境。

## 桌面业务闭环 MVP 验证结果
/// 1. `python -m unittest tests.test_desktop_shell tests.test_qt_app_helpers -v`：通过。
/// 2. 后续仍建议在完整回归中覆盖 `python -m unittest discover -s tests -v`，并手工打开桌面 UI 检查真实文件导入和导出路径。

## 真实桌面试跑与交付验收当前状态
桌面/CLI 自检脚本已落地。默认验收只做本机 preflight，不调用真实 AI 网络，也不要求 PySide6 必须安装。

## 真实桌面试跑与交付验收已完成
- 已新增 `minos_desktop/preflight.py`，输出结构化 JSON 风格报告：`status`、`checks`、`warnings`、`recommendations`。
- 已检查 PySide6 安装状态；未安装时记录 warning，不破坏无 Qt 测试。
- 已检查 AI 配置状态，只显示 `api_key_configured`、`api_key_source`、`api_key_env_name` 等来源信息，不输出明文 API key。
- 已检查默认输出目录和 SQLite DB 写入能力。
- 已检查 `minos_desktop.cli` 和 `minos_desktop.qt_app` 桌面入口可导入。
- 已在 `minos_desktop/cli.py` 增加 `--smoke`、`--output-dir`、`--db-path`、`--require-ai-config`。
- 已新增 `tests/test_desktop_preflight.py`，覆盖缺 PySide6、SQLite 可写、AI key 脱敏、失败格式包含“放弃任务”、CLI smoke JSON 输出。
- 已新增 `minos_core/demo_acceptance.py`，可生成合成 safe demo drawing，并检查 `three_table_generation_result`、manifest、exports、AI evidence refs、PFD/PFMEA/CP 内容和 xlsx zip 可打开性。
- 已在 `minos_core.cli` 增加 `write-demo-drawing` 和 `accept-three-tables`，用于交付验收命令行闭环。
- 已新增 `tests/test_demo_acceptance.py`，覆盖 demo PNG、fake AI 三表输出验收、缺 workbook/manifest 失败和 CLI 命令。

## 真实桌面试跑与交付验收验证结果
/// 1. 首次运行 `python -m unittest tests.test_desktop_preflight tests.test_desktop_shell tests.test_qt_app_helpers -v` 失败，原因为 Windows 上 SQLite 连接释放不够明确，以及旧测试直接调用 `main()` 时被 unittest 参数污染。
/// 2. 已修复：显式关闭 SQLite 连接；`main(argv)` 改为标准显式参数解析，测试不再依赖隐式 unittest 兼容分支。
/// 3. 再次运行 `python -m unittest tests.test_desktop_preflight tests.test_desktop_shell tests.test_qt_app_helpers -v`：16 项通过。
/// 4. `python -m unittest tests.test_demo_acceptance tests.test_ai_drawing_three_table_workflow -v`：14 项通过。

## 真实桌面试跑与交付验收待手工执行
/// 1. `python -m minos_core.cli ai-config`
/// 2. `python -m minos_core.cli write-demo-drawing --output out\desktop_acceptance\safe_demo_drawing.png`
/// 3. `python -m minos_core.cli generate-three-tables --input out\desktop_acceptance\safe_demo_drawing.png --output-dir out\desktop_acceptance\cli_smoke`
/// 4. `python -m minos_core.cli accept-three-tables --result out\desktop_acceptance\cli_smoke\three_table_generation_result.json`
/// 5. `python -m minos_desktop.cli --smoke --output-dir out\desktop_acceptance\preflight --db-path out\desktop_acceptance\preflight\minos_desktop.sqlite3`
/// 6. 安装 `.[desktop]` 后运行 `minos-desktop`，人工检查空路径提示、选择图纸、运行生成、页面刷新、打开输出目录和 Excel 打开性。

## 任务 5 当前状态
工程化基础设施已补齐：项目现在包含最小 `pyproject.toml`、仓库级 `.gitignore`，并已同步 README / progress / rebuild_manifest 中的当前状态说明。

## 任务 5 已完成
- 已新增 `.gitignore`，忽略 `__pycache__/`、`*.pyc`、`.claude/settings.local.json`、虚拟环境、构建目录、测试缓存和常见临时/输出目录。
- 已新增最小 `pyproject.toml`，声明 `minos-core` 包、Python `>=3.9`、空第三方依赖、`minos-core` CLI 入口和 unittest 发现信息。
- 已更新 `README.md`，明确当前 workbook 为 7 张 sheet、测试数量不再固化、draft 入口不是正式导出。
- 已更新 `progress.md` 和 `rebuild_manifest.md`，避免继续把旧的 89 项测试或 5 sheet 说法当作当前状态。
- 未修改、未提交本地 `.claude` 配置。

## 任务 5 验证结果
/// 1. 待运行：`python -m py_compile minos_core/*.py minos_core/adapters/*.py minos_core/exporters/*.py`。
/// 2. 待运行：使用 Python 基本文本检查解析 `pyproject.toml` 必要字段；若当前 Python 提供 `tomllib`，同时做 TOML 解析。
/// 3. 待运行：检查 `.gitignore` 是否包含 `.claude/settings.local.json`、`__pycache__/` 和 `*.pyc`。

## 任务 2 当前状态
`generate-draft` CLI/API 入口已完成，用于从 Evidence/fixture 输入运行 generated pipeline 并输出 APQPChain draft JSON。该入口只生成草案结果，不等同正式导出。

## 任务 2 已完成
- 已在 `minos_core/pipeline.py` 新增 `generate_draft(evidence, output_path=None)` API。
- 已新增 draft envelope 语义：`apqp_chain_draft_result`、`draft_notice`、`draft_is_formal_export=False`、`draft`、`quality_gate`、`manual_review`、`stage_results`。
- 已在 `minos_core/cli.py` 新增 `generate-draft` 子命令，并提供 `run-pipeline` 别名。
- 已在 `minos_core/stage.py` 增加 `generate_draft` / `run_pipeline` stage 外壳入口。
- 已补 `tests/test_generated_chain_stage.py` 针对 API、保存文件、stage wrapper、CLI 子命令和别名的测试。
- 已更新 `tests/test_apqp_rebuild_contract.py` 的固定 stage 顺序契约。
- 已更新 `project_flow.mmd`，补入 assemble draft 与 generate draft 草案入口。

## 任务 2 验证结果
/// 1. `PYTHONPATH="D:/MINOS-CORE" python "D:/MINOS-CORE/tests/test_generated_chain_stage.py" -v`：6 项通过。
/// 2. `PYTHONPATH="D:/MINOS-CORE" python "D:/MINOS-CORE/tests/test_apqp_rebuild_contract.py" -v`：13 项通过。
/// 3. 旧 CLI smoke：`list`、`validate`、`audit --json` 均返回 0。
/// 4. `generate-draft` CLI smoke 返回 0，stdout 与保存 JSON 一致，`draft_is_formal_export=False`，`allow_user_export=False`，`manual_review.required=True`。
/// 5. 额外运行完整 unittest 时，`test_legacy_excel_adapter` 的 limiter export 因 export gate 阻断失败；该失败与任务 2 的 targeted 测试无关，需后续决定是补 limiter 规格字段还是调整 legacy 测试预期。

## 第十二阶段当前状态
AI analyze 增强已接入 FakeLLM 契约，默认 keyword-only 路径保持不变。

## 第十二阶段已完成
- 已新增 `analyze_evidence_bundle_with_ai(source, llm_adapter)`，先运行规则分析，再合并 LLM 结构化候选。
- 已限制 AI 输出块为 `drawings`、`characteristics`、`process_clues`、`pending_fields`、`risksAndUncertainties`。
- 已强制 AI 输出引用已有 evidence，并统一标记 `ai_inferred=True`、`needs_confirmation=True`。
- 已实现非法 JSON、未知输出块、缺失 source_ref、引用不存在 evidence 时直接失败，不做 fallback。
- 已更新 analyze gate，AI process clue 不计入“可进入 generate_pfd”的有效 Pxx route clue。
- 已新增 `tests/test_analyze_stage.py` 中 AI analyze 相关测试，覆盖 FakeLLM、非法 JSON、source_ref、AI-only route 和 keyword-only 不退化。

## 第十一阶段当前状态
PFMEA 与控制计划生成闭环已接通，未搬目录，未接入 LLM。

## 第十一阶段已完成
- 已新增 `minos_core/generate_pfmea.py`，从 `failure_mode_candidates` 生成 `pfmea` bundle，保留证据引用并用明确的工程确认占位字段。
- 已新增 `minos_core/generate_control_plan.py`，从 `pfmea` bundle 生成 `control_plan` bundle，按 AP/严重度/频度做薄规则默认控制项。
- 已更新 `minos_core/stage.py`，接入 `generate_pfmea` 和 `generate_control_plan` 阶段，保持 `validate/export` 路径不变。
- 已更新 `minos_core/quality_gates.py`，新增 PFMEA 与控制计划 bundle gate，并把上游 pending 与本阶段 blocking pending 分开。
- 已修正 brainstorm 预检语义，空 `operation` 在 brainstorm preflight 中只作为 review，真正无候选项仍由候选质量门阻断。
- 已新增 `tests/test_generate_pfmea_stage.py` 和 `tests/test_generate_control_plan_stage.py`，覆盖正常生成、证据引用、AI-only 阻断、缺证据阻断和旧链路不退化。
- 已新增 `README.md`，记录当前 pipeline、运行命令、测试命令和核心边界。
- 已更新 `project_flow.mmd`，补入 failure mode candidates、PFMEA bundle、control plan bundle 与新测试门。
- 第十一阶段完成时完整回归曾显示 114 项全部通过；当前测试数量已继续变化，不再把 114 项作为当前状态。
- 已运行 CLI smoke：`validate`、`audit`、`export` 均通过。

## 当前状态
第二阶段已开始：真实样本迁移的测试与文档已按允许范围更新。adapter 实现由另一个 worker 负责，本轮只约束公开契约并保留验收入口。

## 已完成
- 已确认当前工作树存在并行改动风险，未回退、未覆盖允许范围外文件。
- 已新增 `tests/test_legacy_excel_adapter.py`，覆盖三个真实 Excel 源：
  - 门铰链：`JLH01000300-门铰链.xlsx`
  - 冲压件：`1004258-冲压件.xlsx`
  - 限位器：`XWQ01000100-限位器.xlsx`
- 测试会对每个样本执行：`convert_legacy_workbook` 转 tempfile fixture、JSON 解析、`load_apqp_chain`、`validate_chain`、`export_fixture`、xlsx zip 结构检查和 workbook sheet 顺序检查。历史第二阶段契约当时要求 5 张 sheet；当前交付已扩展为 7 张 sheet。
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

## 第八阶段当前状态
第八阶段已完成代码落地：`ingest` 已从阶段名变成可运行入口，能把多种输入统一转成 Evidence bundle。

## 第八阶段已完成
- 新增 `minos_core/ingest.py`。
- `run_stage(..., stage="ingest")` 已支持 evidence-only 输入，不再强制构造完整 APQPChain。
- 已支持输入类型：`evidence_bundle` JSON、manual `content/text` JSON、fixture 目录、只有 `evidence.json` 的目录、OCR text、FakeOCRAdapter。
- `quality_gates.py` 已做 stage-aware 分流：`ingest/analyze` 使用轻量 Evidence 入口门；`validate/export` 继续使用三表 evidence_refs 覆盖门。
- ingest 阶段规则：至少一条可用且非 AI 推断的 Evidence 才允许进入 analyze；部分 AI 推断或待确认证据只提示不阻断；全部 AI 推断会阻断。
- 已新增 `tests/test_ingest_stage.py`，完整 unittest 已扩展到 40 项并全部通过。

## 第八阶段待验证
/// 1. 运行 CLI validate/audit/export smoke。
/// 2. 审核 git diff。
/// 3. 提交第八阶段改动。

## 第九阶段当前状态
第九阶段已完成代码落地：`analyze` 已能把 Evidence bundle 转成结构化 analysis bundle。

## 第九阶段已完成
- 新增 `minos_core/analyze.py`。
- `run_stage(..., stage="analyze")` 已支持 fixture dir、evidence bundle、manual JSON、OCR text。
- analysis bundle 输出包含：`evidence`、`drawings`、`characteristics`、`process_clues`、`pending_fields`、`ai_inferred_items`、`metadata`。
- 已实现关键词规则：drawing/revision 线索、material thickness、rivet height、push-out force、barcode、pack quantity、P10/P20/P30 工序线索等。
- 新增 `evaluate_analysis_bundle_gate`，判断 analysis bundle 是否可进入 `generate_pfd`。
- analyze 阶段 `allow_user_export=False`，只允许进入下一阶段，不允许直接导出给用户。
- 已新增 `tests/test_analyze_stage.py`，完整 unittest 已扩展到 51 项并全部通过。

## 第九阶段待验证
/// 1. 运行 CLI validate/audit/export smoke。
/// 2. 审核 git diff。
/// 3. 提交第九阶段改动。

## 第十阶段当前状态
第十阶段已完成代码落地：`generate_pfd` 已能从 analysis bundle 生成正式 `process_flow`。

## 第十阶段已完成
- 新增 `minos_core/generate_pfd.py`。
- `run_stage(..., stage="generate_pfd")` 已支持 fixture、analysis bundle、evidence bundle、manual JSON、OCR text。
- PFD 生成规则：只接收明确 `Pxx` 工序线索；无 step id 的 process clue 进入 pending，不猜编号。
- 已生成 `ProcessStep` 和 `TraceLink`，并保留 step/link 的 `evidence_refs`。
- PFD 输出不包含 PFMEA、Control Plan、failure_modes 或 controls。
- 新增 `evaluate_pfd_bundle_gate`，判断 PFD 是否可进入 `brainstorm_failure_modes`。
- AI-only 路线会阻断；OCR 待确认证据可生成 PFD，但保留人工复核提示，且不允许导出。
- 完整 unittest 已扩展到 67 项并全部通过。

## 第十阶段待验证
/// 1. 运行 CLI validate/audit/export smoke。
/// 2. 审核 git diff。
/// 3. 提交第十阶段改动。

## 第十阶段下阶段前筛查修复
进入第十一阶段前已完成一次前向筛查，并修复 PFD 到 `brainstorm_failure_modes` 的衔接风险。

## 已修复问题
- PFD gate 已校验 step/link 的 `evidence_refs` 是否存在且引用顶层 evidence。
- PFD gate 已在 missing evidence refs、AI-only evidence refs 时设置 `evidence_sufficient=False`。
- link 缺少 `evidence_refs` 或引用不存在 evidence 时会阻断。
- `process_function` / `special_characteristics` 为空只作为 review 项，不阻断进入下一阶段。
- 新增 `brainstorm_failure_modes` 前置分支：只接收 `process_flow`，复用 PFD gate，不再误走完整 APQPChain validate/export 路径。
- 完整 unittest 已扩展到 75 项并全部通过。

## 第十阶段二次前向筛查修复
- analyze gate 已收紧为至少 2 个合法 `Pxx` route clue 才允许进入 `generate_pfd`。
- analyze 已避免同一 evidence 中 Pxx 命中的 operation 再输出重复 phrase-only clue。
- `needs_confirmation` 不再被误归入 `ai_inferred_items`。
- analyze gate 已检查 `process_clues.source_ref` 是否引用顶层 evidence。
- PFD/brainstorm gate 已支持字符串形式 `pending_fields`。
- PFD/brainstorm gate 已检查 `link_type`，缺失、空值或非法值会阻断。
- brainstorm preflight 的报告语义已修正为 `stage_mode=brainstorm_failure_modes_preflight`。
- 第十阶段二次前向筛查时完整 unittest 曾扩展到 89 项并全部通过；当前测试数量已继续变化，不再把 89 项作为当前状态。

## Phase 6 pilot 当前状态
Phase 6 真实项目试运行已完成代码落地：input_package 接入 generate_draft，`review-template` 和 `apply-review` 人工复核链路已接通，`run_manifest` schema 收紧。

## Phase 6 pilot 已完成
- 新增 `tests/fixtures/real_project_input_package_template/`：脱敏真实项目 input_package 模板 fixture，包含 input_package.json、evidence.json、review_patch.json（模板态）、source_index.json。
- 新增 `tests/test_phase6_pilot_workflow.py`：覆盖 `input_package -> generate_draft -> review-template -> 人工填写 review_patch -> apply-review -> export` 完整链路。
- 新增 `minos_core/review_patch.py`：`build_review_patch_template` 从 draft envelope 生成待人工填写模板；`apply_review_patch` 应用复核 patch 并记录 confirmations。
- `review_patch_template` 必须携带 `template_status: "requires_human_review_before_apply_review"`；`apply_review_patch` 发现此字段则抛出 `ReviewPatchError`，模板不能被误当成已批准 patch。
- 在 `minos_core/cli.py` 新增 `review-template` 和 `apply-review` 子命令。
- 在 `minos_core/__init__.py` 导出 `build_review_patch_template`，原有 `brainstorm_failure_modes_from_pfd` 等导出保持不变。
- `run_manifest` 的 `inputs`/`outputs` 字段收紧为固定 object 格式（`_dump_json_object`），非 dict 值包装为 `{"value": ...}`；所有 manifest 测试通过。
- 补 `tests/test_review_patch.py` 覆盖 7 个测试场景。
- 新增 `tests/test_input_package.py` 中 real_project_template 和 realistic_input_package 回归测试。
- 完整 unittest 已扩展到 195 项并全部通过。

## Phase 6 pilot 待验证
/// 1. 运行 `python -m unittest discover -s tests -v`，确认 195 项全部通过。
/// 2. 审核 git diff，确认改动聚焦 Phase 6 pilot 链路和文档。
/// 3. 提交 Phase 6 pilot 改动。

## Phase 6 pilot 下一步
准备一个已脱敏、非客户敏感的 filled input_package 示例，跑通 `generate-draft -> review-template -> 人工填写 review_patch -> apply-review -> export` 全链路，并记录哪些字段仍需人工补齐、哪些质量门提示最影响工程人员使用。

## 真实样本闭环验收与最小修复
本阶段已完成三类真实图纸样本的后端闭环验收，并补上了桌面依赖与 preflight 健壮性修复。

## 已完成
- 修复 `load_openai_responses_config()` 的模型漂移：MINOS 不再默认继承 Codex 主模型，未显式配置时固定回落到 `gpt-5.4`，但继续复用 Codex `auth.json` 和中转 `base_url`。
- 同步修正桌面设置状态来源：`model_source` 现在只显示环境变量来源或 `default`，不再误报 `codex_config`。
- 新增 `tests/test_ai_config.py` 回归场景，锁住“Codex 代理 + Codex 鉴权 + MINOS 默认模型仍为 `gpt-5.4`”。
- 跑通第三类真实样本：`C:\Users\fgtan\Desktop\知识库种子\限位器\XWQ01000100-限位器.pdf`。
- `accept-three-tables` 已验证限位器统一工作簿和三份独立 Excel 结构正常，可打开性检查通过。
- 三类真实样本当前结果：
  - `stamping_1004258_fix1`：`needs_review`，PFD 8 步，PFMEA 8 行，CP 8 行，人工复核 122 项。
  - `hinge_JLH01000300`：`needs_review`，PFD 10 步，PFMEA 10 行，CP 10 行，人工复核 203 项。
  - `limiter_XWQ01000100`：`needs_review`，PFD 8 步，PFMEA 8 行，CP 8 行，人工复核 112 项。
- 已安装 `PySide6 6.11.0`，`python -m minos_desktop.cli --smoke --require-ai-config` 现已返回 `status=ready`。
- 已验证桌面启动路径：`python -m minos_desktop.cli` 可拉起进程且不会立即退出。
- 修复 `minos_desktop.preflight`：当 `PySide6` 已安装但当前环境导入异常时，preflight 现在返回失败检查而不是直接崩溃。
- 新增 `tests/test_desktop_preflight.py` 回归场景，覆盖“已安装但导入失败”的 `PySide6` 检查。
- 当前完整回归结果：
  - `python -m unittest discover -s tests -v`：250 项全部通过。
  - `python -m pytest tests/platform -q`：27 项全部通过。

## 本阶段遗留
- 三类真实样本都还是 `needs_review`，说明当前产物已达到工程草案级别，但距离“低复核负担”还有差距。
- 桌面 UI 进程已能启动，但这轮没有做人工点击级验收，尚未逐页确认“选择图纸 -> 运行 -> 自动刷新 -> 打开输出目录”。

## 下一步
/// 1. 用已跑通的真实样本优先压缩 `manual_review.items` 数量，先清理最明显的可自动化字段缺失。
/// 2. 增加一个桌面侧的真实运行记录回归，覆盖 `DesktopRunService` 对真实 PDF 的保存与读取。
/// 3. 做一次人工桌面点击验收，记录是否存在页面刷新、提示文本或打开输出目录的实际交互问题。

## 复核负担压缩阶段
本阶段已完成最值得先做的复核清单压缩：不放宽质量门，只减少重复和低价值噪音。

## 已完成
- 三表结果 envelope 的 `manual_review.items` 已增加统一去重：同一 `item_id`、同一字符串、以及 `PFMEA-xxx` / `failure_mode:PFMEA-xxx`、`CP-xxx` / `control_item:CP-xxx` 等同一目标不会重复展示。
- 去重时优先保留结构化复核项，再保留无法结构化的字符串项，避免丢失复核原因。
- PFD 质量门不再把普通工序 `special_characteristics=[]` 作为每步复核噪音；只有该工序自身 `needs_confirmation=True` 时才提示空特殊特性复核。
- PFD 质量门新增“顶层特殊特性未分配到工序”的聚合复核项：存在未映射的特殊特性时只提示 `process_flow.characteristics.unmapped` 一项，并在 gate report 中保留 `unmapped_special_characteristics` 明细。
- 新增/调整测试：
  - 三表端到端测试断言 `manual_review.items` 不重复，同时 `status` 仍为 `needs_review`。
  - PFD gate 测试断言普通空特殊特性不刷复核，待确认步骤仍保留复核。
  - PFD gate 测试断言未分配特殊特性只聚合提示一次，已分配特殊特性不误报。
- 使用三类既有真实结果离线重算压缩效果：
  - `stamping_1004258_fix1`：122 -> 40，减少 82 项。
  - `hinge_JLH01000300`：203 -> 70，减少 133 项。
  - `limiter_XWQ01000100`：112 -> 35，减少 77 项。
- 压缩后 `allow_user_export` 仍为 `False`，正式导出质量门没有被放宽。

## 验证
- `python -m unittest tests.test_generate_pfd_stage -v`：35 项全部通过。
- `python -m unittest discover -s tests -v`：251 项全部通过。
- `python -m pytest tests/platform -q`：27 项全部通过。

## 受阻记录
- 真实 AI 重跑限位器压缩版时，上游返回 `503 Service temporarily unavailable`：
  - 命令：`python -m minos_core.cli generate-three-tables --input "C:\Users\fgtan\Desktop\知识库种子\限位器\XWQ01000100-限位器.pdf" --output-dir out\real_run\limiter_XWQ01000100_compressed --result-output out\real_run\limiter_XWQ01000100_compressed\three_table_generation_result.json`
  - 原始错误：`generate-three-tables failed: OpenAI Responses API failed after 3 attempt(s): 503: {"error":{"message":"Service temporarily unavailable","type":"api_error"}}`
  - 判断：更像当前中转或上游服务临时不可用，不是本次压缩逻辑错误。

## AI 风险推理增强阶段
本阶段把 PFMEA/CP 从“占位式草案”推进到“AI 先推理完整工程草案”，人工复核从补空白改为审核高风险和不确定项。

## 已完成
- PFMEA 推理增强：
  - 每道 PFD 工序生成多条 PFMEA 风险，不再硬限制最多 5 条；只要求风险行有效、去重、可追溯。
  - 每条 PFMEA 行补齐失效模式、后果、原因、S/O/D/AP、预防控制、探测控制、建议措施、AI 推理理由、confidence、evidence refs。
  - 普通 AI 推理行不再全部 `needs_confirmation=True`。
  - 高严重度、AP 高、特殊特性、低 confidence 仍标记待人工确认。
- CP 生成增强：
  - 根据 PFMEA 风险反推控制计划草案。
  - 缺直接规格/测量/频次时自动生成 draft control intent 和风险控制建议，并保留 `inferred_fields`。
  - CP 行保留 `ai_inferred`、`ai_reasoning`、confidence、PFMEA 风险来源字段和 evidence refs。
- 质量门口径调整：
  - 普通行级 AI 草案保留在 `ai_inferred_items` 中，继续阻断 final export。
  - 普通行级 AI 草案不再逐条生成 manual review 噪音。
  - 高风险、特殊特性、低 confidence、证据不足或 AI 明确不确定的行仍进入人工复核。
- 已由子代理分别完成 PFMEA 与 CP/质量门子任务，主代理完成整合审核。

## 验证
- `python -m pytest tests/test_ai_drawing_three_table_workflow.py tests/test_generate_pfmea_stage.py tests/test_generate_control_plan_stage.py -q`：30 项通过。
- `python -m unittest tests.test_quality_audit tests.test_review_patch tests.test_export_modes tests.test_generated_chain_stage -v`：26 项通过。
- 首次完整回归发现人工复核后 final export 仍被 CP 行级 `ai_inferred_items` 阻断；已修复 `apply-review`，确认 PFMEA/CP 行后会同步清理对应 AI 推断标记。
- `python -m unittest tests.test_review_patch tests.test_input_package tests.test_phase6_pilot_workflow -v`：20 项通过。
- `python -m pytest tests/platform/test_apply_review.py tests/platform/test_exports.py -q`：5 项通过。
- `python -m unittest discover -s tests -v`：256 项全部通过。
- `python -m pytest tests/platform -q`：27 项全部通过。

## 三类真实样本离线重算
未重新调用真实 AI，只用已存在的三类真实结果 JSON 套用新的 PFMEA/CP 推理逻辑：
- `stamping_1004258_fix1`：PFMEA 8 -> 23，CP 8 -> 23，manual review 122 -> 49，final export 仍阻断。
- `hinge_JLH01000300`：PFMEA 10 -> 29，CP 10 -> 29，manual review 203 -> 71，final export 仍阻断。
- `limiter_XWQ01000100`：PFMEA 8 -> 21，CP 8 -> 21，manual review 112 -> 47，final export 仍阻断。

## AI 风险条数规则修正
- 已完成：去掉 `infer_pfmea_from_process_flow` 中的 5 条风险截断，保留去重但不再裁剪有效风险。
- 已完成：把三表端到端和 PFMEA 推理测试中的“最多 5 条”断言改为“同一工序 failure_mode 不重复”。
- 待验证：重新运行 AI 三表工作流测试、完整 unittest 和 platform pytest。

## Responses 流式与图纸预处理修正
- 已完成：确认 `allinai7.cloud` 的关键差异不是 URL/key，而是 Codex 请求里带了 `store:false`、`reasoning.effort=high` 和 Codex 风格 User-Agent。
- 已完成：`AIProviderConfig` 已增加 `store`、`reasoning_effort`、`user_agent`，`ai-config` 会显示这些非敏感字段。
- 已完成：`OpenAIResponsesMultimodalDrawingAnalyzer` 现在默认发送 `stream:true`，并解析 Responses SSE 事件。
- 已完成：新增 streaming parser 单测，覆盖 delta 拼接和 failed event 报错。
- 已验证：`python -m unittest tests.test_ai_config tests.test_openai_multimodal_adapter -v` 通过。

## 中文交付与复核清单聚合
- 已完成：将三表草案 warning 改为中文。
- 已完成：`manual_review.items` 改为中文分组摘要，并新增 `raw_items`、`raw_count`、`summary` 保存完整明细。
- 已完成：限位器真实结果离线重算后，用户可见复核项从 107 条合并为 5 类中文摘要，完整 107 条明细仍保留。
- 已完成：三表结果 envelope 增加 `status_display`，CLI 输出、桌面完成状态、桌面导出摘要和人工复核页默认展示中文摘要，不再把 `raw_items` 直接铺给用户。
- 已完成：统一三表工作簿导出时，“人工复核清单”可接收中文聚合摘要；质量门页保留“明细复核项数”作为内部审计指标。
- 已验证：`python -m pytest tests/test_ai_drawing_three_table_workflow.py tests/test_demo_acceptance.py tests/test_schemas.py -q` 通过。

## 人机协同三表编辑器第一版
- 已完成：新增 `edit_patch` core 能力，支持三表行 add/update/soft_delete/confirm。
- 已完成：编辑后的正式导出增加逐行确认门禁；未软删除行未确认时阻断 final export。
- 已完成：软删除行继续保留在结果 JSON 和 edit_history 中，但导出工作簿时过滤。
- 已完成：桌面 PFD/PFMEA/CP 页面改为 QTableWidget，可添加行、软删除、确认行并保存为 edit_patch。
- 已完成：桌面服务层保存 original/current/edit_patch，支持回读运行记录后继续编辑。
- 已完成：桌面导出页增加草案/正式导出入口，并展示质量门结果。
- 已完成：桌面 PFD 表格补齐工序目的/过程功能、产品特性、过程特性、设备、工装、检具、文件、流程类型、证据、待确认等关键列。
- 已完成：桌面 PFMEA 表格显示继承自 PFD 的工序名称、过程功能、产品/过程特性，方便逐行审核风险来源。
- 已完成：桌面 CP 表格显示 PFMEA 来源、失效模式、特性、规格、测量方法、频次、反应计划、检具等控制字段。
- 已完成：未发生新增、修改、软删除或确认时，保存按钮提示“无需保存”，不提交空 `edit_patch`。
- 已验证：`python -m pytest tests/test_edit_patch.py tests/test_desktop_table_editor.py tests/test_desktop_shell.py tests/test_qt_app_helpers.py tests/test_schemas.py -q` 通过。

## Core 三表联动实现
- 已完成：`ProcessStep` 增加工序目的、产品特性、过程特性、设备、工装、检具、文件、流程类型等字段，并兼容旧 fixture。
- 已完成：PFD 生成保留上述字段；图纸推理 PFD 也同步传递这些字段。
- 已完成：PFMEA 从 PFD/候选包继承工序编号、名称、功能、产品/过程/特殊特性，并丢弃不属于 PFD 的孤儿候选。
- 已完成：CP 生成保留 `source_pfmea_id`、PFMEA 失效原因、预防/探测控制、特殊特性和高风险来源。
- 已完成：质量门/validate 增加三表一致性检查，覆盖 PFD 工序无 PFMEA 风险、高风险 PFMEA 无有效 CP、特殊特性未贯穿、CP 工序不在 PFD、检具/频率/反应计划缺失。
- 已验证：`python -m unittest tests.test_generate_pfd_stage tests.test_generate_pfmea_stage tests.test_generate_control_plan_stage tests.test_stage_result -v`：68 项通过。

## MINOS-CORE v1.5 AIAG-VDA PFMEA 专业化增强
- 已完成：新增 `aiag_vda_pfmea`，支持 AIAG-VDA PFMEA 字段归一化、AP 计算和 RPN 辅助计算。
- 已完成：PFMEA 生成链路输出 AIAG-VDA 风格字段，包括过程项、过程步骤、过程工作要素、功能/要求、推荐措施、责任人、目标日期、措施状态、措施后 S/O/D/AP 等。
- 已完成：新增 `action_closure`，检查高 AP 推荐措施、中高 AP 责任人/目标日期、逾期状态和措施后评价完整性。
- 已完成：新增 `change_management`，支持字段级 diff、PFD/PFMEA/CP 变更影响分析和未处理影响阻断。
- 已完成：新增 `knowledge_recommendation`，提供轻量本地知识库规则推荐；推荐项必须人工采纳或填写忽略原因，不能自动成为正式结论。
- 已完成：扩展 `edit_patch`，支持 `accept_recommendation`、`ignore_recommendation`、`resolve_change_impact`，并记录字段级 before/after 审计历史。
- 已完成：扩展质量门，v1.5 正式导出会检查 AP 措施闭环、变更影响和知识库推荐处理。
- 已完成：拆分严格门范围，`strict_three_table_linkage` 只管三表一致性，`strict_aiag_vda_pfmea_gate` 才启用 v1.5 专业严格门，避免旧 fixture 和 legacy 导出被误伤。
- 已完成：桌面 PFMEA 表格和三表 Excel 导出补齐 AIAG-VDA 关键字段，表头和用户可见说明保持中文。
- 已完成：知识库推荐在用户可见 `manual_review.items` 中归并到 PFMEA 复核摘要，完整明细仍保留在 `raw_items`。
- 已验证：`python -m pytest tests/test_aiag_vda_v15.py tests/test_desktop_table_editor.py tests/test_edit_patch.py -q`：19 项通过。
- 已验证：`python -m pytest tests/test_ai_drawing_three_table_workflow.py tests/test_generate_pfmea_stage.py tests/test_generate_control_plan_stage.py tests/test_desktop_table_editor.py -q`：42 项通过。
- 已验证：`python -m pytest tests/test_aiag_vda_v15.py tests/test_edit_patch.py tests/test_quality_audit.py tests/test_review_patch.py tests/test_stage_result.py tests/test_apqp_rebuild_contract.py tests/test_export_modes.py tests/test_legacy_excel_adapter.py -q`：60 项和 7 个 subtests 通过。
- 已验证：`python -m unittest discover -s tests -v`：290 项全部通过。

## MINOS v1.6 桌面专业闭环
- 已完成：桌面导航新增“措施管理”“变更影响”“知识库推荐”三个中文页面。
- 已完成：PFMEA 页面新增筛选入口，覆盖 AP 高、AP 中、逾期、待措施、待措施后评价、待确认、知识库推荐待处理和变更影响待处理。
- 已完成：`table_editor` 增加 UI-neutral helper，可把三表结果转换为措施管理行、变更影响列表和知识库推荐列表，并生成推荐/变更处理 patch item。
- 已完成：桌面 SQLite 增加 `knowledge_rules` 表，自动写入默认知识库规则，支持查看、新增、停用和从推荐沉淀本地规则。
- 已完成：桌面服务层新增 `handle_recommendation` 和 `resolve_change_impact`，推荐采纳/忽略、变更处理/忽略都统一走 `edit_patch`。
- 已完成：修正桌面运行记录的累计 patch 保存和回读，关闭后重新加载仍能拿到完整 edit_patch。
- 已完成：Qt 知识库推荐页支持采纳、忽略、沉淀为知识库；变更影响页支持标记已处理和忽略，忽略时要求填写原因。
- 已验证：`python -m pytest tests/test_desktop_table_editor.py tests/test_desktop_shell.py tests/test_edit_patch.py tests/test_aiag_vda_v15.py -q`：33 项通过。
- 已验证：`python -m pytest tests/test_ai_drawing_three_table_workflow.py tests/test_generate_pfmea_stage.py tests/test_generate_control_plan_stage.py tests/test_qt_app_helpers.py tests/test_export_modes.py tests/test_legacy_excel_adapter.py -q`：44 项和 3 个 subtests 通过。
- 已验证：`python -m unittest discover -s tests -v`：294 项全部通过。
- 已验证：`python -m minos_desktop.cli --smoke --output-dir out\desktop_acceptance\preflight --db-path out\desktop_acceptance\preflight\minos_desktop.sqlite3`：`status=ready`。

## MINOS v1.7 导出与验收实现
- 已完成：聚焦 `minos_core/exporters/*`、`edit_patch` 导出入口和导出/acceptance 测试，不改桌面 UI。
- 已完成：APQP/PFMEA 导出列顺序按 AIAG-VDA 审核顺序打磨，三表拆分导出增加草案首行显眼标记。
- 已完成：正式统一工作簿新增“正式导出审计”页，汇总质量门、人工确认、manual_review、edit_patch 历史和软删除摘要。
- 已完成：编辑后正式导出会把软删除摘要写入导出链路 metadata，表格行继续过滤软删除项，审计页保留摘要。
- 已完成：补充 final export 阻断、正式审计页内容、草案标记和 xlsx zip 可打开测试。
- 已验证：`python -m pytest tests/test_export_modes.py tests/test_edit_patch.py tests/test_ai_drawing_three_table_workflow.py tests/test_demo_acceptance.py tests/test_apqp_rebuild_contract.py -q`：45 项通过。
- 已验证：`python -m pytest tests/test_legacy_excel_adapter.py -q`：1 项和 3 个 subtests 通过。
- 已验证：`python -m pytest tests/test_export_modes.py tests/test_demo_acceptance.py -q`：9 项通过。
