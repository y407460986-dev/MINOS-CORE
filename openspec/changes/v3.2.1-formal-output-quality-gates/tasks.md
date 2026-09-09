# Tasks: V3.2.1 Formal Output Quality Gates

## Define

- [x] /// 1. 意图：固定防复发目标。输入：JLV 输出审核结果。输出：坏夹具缺陷清单。验证：每个缺陷都有对应测试断言。

## Specify

- [x] /// 2. 意图：明确正式导出阻断边界。输入：重复 CP ID、PFMEA 覆盖缺口、drawing risk、泛化 CP、空导出表。输出：质量门规则。验证：坏夹具 `allow_formal_release=false`。

## Implement

- [x] /// 3. 意图：按 TDD 实现结构质量门。输入：audit/export gate 红灯测试。输出：blocker 审计项进入正式质量门。验证：聚焦测试通过。
- [x] /// 4. 意图：按 TDD 实现 CP ID 确定性归一化。输入：模型重复 ID。输出：唯一 CP ID。验证：链式和规则 CP 测试通过。
- [x] /// 5. 意图：按 TDD 实现 drawing risk 投影。输入：`D00R HIMGE` 和盐雾 240h 漏项。输出：人工复核和正式阻断。验证：drawing gate 测试通过。
- [x] /// 6. 意图：按 TDD 实现导出表完整性。输入：缺追溯矩阵和人工复核项。输出：可读 worksheet 行。验证：OpenXML 和 workbook 测试通过。

## Verify

- [x] /// 7. 意图：完整回归。输入：聚焦 pytest、JLV fixture、workbook 导出、文档。输出：全部通过记录。验证：`git diff --check`、UTF-8 读取、OpenXML 检查通过。
