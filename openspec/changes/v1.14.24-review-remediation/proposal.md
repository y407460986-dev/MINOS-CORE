# Proposal: V1.14.24 Review Remediation

## Why
5 路深度审查发现，MINOS-CORE 当前最大风险不在单个生成规则，而在交付边界和数据合同：平台/桌面安全默认值偏宽，final 导出门槛不够硬，链式三表证据与置信度会断链，桌面长任务状态可能误报，CI 和测试入口不能稳定代表真实交付状态。

本轮目标是先降低可交付风险，不做 `pipeline.py` 全量重构。

## What
- 加固平台和桌面边界：平台 API 默认本地监听并要求 token；SSE 补鉴权；API key 备份脱敏；artifact 和 review result 使用 SHA256 复核；final export 不通过质量门时阻断。
- 收敛三表运行合同：PFD/PFMEA/CP 输出必须带版本、证据、置信度、AI 推断和待确认标记；特殊特性分类与具体特性引用分离。
- 修复桌面链式长任务状态：阶段进入 running 先落库；确认/重生成防重复；SSE 重连返回真实终态。
- 修复测试和 CI 信号：统一 pytest 入口；补 test/dev 依赖；修 real API marker；去掉本机绝对路径；增加桌面构建检查；Excel 验证使用 `openpyxl` 打开。
- 仅做与上述合同统一直接相关的轻量拆分，不做无关架构重写。
- 记录架构减重边界：本轮只识别 `pipeline.py`、`quality_gates` 和 stage assembly 的后续拆分点，避免在安全/合同修复同时扩大重构面。

## Non-goals
- 不删除旧 CLI / legacy 三表入口。
- 不在本轮彻底拆分 `pipeline.py`、`quality_gates` 或 `DesktopRunService`。
- 不把真实 API 长测放进普通 PR 必跑路径。
- 不引入新的企业权限、多租户或客户门户能力。

## Acceptance
- 安全与 final export 相关回归测试覆盖默认鉴权、hash 复核、坏 patch 拒绝、final 阻断和备份脱敏。
- 链式 PFD/PFMEA/CP 测试覆盖 schema、行级证据、置信度、特殊特性引用和 CP 目标行选择。
- 桌面后端测试覆盖 running 落库、重复请求保护、SSE 终态恢复和 SSE 鉴权。
- CI 配置安装测试所需依赖，pytest 为官方全量入口，real API marker 能选中目标测试，桌面前端构建进入 CI。
- `python -m pytest tests`、前端 `npm run build` 或相应聚焦验证结果被记录到进度中。
- `findings.md` 或集成记录中列明本轮不拆的大文件、后续拆分顺序，以及 `quality_gates` 中仍需迁出的副作用风险。
