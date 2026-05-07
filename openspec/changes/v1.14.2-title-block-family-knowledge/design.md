# Design: V1.14.2 Title Block Family Knowledge

## Design Principle
零件族识别的第一性问题是“图框说这张图是什么”。结构词、组件词和制造线索有价值，但它们只能辅助判断，不能压过标题栏。V1.14.2 因此采用“标题栏强证据 + 全图辅助证据 + 组件词降权”的规则。

## Title Block Priority
分类器给不同字段赋予不同证据权重：
- `drawing_identity.part_name`、`drawing_identity.title` 是主证据。
- `metadata.ocr_analysis_summary.drawing_identity` 是 hybrid 模式下的补充主证据。
- OCR evidence 的 `content` 是辅助证据，若来自标题栏提取结果则通过 `drawing_identity` 提升。
- 技术要求、检验要求、制造线索、材料和路径类字段权重低于图框。

分类结果仍输出 `matched_evidence`，但每条 evidence 记录字段路径和加权得分，便于用户看到系统到底命中了图框还是命中了局部组件。

## OCR Unlabeled Title Line
很多图框不会写标准 `Part Name:` 标签，OCR 可能只读到一行类似：

```text
JLV03000500BACKX D00R HIMGE 尾门较链
```

V1.14.2 在标签提取失败后执行保守候选提取：
- 候选行必须包含已知零件族词，如 `铰链/较链/hinge/限位器/limiter/冲压件/stamping`。
- 如果有图号，先从行中去掉图号。
- 跳过明显技术要求或备注行，例如包含“不可、不得、毛刺、检验、材料、尺寸”等。
- 保留候选行的 OCR block evidence ref，并标记为 OCR 推断、需要确认。

## Family Knowledge Signals
内置族识别词覆盖三类线索：
- 门铰链：尾门/背门/车门铰链、DH ASSY、hinge assembly、hinge pin、转轴、铰链臂、开闭角度、转动力矩、润滑等。
- 限位器：door check、check strap、check arm、限位臂、限位杆、档位力、保持力、detent、roller、spring、stopper 等。
- 冲压件：冲压件、钣金件、sheet metal、stamped bracket、blanking、piercing、flanging、embossing、加强筋、翻边、安装孔、SPCC/DC01 等。

`衬套/bushing/轴套` 作为门铰链组件线索保留，但权重降低，避免单独命中。

## AI Prompt Boundary
视觉模型提示要求先读标题栏，并明确：
- `drawing_identity.part_name` 必须优先来自标题栏/图框。
- 组件名、局部标注、BOM 行和技术要求不能覆盖整张图纸零件名。
- 当标题栏写尾门铰链但技术要求提到衬套时，零件名仍应是尾门铰链，衬套应进入组件/特性/工艺线索。

## Hybrid Identity Lock
Hybrid 的职责分层为：
- OCR/标题栏负责锁定整件身份：图号、零件名、版本和零件族。
- 视觉模型负责补充结构、尺寸关系、局部组件、制造特征和复核提示。
- 当 OCR `drawing_identity` 置信度达到锁定阈值时，视觉结果不能覆盖 `drawing_identity.part_name` 等整件身份字段。
- 当 OCR 零件族分类达到自动接受阈值时，后续 PFD/PFMEA/CP 使用该零件族上下文；视觉命中的“衬套”等局部词只作为组件/工艺线索。

实现上，hybrid 视觉成功后仍保留视觉分析结果，但会把 OCR 标题栏身份写回最终 `drawing_identity`，合并 OCR evidence，并在 `metadata.ocr_identity_lock` 中记录原始视觉身份、锁定字段、OCR 身份和锁定零件族，方便人工复核。

## Verify
- 单元测试验证标题栏强证据压过组件词。
- 单元测试验证单独衬套不会变成门铰链。
- OCR 测试验证无标签图框能抽取门铰链零件名并保留证据。
- 知识库加载测试确认新增族相关规则可被加载。
- Hybrid 测试验证视觉把整件名误写成“衬套”时，高置信 OCR 标题栏仍锁定“尾门较链”和 `door_hinge`。
