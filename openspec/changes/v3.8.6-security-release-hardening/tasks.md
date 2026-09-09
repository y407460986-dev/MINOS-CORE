# v3.8.6 安全加固与发布整改 tasks

- [x] /// 1. 建立 OpenSpec 和根流程记录；验证：UTF-8 可读，流程图节点不重复。
- [x] /// 2. 为 SSE stream token 写红灯测试；验证：无 token / 错 token / 过期 token 失败，正确 token 通过。
- [x] /// 3. 实现 stream token 派生、校验和前端 URL 拼接；验证：SSE auth 聚焦测试通过。
- [x] /// 4. 为图纸文件和输出目录校验写红灯测试；验证：非法扩展、magic mismatch、null byte、不存在文件、文件型输出目录均失败。
- [x] /// 5. 实现 `validate_drawing_input_file()`、`validate_output_directory()`、`validate_user_selected_directory()` 并接入 API routes；验证：路径校验和 sidecar 聚焦测试通过。
- [x] /// 6. 为 Tauri 打开路径白名单写静态测试；验证：三个打开命令均调用白名单校验。
- [x] /// 7. 实现 Tauri 路径白名单和 canonicalize；验证：Rust check 和 Tauri 静态测试通过。
- [x] /// 8. 为 Platform auth required 写测试；验证：required 模式 token 缺失/错误被拒，正确 token 通过。
- [x] /// 9. 实现 `MINOS_PLATFORM_AUTH_REQUIRED` 和 CORS 收口；验证：platform tests 通过。
- [x] /// 10. 为 `SecretStr` Pydantic 脱敏写红灯测试；验证：`model_dump()` / `model_dump_json()` 不含明文。
- [x] /// 11. 实现 SecretStr serializer 脱敏；验证：secret/security 聚焦测试通过。
- [x] /// 12. 新增仓库卫生脚本和 CI job；验证：脚本本地通过，CI YAML 包含 frontend build 和 cargo check。
- [x] /// 13. 清理 release 追踪制品和 `.gitignore` / build 脚本；验证：`git ls-files release` 不再列出 exe/pdf。
- [x] /// 14. 为桌面 SQLite migration 写红灯测试；验证：空库、旧库、重复初始化和原表存在。
- [x] /// 15. 实现桌面 SQLite `schema_version` migration 骨架；验证：desktop services 聚焦测试通过。
- [x] /// 16. 新增 `docs/release-checklist.md`；验证：文档 UTF-8 可读，包含测试/build/smoke/安装/Excel/签名状态。
- [x] /// 17. 最终聚焦验证和 `git diff --check`；验证：记录通过项和未跑项。
