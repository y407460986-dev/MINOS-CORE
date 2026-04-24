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
