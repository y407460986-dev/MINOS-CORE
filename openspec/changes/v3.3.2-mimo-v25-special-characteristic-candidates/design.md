# Mimo V2.5 特殊特性候选设计

## Define

特殊特性识别分两层：候选识别和正式确认。mimo-v2.5 只负责候选识别，不负责最终放行。

## Specify

官方 API 边界：

1. `base_url=https://api.xiaomimimo.com/v1`。
2. `endpoint=chat/completions`。
3. 鉴权头优先使用 quick start 中的 `api-key`。
4. 图片通过 `messages[0].content[]` 的 `image_url.url` 传入，可使用本地渲染页转成的 base64 data URL。

候选 schema：

```json
{
  "candidate_id": "MSC-001",
  "candidate_type": "SC",
  "source": "visual_symbol",
  "symbol_text_or_shape": "SC",
  "linked_feature": "孔径 10.0 +0.05/0 mm",
  "symbol_bbox": [0.12, 0.20, 0.04, 0.03],
  "linked_feature_bbox": [0.18, 0.20, 0.18, 0.05],
  "evidence_refs": ["drawing_page_001"],
  "evidence_regions": [
    {
      "evidence_ref": "drawing_page_001",
      "bbox": [0.12, 0.20, 0.04, 0.03],
      "text": "SC",
      "confidence": 0.91
    }
  ],
  "confidence": 0.91,
  "needs_confirmation": false,
  "confirmation_status": "rule_confirmed",
  "reasoning": "图纸上明确 SC 标识绑定到孔径尺寸。"
}
```

确认规则：

1. `candidate_type` 必须是 `SC` 或 `CC`。
2. `source` 必须是 `visual_symbol`、`legend` 或 `ocr_text`。
3. 必须有 `evidence_refs`。
4. 必须有非零 `symbol_bbox` 或明确 OCR 文本证据。
5. 必须有 `linked_feature`。
6. `confidence >= 0.85` 时可 `rule_confirmed`；否则 `needs_confirmation=true`。
7. `source=knowledge` 只能生成候选，不能自动确认。
8. 没有明确图纸符号、图例或 SC/CC 文本时，数值要求不能成为特殊特性候选。

## Implement

/// 1. 配置层增加 vision provider。
/// 2. adapter 层增加 mimo prompt 和 analyzer factory。
/// 3. drawing analysis 层规范化候选 schema。
/// 4. fusion 层合并 OCR 明确文本候选和 mimo 视觉候选。
/// 5. registry 层只注册已确认 SC/CC。
/// 6. orchestration 层清理未确认下游引用。
/// 7. gate 层把未确认候选投影为正式导出阻断。

## Verify

/// 1. fake mimo response 单测。
/// 2. numeric-only 回归。
/// 3. explicit SC/CC 文本回归。
/// 4. unknown visual symbol 进入人工复核。
/// 5. unconfirmed candidate 不下游继承。
/// 6. final export 被未确认候选阻断。
