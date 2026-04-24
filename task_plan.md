# MINOS-CORE 重建任务计划

## 当前职责
本轮只负责 fixture、测试和文档，不写 `minos_core` 业务代码，不删除文件，不回退其他 worker 的改动。

允许写入范围：
- `tests/**`
- `configs/samples/*.json`
- `rebuild_manifest.md`
- `task_plan.md`
- `progress.md`
- `findings.md`
- `project_flow.mmd`

## 目标
把 MINOS-CORE 重建的测试底座先立住，让核心代码和 exporter worker 后续能按同一套输入、校验和 CLI 契约对齐。

本轮交付内容：
- sample configs 清理为纯元数据，不再承载路径、规则、规格值或工艺知识。
- 新增 `tests/fixtures/apqp_chain` 三表链路 fixture。
- 新增 unittest 契约测试，覆盖 domain 加载、validation、xlsx 结构、APQP 工作簿、CLI。
- 重写重建文档为 MINOS-CORE 口径。

## 成功标准
- `configs/samples/*.json` 只包含样本身份、产品族、阶段、语言、交付命名等元数据。
- APQP fixture 包含 `process_flow.json`、`pfmea.json`、`control_plan.json`，并能表达 PFD -> PFMEA -> CP 的完整追溯链。
- validation 测试必须同时覆盖：完整链路通过；mandatory PFMEA 缺少 CP 覆盖时失败。
- xlsx 测试必须覆盖：sheet 名清洗/截断/去重；xlsx zip 基本结构完整。
- APQP 工作簿测试必须要求 5 张 sheet：摘要、过程流程图、PFMEA、控制计划、三表追溯矩阵。
- CLI 测试必须覆盖 `list`、`validate`、`export` 三个动作。
- 文档和流程图能让后来 worker 明确 fixture、测试、核心代码、exporter 的边界。

## 执行流程
/// 1. 只读扫描仓库状态，确认现有 tests、configs、docs 和 minos_core 暴露情况。
/// 2. 清理 sample configs，把非元数据迁出配置口径。
/// 3. 建立 APQP 三表 fixture，固定可追溯链路样例。
/// 4. 编写 unittest 契约测试，不触碰核心实现。
/// 5. 重写 `task_plan.md`、`progress.md`、`findings.md`、`rebuild_manifest.md`、`project_flow.mmd`。
/// 6. 做 JSON 可解析性、测试发现、文档可读性和修改范围审核。

## OpenSpec 四步闭环
1. Define：以 MINOS-CORE 重建为对象，定义 fixture、测试和文档的交付边界。
2. Specify：用 fixture JSON 和 unittest 明确 domain、validation、exporter、CLI 的公开契约。
3. Implement：只在允许范围内新增/更新测试资产、样本元数据和文档。
4. Verify：运行结构检查和测试发现；如核心代码尚未就绪，记录契约测试的预期失败边界。

## 非目标
- 不实现 `minos_core` 任何核心逻辑。
- 不实现 exporter。
- 不迁移旧 `minos` 代码。
- 不删除旧文件。
- 不把真实本地路径、知识库路径或规格规则继续放进 sample config。

## 当前假设
- 核心代码和 exporter 由其他 worker 并行实现。
- 本轮测试按 `minos_core` 包名和 CLI `python -m minos_core.cli` 建立契约。
- 如果核心实现尚未出现，测试可以先作为重建验收门槛存在。
