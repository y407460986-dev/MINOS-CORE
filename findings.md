# MINOS-CORE 重建发现

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

## 当前限制
- 本轮没有实现核心代码，也没有实现 exporter。
- 当前测试是契约测试；如果核心实现尚未落地，运行测试会暴露 import 或 CLI 入口缺失。
- 没有删除任何文件，也没有改动允许范围外文件。
