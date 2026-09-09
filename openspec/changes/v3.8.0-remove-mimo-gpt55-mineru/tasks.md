# Tasks

- [x] /// 1. 建立 v3.8.0 OpenSpec 和 Superpowers 修改计划。
- [x] /// 2. 写红灯测试：`MINOS_VISION_PROVIDER=mimo` 不再启用 Mimo。
- [x] /// 3. 删除 `ai_config.py` 中 Mimo provider、Mimo API key、Mimo base URL 和 Mimo model 分支。
- [x] /// 4. 写红灯测试：`MimoV25ChatCompletionsDrawingAnalyzer` 和 `_mimo_v25_drawing_analysis_prompt` 不再存在。
- [x] /// 5. 删除 `minos_core/adapters/multimodal.py` 中 Mimo Chat Completions adapter、prompt、payload 和 crop helper。
- [x] /// 6. 新增 `drawing_visual_evidence` 裁剪模块和测试。
- [x] /// 7. 新增 GPT5.5 `special_characteristics_visual_locator` fake/normalizer 和测试。
- [x] /// 8. 将 GPT5.5 locator 输出接入 hybrid fusion、evidence packet 和 judge 之前的候选融合。
- [x] /// 9. 清理 Mimo 命名残留，将测试 fixture source 改为 `gpt55_visual_locator`。
- [ ] /// 10. 用 JLV 图纸建立真实回归：当前 fake/单测已覆盖第 4 条第(2)项 SC、第 5/6 条 CC；真实 GPT5.5 图纸试跑仍不稳定，不能标记完成。
- [x] /// 11. 将所有产品版本来源同步到 `3.8.0`，并通过 `tests/test_release_version_sync.py`。
- [ ] /// 12. 运行聚焦测试、JLV 真实图纸验收、桌面构建和 release build；聚焦测试、编译、桌面构建、release build 和 packaged sidecar smoke 已通过，真实 JLV 完全验收仍未完成。
