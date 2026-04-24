# MINOS-CORE 重建交付清单

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
