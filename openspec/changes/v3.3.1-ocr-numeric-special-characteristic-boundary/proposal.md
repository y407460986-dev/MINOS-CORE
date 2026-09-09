# OCR 数值指标不自动升级特殊特性

## Why

当前生成的 #1 结果中，OCR fallback 把“红锈出现时间不低于120h”识别成 `special_characteristics` 下的 PTC 候选。PFD 生成阶段随后把 `special_characteristics` 当作 SC/CC 重点线索，导致镀锌处理和镀层检验被放大为 SC 工序，PFMEA 和控制计划继续继承这个错误分类。

特殊特性必须来自图纸明确标识、客户要求或人工确认，单纯数值性能要求只能作为技术指标或检验指标，不能自动升级为 SC/CC/PTC。

## What

- OCR 抽取层保留数值阈值到 `numeric_specifications`。
- OCR 抽取层不再把数值阈值额外写入 `special_characteristics`。
- 明确出现 `SC`、`CC`、`PTC`、特殊特性、关键特性等标识的文本仍进入 `special_characteristics`。
- 增加回归测试，覆盖“普通盐雾阈值不是特殊特性”和“明确 SC 标识仍保留”。

## Non-Goals

- 不重写 PFD/PFMEA/CP 的提示词。
- 不改历史已生成的 JSON 或 Excel。
- 不改变显式 SC/CC/PTC 标识的识别入口。

## Acceptance

- `tests/test_drawing_ocr_analysis.py` 中数值要求用例先红后绿。
- `按GB/T10125...不低于120h` 只出现在 `numeric_specifications`，不出现在 `special_characteristics`。
- `SC 孔径 10.0 +/- 0.1 mm` 仍被识别为特殊特性，分类为 `SC`。
