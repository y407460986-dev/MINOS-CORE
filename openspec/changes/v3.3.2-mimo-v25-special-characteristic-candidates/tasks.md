# Tasks

- [x] /// 1. 建立 OpenSpec proposal，明确 mimo-v2.5 只作为视觉候选识别 provider。
- [x] /// 2. 建立 OpenSpec design，锁定小米 mimo Chat Completions API、`image_url` 传图和候选 schema。
- [x] /// 3. 建立 OpenSpec tasks，拆分后续配置、适配器、schema、fusion、registry、downstream、gate 和验证工作。
- [x] /// 4. 更新根记录文件：`task_plan.md`、`progress.md`、`findings.md`。
- [x] /// 5. 更新 `project_flow.mmd`，只追加本变更节点和边。
- [x] /// 6. 配置：增加 vision provider 配置读取和测试。
- [x] /// 7. 适配器：增加 mimo-v2.5 analyzer factory、prompt 和 payload 测试。
- [x] /// 8. schema：增加 special_characteristic_candidates 规范化和风险投影。
- [x] /// 9. fusion：合并 OCR 明确文本候选和 mimo 视觉候选。
- [x] /// 10. registry：只注册已确认 SC/CC，跳过未确认候选。
- [x] /// 11. downstream：PFD/PFMEA/CP 清理未确认特殊特性引用。
- [x] /// 12. gate：未确认候选阻断正式导出。
- [x] /// 13. 验证：运行聚焦测试、UTF-8 检查和 diff 检查。
