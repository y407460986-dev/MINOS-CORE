# GPT5.5 特殊特性 AI 裁判重构

## Why

当前 Mimo 能看到视觉候选，但系统仍缺少一个真正综合图例、符号、OCR 文本和客户规则的 AI 裁判层。仅靠候选规则确认会把“看见符号”和“判定 SC/CC”混在一起，导致星形、三角形、菱形等客户符号无法稳定解析，或在证据不足时被误放行。

## What

- 新增 `special_characteristic_evidence_packet`，作为 GPT5.5 裁判输入。
- 新增 `special_characteristic_judgments`，保存 GPT5.5 对每个候选的 SC/CC/不确定判决。
- Mimo/OCR 候选不再直接成为正式 `special_characteristics`。
- 只有 `judge_confirmed` 或 `human_confirmed` 的 SC/CC 能进入 `characteristic_registry`。
- 未判定、证据不足或 verifier 质疑的项进入 drawing gate 和 final export gate。

## Non-Goals

- 不让 GPT5.5 直接绕过证据包读取整张图后自由输出三表。
- 不在第一版实现复杂 UI 框选训练。
- 不重新引入 PTC 作为图纸正式特殊特性类型。

## Acceptance

- fake Mimo 候选必须先进入 evidence packet，不能直接进入 registry。
- fake GPT5.5 verdict 引用完整证据时，SC/CC 可以进入 registry 和三表。
- fake GPT5.5 verdict 引用不存在证据时，必须进入人工复核且不能进入 registry。
- 普通数值技术要求不能被 GPT5.5 verdict 单独升级为 SC/CC。
- final export gate 阻断未复核或证据不完整的 AI verdict。
