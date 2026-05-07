# Design: V1.14 Drawing Knowledge Linkage Closure

## Design Principle
V1.14 的核心原则是“先把事实、关系和责任对象化，再让 AI 帮忙生成”。图纸识别、知识复用、三表联动和行动闭环不能只是界面上的四个页面，而要共享同一套证据、ID、状态和质量门语义。

## Drawing Recognition Baseline
图纸识别结果进入统一事实层：
- `drawing_facts`：尺寸、公差、GD&T、材料、表面处理、特殊特性、图纸注释、引用标准、关键区域和工艺暗示。
- `characteristic_registry`：继续作为产品/过程特性的主数据入口，负责去重、稳定 ID、证据挂接和三表引用状态。
- `evidence_refs`：每个识别事实都要能回到图纸页码、区域、文本片段或视觉框。
- `review_debts`：低置信、冲突、缺少规格、疑似特殊特性等情况不静默吞掉，进入人工复核或行动项。

## Knowledge Reuse
知识复用以结构化知识对象为单位，而不是直接拼接文本：
- 知识对象至少包含 `knowledge_id`、`version`、`category`、`applicability`、`process_terms`、`characteristic_terms`、`failure_mode`、`effect`、`cause`、`prevention_control`、`detection_control`、`rating_hint`、`action_template`、`source`、`status`。
- 推荐生成顺序为：图纸事实 -> 工序上下文 -> 已采纳历史知识 -> 本地规则/模块库。
- 推荐项必须保留来源、命中原因、适用条件、目标三表行、建议字段和生命周期状态。
- 采纳推荐和写入字段继续分开：accept 表示认可建议，apply 才形成 edit patch。

## Three-Table Linkage
三表联动使用稳定引用和派生视图：
- PFD 工序、PFMEA 行、CP 控制项都要有稳定 ID，并保留来源证据。
- `linkage_map` 作为 PFD -> PFMEA -> CP 的统一查询入口。
- `sync_snapshot` 汇总当前三表覆盖状态、特殊特性贯穿状态和关键风险控制状态。
- `sync_issues` 输出缺失 PFMEA、缺失 CP、孤儿 CP、弱关联、特殊特性未贯穿、变更影响未处理等问题。
- 三表编辑必须通过 edit patch 进入，不能直接改写最终结果后跳过审计。

## Action Closure
行动项是闭环主对象：
- 来源包括图纸低置信事实、联动 gap、知识推荐未处理、高 AP 或高严重度风险、导出阻断项。
- 生命周期建议为 `open`、`in_progress`、`closed`、`ignored`、`expired`。
- 关闭必须有 evidence，忽略必须有 reason。
- 行动项要能回指图纸证据、知识推荐、三表行和质量门问题。
- 质量门读取行动项状态，正式导出只允许在关键问题闭环后放行。

## Desktop and Export
V1.13 桌面工作台承载 V1.14 的可见性：
- 图纸页显示识别事实、证据定位、置信度和待复核项。
- 三表页显示被知识建议和联动问题影响的行。
- 联动页按 PFD 工序展开 PFMEA 风险、CP 控制、gap、特殊特性贯穿和变更影响。
- 闭环页统一处理复核项、知识推荐和行动项。
- 导出页明确显示草案/正式状态、阻断原因和可审计清单。

## OpenSpec Loop
- Define：确认 V1.14 是图纸事实到工程闭环的基线，不是视觉引擎重写。
- Specify：定义图纸事实、知识对象、联动视图、行动项和导出质量门的边界。
- Implement：先落文档和 schema 约束，再接核心派生视图、桌面可见性和导出审计。
- Verify：用真实或脱敏样例检查图纸事实可追溯、推荐可处理、三表 gap 可见、行动项可关闭、正式导出可阻断。
