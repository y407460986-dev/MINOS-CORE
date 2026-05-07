# Proposal: V1.14.2 Title Block Family Knowledge

## Why
V1.14.1 已经让 OCR-first / hybrid 图纸入口可以稳定产出 `drawing_analysis`，但零件族识别仍把整份图纸文本一起打分。这样会放大技术要求、子件说明、路径名或历史知识中的局部词，例如“衬套”，导致用户看到“图框写的是尾门铰链，系统却像命中了衬套”。

V1.14.2 的目标是把图框/标题栏里的零件名作为零件族识别的主证据，并补强门铰链、限位器、冲压件的结构和视觉线索。零件族识别应先回答“这张图纸整体是什么件”，再把衬套、销轴、滚轮、弹簧、翻边、孔位等作为零部件或特性线索进入后续 PFD/PFMEA/CP。

## What
- 零件族分类增加标题栏优先级：`drawing_identity.part_name/title`、OCR 图框文本和 OCR summary 的权重高于技术要求、制造线索和证据路径。
- OCR 无标签图框增加保守零件名提取：当图框行包含图号和“尾门较链/door hinge/限位器/冲压件”等零件族词时，抽取为 `drawing_identity.part_name`，并保留 OCR block evidence ref。
- 扩充门铰链、限位器、冲压件的识别词：覆盖常见中文错识别、英文缩写、结构件、功能词和工艺外观线索。
- 降低“衬套/bushing/轴套”作为门铰链独立判定依据的影响；它仍可作为门铰链组件线索，但不能单独把一张衬套图判成门铰链。
- 强化视觉模型提示：要求先读标题栏，零件名必须优先来自图框，不能把局部标注或子件名称当作整张图纸零件名。
- Hybrid 模式增加 OCR 身份锁定：当 OCR/标题栏高置信识别出整件 `drawing_identity` 和零件族时，视觉结果只能补充结构、特性、组件和工艺线索，不能覆盖整件零件名或零件族。

## Non-goals
- 不新增独立“衬套”零件族。
- 不重写 V1.14 的族知识库转换、三表联动、行动项或导出质量门。
- 不让标题栏结果绕过人工复核；低置信或 OCR 错识别仍需要确认。
- 不把局部组件词完全删除；它们仍可用于工艺、PFMEA 或控制计划建议。

## Acceptance
- 图框/标题栏写“尾门铰链/尾门较链/door hinge/DH ASSY”时，零件族识别返回 `door_hinge`，matched evidence 指向标题栏或 `drawing_identity.part_name`。
- 只有“衬套/bushing/轴套”组件词、缺少铰链标题时，不会自动判成 `door_hinge`。
- OCR 无标签图框行能抽取出门铰链类零件名，并带 `field_evidence_refs.part_name`。
- 视觉 prompt 明确要求标题栏优先，并区分整件零件名与局部组件。
- Hybrid 成功调用视觉模型时，如果视觉把整件名误写成“衬套”等局部组件，高置信 OCR 标题栏仍锁定最终 `drawing_identity.part_name` 和 `door_hinge` 零件族。
- 定向测试覆盖分类、OCR 图框抽取和知识规则加载。
