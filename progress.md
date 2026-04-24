# MINOS-CORE 重建进度

## 当前状态
本轮 fixture、测试和文档工作已进入收尾验证阶段。核心实现与 exporter 不在本轮写入范围内，相关行为由新增 unittest 契约测试约束。

## 已完成
- 已确认当前工作树存在并行改动风险，未回退、未覆盖允许范围外文件。
- 已将 `configs/samples/door_hinge.json` 清理为纯元数据。
- 已将 `configs/samples/limiter.json` 清理为纯元数据。
- 已将 `configs/samples/stamping.json` 清理为纯元数据。
- 已新增 `tests/fixtures/apqp_chain/process_flow.json`。
- 已新增 `tests/fixtures/apqp_chain/pfmea.json`。
- 已新增 `tests/fixtures/apqp_chain/control_plan.json`。
- 已新增 `tests/test_apqp_rebuild_contract.py`，覆盖：
  - domain 加载完整 APQP fixture。
  - validation 完整链路成功。
  - mandatory PFMEA 缺 CP 覆盖失败。
  - xlsx sheet 名清洗、截断和去重。
  - xlsx zip 基本结构。
  - APQP 工作簿 5 张固定 sheet。
  - CLI `list`、`validate`、`export`。
- 已重写 `task_plan.md`、`progress.md`、`findings.md`、`project_flow.mmd` 为 MINOS-CORE 重建口径。
- 已新增 `rebuild_manifest.md` 记录交付清单和契约边界。

## 当前待验证
/// 1. 校验所有 JSON 文件能被 Python `json` 模块解析。
/// 2. 使用 unittest discovery 确认测试文件可被发现。
/// 3. 如核心代码尚未就绪，记录测试运行失败的真实原因，不把失败包装成完成。
/// 4. 用 git status 审核修改范围是否仍在允许清单内。

## 风险
- 当前读取到的 `minos_core` 目录尚未暴露 domain、validation、exporter、CLI Python 文件；如果其他 worker 尚未提交核心实现，契约测试会因 import 失败而失败。
- 本轮没有写核心代码，因此不会自行修复上述失败，只记录为跨 worker 对齐事项。

## 下一步
- 等核心代码 worker 暴露 `minos_core.domain`、`minos_core.validation`、`minos_core.exporters.*`、`minos_core.cli` 后，运行 `python -m unittest discover -s tests -v`。
- 若公开函数名不同，优先让核心代码对齐测试契约；只有在团队确认新命名更合理时，再更新测试适配层。
- exporter worker 需要确保生成的 APQP 工作簿 sheet 顺序固定，并保证 sheet 名唯一化发生在底层 xlsx writer。
