# v3.8.6 安全加固与发布整改 design

## Define

本变更是发布前止血，不重构主链路。主链路保持图纸识别到 PFD、PFMEA、CP、质量门和 Excel 导出的现状。

## Specify

SSE 使用主 API token 派生短期 stream token。普通 REST 继续使用 Bearer token。图纸文件校验和输出目录校验放在 `minos_core.validation`，API route 只调用 helper。Tauri 侧维护运行时路径白名单，打开前统一 canonicalize。

Platform API 使用 `MINOS_PLATFORM_AUTH_REQUIRED=1` 区分交付环境。SecretStr 的 Pydantic serializer 默认脱敏，明文仅能通过 `get_secret_value()` 获取。桌面 SQLite migration 只覆盖 `minos_desktop`，不重复处理已有 `minos_platform.ppap_schema_version`。

发布质量门通过 CI 和本地共用的 `scripts/check_repo_hygiene.py` 防止 release 二进制、未授权 PDF 和敏感文件回归。

## Implement

按蓝图 PR1 到 PR9 分批实现，每个行为变化先写失败测试，再写最小实现。文档、CI 和 release 清理属于配置/文档变更，使用静态检查和仓库状态验证。

## Verify

聚焦验证：

- `python -m pytest tests/desktop/api/test_sse_auth.py tests/desktop/test_sse_chain_resilience.py -q`
- `python -m pytest tests/desktop/api/test_path_validation.py tests/test_desktop_api_sidecar.py -q`
- `python -m pytest tests/desktop/security/test_secret_str.py tests/test_desktop_api_sidecar.py -q`
- `python -m pytest tests/desktop/services/test_sqlite_store_migration.py tests/desktop/services -q`
- `python -m pytest tests/platform -q`
- `python -m pytest tests/test_desktop_tauri_app_state.py -q`
- `python scripts/check_repo_hygiene.py`

发布前综合验证按 `docs/release-checklist.md` 执行。
