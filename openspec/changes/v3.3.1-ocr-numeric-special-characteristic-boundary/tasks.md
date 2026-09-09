# Tasks

- [x] /// 1. 意图：复现 #1 特殊特性误识别。输入：`out/open-test/ui-run-latest/three_table_generation_result.json`。输出：确认 `不低于120h` 被写入 `special_characteristics` 并放大成 P07/P08 的 SC。验证：JSON 摘要显示 PFD/PFMEA/CP 均继承 SC。
- [x] /// 2. 意图：写红灯测试。输入：普通盐雾阈值 OCR 文本。输出：断言数值要求不进入 `special_characteristics`。验证：修复前测试失败，显示 `OCR-NS-001`。
- [x] /// 3. 意图：保留显式特殊特性识别。输入：`SC 孔径 10.0 +/- 0.1 mm`。输出：仍识别为 `classification=SC`。验证：同一测试文件覆盖。
- [x] /// 4. 意图：最小修复 OCR 抽取边界。输入：`minos_core/drawing_ocr_analysis.py`。输出：`_numeric_specification_items()` 只返回数值指标。验证：数值要求不再生成 `OCR-NS-*`。
- [x] /// 5. 意图：交付前验证。输入：聚焦测试、OpenSpec 文档、根流程记录。输出：测试通过、UTF-8 可读、diff 无空白错误。验证：记录命令结果。
