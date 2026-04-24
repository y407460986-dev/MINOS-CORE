# MINOS-CORE 重建交付清单

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

覆盖内容：
- domain loader 读取完整 APQP fixture。
- validation 接受完整链路。
- validation 拒绝 mandatory PFMEA 缺少 CP 覆盖。
- xlsx writer sheet 名清洗、截断、去重。
- xlsx zip 结构完整性。
- APQP workbook 固定 5 张 sheet。
- CLI `list` / `validate` / `export`。

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

## 注意
如果核心代码尚未提供 `minos_core.domain`、`minos_core.validation`、`minos_core.exporters`、`minos_core.cli`，完整测试会失败。这不是 fixture/测试任务的绕行点，而是重建契约尚未被实现的明确信号。
