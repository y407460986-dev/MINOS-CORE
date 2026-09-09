# GPT5.5 特殊特性 AI 裁判设计

## Define

GPT5.5 是特殊特性裁判，不是原始视觉传感器。它只能消费由 Mimo、OCR/PDF 和客户规则构成的 evidence packet。

## Specify

新链路分四层：

1. Sensor layer：Mimo/OCR/PDF 只生成证据。
2. Evidence packet layer：MINOS 统一证据结构和 page/candidate/legend 引用。
3. Judge layer：GPT5.5 输出 `special_characteristic_judgments`。
4. Gate layer：verifier、registry、drawing gate、final export gate 决定能否进入正式三表。

判决必须包含：

- `classification`: `SC`、`CC` 或 `unknown`。
- `verdict`: `confirmed`、`rejected` 或 `needs_human_review`。
- `standard_evidence_refs`: 图例、OCR 文本或客户规则证据。
- `symbol_evidence_refs`: Mimo/OCR 候选证据。
- `page_evidence_refs`: drawing page 证据。
- `reasoning_summary`: 面向用户的中文摘要。

没有标准证据或符号证据时，不允许 `confirmed`。

## Implement

/// 1. Evidence packet builder。
/// 2. GPT5.5 judge adapter wrapper。
/// 3. Judge verdict normalizer and verifier。
/// 4. Candidate confirmation boundary refactor。
/// 5. Hybrid pipeline judge integration。
/// 6. Registry and gate update。
/// 7. Workbench display update。

## Verify

/// 1. fake evidence packet 单测。
/// 2. fake judge confirmed verdict 单测。
/// 3. hallucinated evidence verdict 单测。
/// 4. numeric-only regression。
/// 5. registry propagation regression。
/// 6. final export gate regression。
/// 7. UI static display regression。
