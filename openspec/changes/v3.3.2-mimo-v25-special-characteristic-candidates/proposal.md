# Mimo V2.5 特殊特性候选识别

## Why

MINOS 当前 OCR-first 能避免一部分标题栏和技术要求误读，但对图纸中的客户符号、局部符号、图例和符号-尺寸绑定仍然不稳定。单靠 OCR 不能保证 CC/SC 召回；单靠视觉模型又可能把数值要求误判为特殊特性。

## What

- 增加 `mimo-v2.5` 作为图纸视觉候选识别 provider，调用方式为小米官方 OpenAI-compatible Chat Completions：`POST https://api.xiaomimimo.com/v1/chat/completions`。
- 新增 `special_characteristic_candidates` 顶层字段，保存 SC/CC/PTC/unknown 候选和证据区域。
- OCR 明确 SC/CC 文本和 mimo 视觉符号统一进入候选融合。
- 只有已确认候选进入正式 `special_characteristics` 和 `characteristic_registry`。
- 未确认候选进入 drawing gate、chain metadata 和 final export gate。

## Non-Goals

- 不把数值阈值自动升级为特殊特性。
- 不要求第一版 UI 支持在线框选确认。
- 不改变已生成历史文件。

## Acceptance

- 配置 `MINOS_VISION_PROVIDER=mimo` 且 `MINOS_MIMO_MODEL=mimo-v2.5` 时，默认 hybrid 图纸识别使用 mimo analyzer。
- fake mimo response 中的视觉符号候选被规范化并保留 bbox/evidence。
- 普通数值要求不会进入 `special_characteristics`。
- 未确认候选不会传给 PFD/PFMEA/CP 的 `special_characteristics`。
- 未确认候选会阻断正式导出，但不阻断草案继续生成。
