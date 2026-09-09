# Proposal: V3.2.1 Formal Output Quality Gates

## Why

JLV 真实图纸复测证明，正式导出允许不等于内容可信。当前系统可能在 CP ID 重复、PFMEA 未完全被 CP 覆盖、图纸身份疑似 OCR 误读、盐雾红锈要求漏提、人工复核清单和追溯矩阵空表时仍生成看似完整的正式 xlsx。

这类问题不能靠事后修改报告解决，必须变成 MINOS-CORE 的正式输出防线。

## What

- 正式导出质量门增加结构阻断项。
- CP ID 在生成归一化阶段确定性唯一。
- 图纸识别疑点和盐雾技术要求漏项进入人工复核并阻断正式放行。
- 导出工作簿必须包含可读追溯矩阵和人工复核清单。
- 用小夹具复现 JLV 缺陷，不依赖真实 PDF、OCR 或 AI。

## Non-goals

- 不修改当前已导出的 JLV 报告。
- 不把所有 warning 都改成阻断。
- 不重写三表生成主流程。
- 不引入新的质量门框架。

## Acceptance

- 坏 JLV fixture 正式导出被阻断。
- 修正 JLV fixture 正式导出允许。
- 追溯矩阵和人工复核清单不再只有表头。
- 聚焦 pytest、OpenXML 可打开性和 diff 检查通过。
