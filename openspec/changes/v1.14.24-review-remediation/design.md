# Design: V1.14.24 Review Remediation

## Approach
本轮按风险顺序做窄改动：先加硬安全和导出门槛，再统一三表运行合同，再修桌面任务状态，最后补 CI/测试可信度。每个主题先补失败测试，再做最小实现。

## Security and Delivery Gates
- 平台 API 默认只监听 `127.0.0.1`，缺少 token 时拒绝普通访问；显式 dev 开关才允许无鉴权开发运行。
- artifact 下载前按数据库记录复算 SHA256；列表不返回服务器绝对路径。
- review patch 必须是可解析 JSON object，坏 patch 不推进项目状态。
- final export 只允许质量门通过的链路；不通过时拒绝写 final 文件。
- 桌面备份使用脱敏数据库副本，`settings.ai_api_key` 不进入备份 zip。

## Three-Table Contract
- PFD/PFMEA/CP bundle 和行级对象保留 `schema_version`、`document_type`、`evidence_refs`、`confidence`、`ai_inferred`、`needs_confirmation`。
- LLM 输出 schema 支持证据与置信度；归一化时可从上游继承，缺失时标记人工确认。
- `special_characteristic_class` 只表示 `SC/CC/无`，`characteristic_refs` 保存具体特性 ID。
- CP 生成范围包含 H/M、高严重度，以及带特殊特性或特性引用的 PFMEA 行。

## Desktop Runtime State
- 阶段切到 running 必须先持久化，API 返回持久化后的 run。
- 阶段确认和重生成接口防止重复后台任务写同一个 run。
- SSE 空通道或重连时查询持久化 chain state，返回真实 done/failed；开启 API token 时 SSE 也必须鉴权。

## Verification
- Python 使用 pytest 作为官方入口。
- Excel 验证从 zip 结构检查升级到 `openpyxl.load_workbook` 打开所有 sheet。
- CI 分 Python offline、real acceptance、desktop build 三类信号；真实 API 保持手动/发布触发。

## Architecture Boundary
- 第一轮不大拆 `pipeline.py`，只允许为安全门槛和 canonical contract 做必要的边界适配。
- `quality_gates` 本轮保持以纯判断为目标；若发现 review issue、knowledge recommendation、自动确认等副作用，先记录迁出点和测试缺口。
- 第二轮拆分顺序建议为 drawing analysis、three-table generation、chain assembly、export facade，避免和本轮安全/状态修复互相放大风险。
