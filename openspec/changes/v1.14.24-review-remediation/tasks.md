# Tasks: V1.14.24 Review Remediation

## Define
- [x] /// 1. 意图：把本轮目标收口为审查风险整改。输入：5 路审查结论和用户执行计划。输出：安全、合同、桌面状态、CI 测试四条主线。验证：proposal 明确不做全量架构重写。
- [x] /// 2. 意图：建立 OpenSpec 四步闭环。输入：既有 OpenSpec 目录结构。输出：proposal、design、tasks。验证：三个文件可 UTF-8 读取。

## Specify
- [x] /// 3. 意图：锁定安全与交付硬门槛。输入：平台鉴权、artifact、review patch、final export、备份问题。输出：可测试的阻断和脱敏规则。验证：design 写明每项门槛。
- [x] /// 4. 意图：锁定三表 canonical contract。输入：PFD/PFMEA/CP 断链问题。输出：schema、证据、置信度、特殊特性字段语义。验证：design 写明字段职责。
- [x] /// 5. 意图：锁定桌面任务状态目标。输入：SSE 终态、running 落库、重复提交问题。输出：持久化状态和重连语义。验证：design 写明重连必须返回真实终态。
- [x] /// 6. 意图：锁定 CI 和测试入口。输入：pytest/unittest 混用、marker、路径、桌面构建问题。输出：pytest 官方入口和桌面构建信号。验证：design 写明 CI 分类。

## Implement
- [x] /// 7. 意图：实现安全与 final export 阻断。输入：worker 安全线测试。输出：平台/adapter/export/backup 最小修复。验证：平台 review patch 语义 dry-run、artifact hash、final export gate、SSE token、备份 zip 脱敏聚焦测试通过。
- [x] /// 8. 意图：实现三表合同贯穿。输入：worker 三表合同线测试。输出：bundle/row 字段完整，证据和置信度保守继承，canonical row 剥离 `classification` 旧字段。验证：三表 workflow/linkage/risk 聚焦测试通过。
- [x] /// 9. 意图：实现桌面长任务状态修复。输入：worker 桌面状态线测试。输出：running 落库、重复保护、SSE 真实终态与鉴权，PFMEA/CP 重生成后台接受已认领 running。验证：desktop API/SSE 聚焦测试通过。
- [x] /// 10. 意图：实现 CI 与测试可信度修复。输入：worker CI 测试线验证。输出：test/dev extra、CI jobs、marker、路径和 Excel 打开验证。验证：pytest marker/path/openpyxl 聚焦检查通过。
- [x] /// 11. 意图：识别架构减重边界。输入：`pipeline.py`、`quality_gates`、stage assembly 和当前 OpenSpec。输出：本轮不拆范围、第二轮拆分顺序和副作用迁移清单。验证：发现记录可指导后续重构，不扩大本轮改动。
- [x] /// 16. 意图：实现公司工艺边界默认档案。输入：用户确认的本厂能力、外购输入和禁止工序。输出：`minos_core.process_boundary` 默认配置、prompt 文本和 PFD 后处理。验证：`tests/test_process_boundary.py` 红绿通过。
- [x] /// 17. 意图：把工艺边界接入桌面设置。输入：现有 SQLite settings 和 `/api/settings`。输出：`get_process_boundary_config`、`set_process_boundary_config`、GET 返回和 PATCH 保存。验证：desktop service/API 聚焦测试通过，空 payload 返回 422。
- [x] /// 18. 意图：把工艺边界接入 PFD 链路。输入：`generate_pfd_from_drawing` 和桌面 `start_chain_run`。输出：prompt 注入、生成后自动修正、metadata 调整记录和桌面运行传参。验证：三表链路 mock LLM 测试和服务层传参测试通过。
- [x] /// 19. 意图：在设置页开放全局编辑入口。输入：SettingsPage、前端 API/types。输出：“公司工艺边界”区块、编辑/保存/恢复默认、多行文本输入和 PATCH client。验证：`tests/test_desktop_tauri_app_state.py` 静态契约通过。

## Verify
- [x] /// 12. 意图：运行 Python 聚焦回归。输入：五条线改动文件。输出：相关测试结果。验证：`tests/three_table_workflow ... tests/test_confidence_propagation.py` 112 项和 9 个 subtests 通过；安全/桌面/CI 聚焦 150 项和 12 个 subtests 通过。
- [x] /// 13. 意图：运行全量 Python 测试。输入：当前工作区。输出：`python -m pytest tests -q` 结果。验证：975 项通过，8 项 skipped，70 个 subtests 通过，退出码为 0。
- [x] /// 14. 意图：运行桌面前端构建。输入：`apps/desktop-tauri`。输出：`npm ci` 和 `npm run build` 结果。验证：`npm ci` 退出码为 0，`npm run build` 完成 TypeScript 检查和 Vite production build。
- [x] /// 15. 意图：检查文档和 diff。输入：OpenSpec、根文档、代码改动。输出：UTF-8、Mermaid 节点、`git diff --check` 结果。验证：无乱码、无冲突标记。
