# OCR 数值指标特殊特性边界设计

## Define

本次修复的目标不是判断盐雾要求是否重要，而是明确“重要技术指标”和“特殊特性标识”是两类数据。前者可以影响工艺和控制计划内容，后者才允许驱动 SC/CC 标注。

## Specify

OCR fallback 输出分三层：

1. `numeric_specifications`：阈值、单位和来源文本，例如 `不低于120h`。
2. `special_characteristics`：只有明确标识或关键词，例如 `SC`、`CC`、`PTC`、`特殊特性`、`关键特性`。
3. `technical_requirements` / `surface_treatments`：其他技术要求和表面处理线索。

PFD 可以读取 `numeric_specifications` 作为技术指标，但如果图纸没有明确特殊特性标识，`product_characteristic_class` 和 `process_characteristic_class` 应保持 `无`。

## Implement

最小实现点在 `minos_core/drawing_ocr_analysis.py`：

/// 1. 保留 `_numeric_specification_items()` 对数值阈值的抽取。
/// 2. 删除数值阈值生成 `OCR-NS-*` 特殊特性候选的逻辑。
/// 3. 让 `build_drawing_analysis_bundle_from_ocr()` 不再把 numeric spec 合并到 `special_characteristics`。
/// 4. 保持 `_special_characteristic_items()` 的显式标识识别不变。

## Verify

/// 1. 红灯：数值盐雾要求当前会出现在 `special_characteristics`。
/// 2. 绿灯：修复后同一文本只进入 `numeric_specifications`。
/// 3. 回归：明确 `SC` 文本仍进入 `special_characteristics`。
/// 4. 聚焦验证：运行 `python -m pytest tests/test_drawing_ocr_analysis.py -q`。
