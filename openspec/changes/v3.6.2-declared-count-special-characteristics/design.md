# 声明数量驱动的 CC/SC 识别设计

## Define

图纸中声明的特殊特性数量是硬约束，不是提示词里的背景信息。系统必须先识别声明数量，再要求视觉模型按数量找具体位置。

## Specify

新字段：

- `declared_special_characteristics`: OCR/MinerU 抽取出的声明行。
- `declared_totals`: 按分类汇总的声明数量，例如 `{"CC": 2, "SC": 1}`。
- `special_characteristic_locations`: Mimo 按声明数量找到的位置。
- `special_characteristic_discovery`: 覆盖率、缺失数量和数量不一致风险。

确认规则：

1. 没有声明数量时，Mimo 找到的 CC/SC 只能作为候选，仍需 GPT5.5 或人工确认。
2. 有声明数量时，Mimo 必须尝试找到精确数量。
3. 找到数量少于声明数量时，不能正式放行。
4. 找到数量多于声明数量时，多出的只作为候选，不能直接进入 registry。
5. GPT5.5 confirmed 必须引用声明证据、视觉定位证据和页面证据。

## Implement

/// 1. 新增声明数量抽取模块。
/// 2. OCR bundle 挂载声明数量。
/// 3. Mimo prompt 接收声明数量并输出定位结果。
/// 4. 新增 discovery normalizer 和数量风险。
/// 5. evidence packet v2 合并声明和定位。
/// 6. GPT5.5 verifier 增加数量一致性检查。
/// 7. hybrid/fallback/gate/UI 接入。

## Verify

/// 1. OCR 声明数量单测。
/// 2. Mimo prompt 定向查找单测。
/// 3. fake Mimo 定位数量单测。
/// 4. fake GPT5.5 裁判数量一致性单测。
/// 5. hybrid fallback 仍保留声明数量单测。
/// 6. final export gate 阻断缺失数量单测。
/// 7. JLV 真实图纸浏览器验收。
