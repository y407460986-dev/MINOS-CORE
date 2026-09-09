# v3.8.0 删除 Mimo，改用 GPT5.5 + MinerU 识别特殊特性

## Why

真实 JLV 图纸验证显示，Mimo 在 CC/SC 识别上不适合作为正式视觉证人：

- Mimo 把第 6 条误判为 SC。
- Mimo 漏掉第 4 条第(2)项 `转动力矩(0.5~2.5)Nm` 的 SC 胶囊标记。
- Mimo 返回的 bbox 与渲染图坐标存在偏移，不能直接作为可追溯定位证据。

GPT5.5 对图纸视觉理解更好，但整页一次性识别仍可能漏掉小符号。因此 v3.8.0 要删除 Mimo 组件，改成 MinerU/OCR 提供文本和声明数量，GPT5.5 负责视觉定位、缺失项聚焦复核和证据约束裁判。

## What

- 删除 Mimo provider、配置读取、Chat Completions adapter、Mimo prompt 和 Mimo 专用测试。
- 保留 OpenAI Responses 图像输入能力，并将其作为唯一图纸视觉模型通道。
- 新增 GPT5.5 特殊特性视觉定位器，输入整页图、标题栏/图例/技术要求裁剪和 OCR 摘要。
- 新增图纸视觉证据裁剪模块，固定生成整页、标题栏、图例、技术要求和尺寸/GD&T 区域。
- 用 `declared_totals` 驱动数量闭环：声明有 `CC=2, SC=1` 时必须确认 2 个 CC 和 1 个 SC，否则进入聚焦复核或人工复核风险。
- 将 JLV 图纸回归固定为：SC 在第 4 条第(2)项 `转动力矩(0.5~2.5)Nm`，CC 在第 5 条和第 6 条。
- 将产品版本同步到 `3.8.0`。

## Non-Goals

- 不保留 Mimo fallback。
- 不新增人工框选 UI。
- 不替换 MinerU。
- 不把 GPT5.5 视觉候选直接写入正式 `special_characteristics`，仍需 evidence judge 或人工确认。
- 不改动三表继承边界。

## Acceptance

- 设置 `MINOS_VISION_PROVIDER=mimo` 不再启用 Mimo，系统仍使用 OpenAI Responses/GPT5.5 图像通道。
- 代码中不存在 `MimoV25ChatCompletionsDrawingAnalyzer`、`_mimo_v25_drawing_analysis_prompt`、`MINOS_MIMO_*` 运行配置分支。
- fake GPT5.5 locator 能输出 JLV 的 `SC-REQ4-TORQUE`、`CC-REQ5-GB15086`、`CC-REQ6-M0102`。
- `declared_totals={"CC":2,"SC":1}` 时，确认数不足会触发聚焦复核或数量风险。
- JLV 真实图纸验收输出 2 个 CC 和 1 个 SC，且 SC linked feature 包含 `转动力矩(0.5~2.5)Nm`。
- `tests/test_release_version_sync.py` 通过并确认版本为 `3.8.0`。
