# Design: V3.2.1 Formal Output Quality Gates

## Quality Gate

正式输出质量门继续使用 `evaluate_export_gate()` 作为唯一入口。新增结构缺陷由 `audit_chain()` 产生，severity 为 `blocker` 的审计项进入 `manual_review_items`、`review_issues`，并使 `allow_user_export=false`。

结构缺陷包括重复 `control_plan_id`、PFMEA 未被 CP 覆盖、CP 缺少产品/过程特性、CP 只有“按图纸/按规范/按工艺卡/按作业指导书”等泛化控制语句。

## CP ID

CP ID 不再信任模型返回值。链式生成和规则生成统一使用 `CP-` + PFMEA 后缀，例如 `PFMEA-P02-01` 对应 `CP-P02-01`。模型原始 ID 如需保留，只写入 `model_control_plan_id`。

## Drawing Risks

OCR 身份疑点和盐雾技术要求漏项先在 drawing gate 里形成 manual review item，再通过 chain metadata 带到正式质量门。未确认的 blocker 不能正式导出。

第一批风险只覆盖已观察到的问题：`D00R`、`HIMGE` 等标题栏字符混淆，以及 OCR 证据里存在“红锈 240h”但结构化技术要求漏掉该约束。

## Workbook Completeness

`三表追溯矩阵` 没有显式矩阵时从 APQPChain 的 PFD/PFMEA/CP 合成。`人工复核清单` 使用 quality gate 的 manual review items；如果为空但存在 review issues，则用 review issues 兜底。

## Regression

JLV fixture 是最小结构化失败样本，不包含真实客户图纸 PDF，不调用 OCR 或 AI。它只验证 MINOS 内部质量门能挡住已知缺陷形状。
