# ADR 003: Security and Validation

**Status**: Accepted

**Date**: 2026-05-28

**Context**: Track 3 - Security and Validation

## Context

MINOS-CORE v2 在安全方面存在以下问题：

1. **明文 API Key**：第三方 LLM/OCR 凭据散落在 `.env` 与配置文件，容易因为日志/异常打印泄露。
2. **未鉴权的桌面 API**：`minos-desktop-api` 在本机监听 HTTP 端口，但没有强制鉴权，任意本地进程都能调用三表生成。
3. **输入校验缺失**：图纸路径、fixture JSON、查询参数等没有统一的边界校验，PathTraversal/超大输入/异常 schema 都可能击穿管线。

## Decision

我们引入了 **`minos_desktop.security` 包** 来集中处理凭据和鉴权，并在 Core 与桌面层补齐输入校验。

### 1. 凭据保护：`SecretStr` + `SecureAPIKeyStore`

`minos_desktop/security/secret_str.py` 提供 `SecretStr`：

- `repr()` 与 `str()` 始终返回 `**********`，避免日志/异常意外暴露。
- 通过 `get_secret_value()` 显式获取明文。

`minos_desktop/security/api_key_store.py` 提供 `SecureAPIKeyStore`：

- 使用 `keyring` 把 API key 写入 OS 凭据存储（Windows Credential Manager / macOS Keychain / Secret Service）。
- 接受 `str` 或 `SecretStr`，存空值会抛 `ValueError`。
- 提供 `store_api_key` / `get_api_key` / `delete_api_key` / `has_api_key`。

### 2. 桌面 API Bearer 鉴权

`minos_desktop/api/auth.py::require_api_token` 是 FastAPI 依赖：

- 读取环境变量 **`MINOS_DESKTOP_API_TOKEN`**；
- 若设置了 token，则要求请求头 `Authorization: Bearer <token>`，否则返回 401（`UNAUTHORIZED`）；
- 若环境变量为空，依赖会放行（兼容本地开发）。

`minos_desktop/api/cli.py` 启动时若未提供 token，会通过 `secrets.token_urlsafe(24)` 自动生成并注入环境变量，确保进程内一致。

`minos_desktop/security/auth_middleware.py` 还提供了一个独立的 `AuthMiddleware` 类与 `require_auth` 装饰器，使用 `secrets.compare_digest` 做常量时间比较，便于自定义路由按需引用。

### 3. 输入校验

校验责任分摊到现有模块：

- `minos_core.validation.validate_chain` 校验 APQP 链路结构；
- `minos_core.schemas` 描述 fixture/输出 schema；
- 桌面 API 的 `schemas.py` 用 Pydantic 做 HTTP 边界校验；
- 服务层 `minos_desktop/services/run_service.py` 内的请求构造逻辑做路径与参数过滤。

## Consequences

### Positive

1. **凭据不再裸跑**：`SecretStr` 拦截了大多数日志泄露；`keyring` 把长期凭据移到 OS 凭据存储。
2. **本地 API 默认带鉴权**：CLI 启动后会写入 `MINOS_DESKTOP_API_TOKEN`，前端持有同一 token 才能访问。
3. **错误返回结构稳定**：未鉴权返回 401，前端 UX 容易处理。

### Negative

1. **新增 keyring 依赖**：在某些 headless Linux 环境需要额外的 Secret Service 后端。
2. **token 管理责任移交给前端**：必须在桌面 UI 启动时同步读取或派发 token。

### Neutral

1. 现有 `.env` 配置仍然有效；`SecureAPIKeyStore` 是可选项，未启用时回退到环境变量。
2. `require_api_token` 在未设置 token 时放行，便于本地脚本和单元测试，但生产部署必须显式配置。

## Implementation Status

**Completed**:

- ✅ `minos_desktop.security`：`SecretStr` / `SecureAPIKeyStore` / `AuthMiddleware`。
- ✅ `minos_desktop.api.auth.require_api_token` 接入所有受保护路由。
- ✅ `minos-desktop-api` CLI 启动时自动生成 token。

**Pending**:

- ⏳ 完整的 schema-级输入校验（统一 `minos_core.security` 包）。
- ⏳ 在前端持续展示 token 与一键复制能力。

## References

- `minos_desktop/security/secret_str.py`
- `minos_desktop/security/api_key_store.py`
- `minos_desktop/security/auth_middleware.py`
- `minos_desktop/api/auth.py`
- `minos_desktop/api/cli.py`

## Related ADRs

- ADR 001: Module Restructuring
- ADR 002: AI Service Resilience
- ADR 004: Observability
- ADR 005: Extensibility (本 ADR 中 `MinosError` 由 ADR 004 提供)

### Status Update (2026-06-26)

Phase 3 of the MINOS-CORE remediation plan reviewed this ADR:

| Item | Status | Notes |
|------|--------|-------|
| `SecretStr` / `SecureAPIKeyStore` / `AuthMiddleware` | ✅ Done | `minos_desktop/security/` package exists with 4 modules (`secret_str.py`, `api_key_store.py`, `auth_middleware.py`, `token_manager.py`) |
| `require_api_token` for protected routes | ✅ Done | Defined in `minos_desktop/api/auth.py` line 34 |
| CLI auto-generates token on startup | ✅ Done | Implemented in `minos_desktop/api/cli.py` |
| Schema-level input validation | 🔄 Partially done | `minos_core/validation.py` (607 lines) provides `InputValidator` (path traversal, file type/size, filename) and `validate_chain` for APQP chain structure; but no unified `minos_core.security` package exists -- validation is scattered across `minos_core.validation`, `minos_core.schemas`, and desktop API Pydantic schemas |
| Frontend token display and one-click copy | ⏳ Still pending | Not found in frontend SettingsPage or API client code |
