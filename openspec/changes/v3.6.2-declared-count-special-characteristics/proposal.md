# 声明数量驱动的 CC/SC 识别

## Why

真实 JLV 图纸在标题栏/产品特殊特性表中声明了关键特性 CC 数量和重要特性 SC 数量，但当前 Mimo 开放式视觉识别可能返回 0 个候选，导致 GPT5.5 没有可裁判对象，最终桌面版仍显示没有 SC/CC。

## What

- 从 MinerU/OCR 文字和表格中抽取 `declared_special_characteristics`。
- 将声明数量放入 Mimo 上下文，要求 Mimo 按 `CC expected_count` 和 `SC expected_count` 定向定位。
- 新增 `special_characteristic_locations` 保存 Mimo 定位结果。
- evidence packet 增加声明、定位、缺失数量和覆盖范围。
- GPT5.5 裁判必须同时核对声明数量、视觉位置和证据引用。
- 声明数量大于 0 但定位或确认数量为 0 时，必须进入 drawing/final export gate。

## Non-Goals

- 不把 PTC 作为正式图纸特殊特性类型。
- 不让 GPT5.5 绕过证据包直接自由重读整张图。
- 不在本变更中做人工框选训练界面。
- 不改变已经确认的 registry 继承边界。

## Acceptance

- OCR 文本包含 `关键特性 CC ... 2` 和 `重要特性 SC ... 1` 时，系统输出 `declared_totals={"CC":2,"SC":1}`。
- Mimo prompt 收到声明数量后必须包含“找到 2 个 CC 和 1 个 SC”的定向要求。
- fake Mimo 返回 2 个 CC、1 个 SC 位置时，GPT5.5 fake verdict 能确认 3 个正式特殊特性。
- fake Mimo 返回 0 个位置时，结果不能静默通过，必须生成数量缺失风险。
- JLV 种子图纸验收时，至少能在结果中看到声明数量 `CC=2, SC=1`；若定位未完成，工作台和 gate 必须明确显示缺失数量。
