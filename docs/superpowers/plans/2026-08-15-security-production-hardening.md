# MINOS-CORE 安全与生产加固修复计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 封堵平台任意文件读写、修复三表 final 导出质量门绕过，并收口 sidecar、任务并发、CI 签名供应链和文档/类型检查缺口。

**Architecture:** 第一阶段建立一个统一的可信路径校验 seam，所有上传、fixture 引用和知识库输出都通过该 seam；final 导出统一从质量门进入。第二阶段修复桌面任务生命周期和 SQLite 并发；第三阶段修复 CI/release 供应链与架构漂移。每个阶段都有独立回归测试，可单独合并。

**Tech Stack:** Python 3.11、pytest、FastAPI、SQLite、React/Tauri、Rust、GitHub Actions、PyInstaller、npm/Cargo lock。

---

## 文件地图

### 第一阶段：安全边界

- Create: `minos_core/security_paths.py` — 可信根、相对引用、文件名、symlink/reparse 校验。
- Modify: `minos_platform/utils.py` — 复制前安全校验、失败清理、禁止跟随 symlink。
- Modify: `minos_platform/routers/input_packages.py` — 只接受受信上传根内路径。
- Modify: `minos_platform/routers/review_patches.py` — patch 路径复用同一校验。
- Modify: `minos_core/adapters/fixture_json.py` — 限制 `evidence_path` 和 `review_patch_path` 在包目录内。
- Modify: `minos_desktop/api/routes_knowledge.py` — 校验 `family_key` 和最终写入路径。
- Modify: `minos_core/edit_patch.py` — final 导出强制质量门。
- Test: `tests/test_security_paths.py`、`tests/platform/test_input_packages.py`、`tests/platform/test_review_patches.py`、`tests/test_fixture_json.py`、`tests/test_knowledge_routes.py`、`tests/edit_patch/test_export_gate.py`。

### 第二阶段：桌面运行稳定性

- Modify: `minos_desktop/api/routes_runs.py` — 防止同一 run/stage 重复启动。
- Modify: `minos_desktop/services/run_chain_service.py` — in-flight 状态、取消和失败持久化。
- Modify: `minos_desktop/api/sse.py`、`minos_desktop/api/app.py` — channel 回收和启动恢复。
- Modify: `minos_desktop/services/sqlite_store.py`、`minos_desktop/services/run_repository.py` — WAL、统一事务和 busy 重试。
- Modify: `apps/desktop-tauri/src-tauri/src/lib.rs` — sidecar PID/token ownership 和孤儿清理。
- Modify: `apps/desktop-tauri/src/api/sse-client.ts`、`apps/desktop-tauri/src/pages/ThreeTableWorkbench.tsx` — token 脱敏传递、重连错误和 timer 生命周期。
- Test: `tests/desktop/test_sse_chain_resilience.py`、`tests/desktop/test_services.py`、`tests/test_desktop_api_sidecar.py`、Rust lifecycle tests、Tauri static contract tests。

### 第三阶段：发布与工程门禁

- Modify: `.github/workflows/windows-release.yml` — Action pin、签名 secrets 最小作用域。
- Modify: `.github/workflows/ci.yml` — 将 `minos_platform` 纳入 mypy，启用 lock hashes 检查。
- Modify: `requirements/locks/linux-py311.txt`、`requirements/locks/windows-py311.txt` — 更新安全版本和 hashes。
- Modify: `apps/desktop-tauri/package.json`、`apps/desktop-tauri/package-lock.json` — 修复 npm audit high 漏洞。
- Modify: `.github/workflows/windows-release.yml` — 使用 Windows lock 安装发布测试依赖。
- Modify: `minos-desktop-api.spec` — 收集 `config/`。
- Modify: `pytest.ini`、`tests/acceptance/test_real_api_acceptance.py`、`tests/test_ci_contract.py` — 修复 real_api 标记契约。
- Modify: `README.md`、`docs/architecture/data-flow.md`、`docs/architecture/modules.md`、`CHANGELOG.md`、`docs/adr/002-ai-resilience.md` — 修正真实入口和质量门配置说明。
- Test: `tests/test_ci_contract.py`、`tests/test_dependency_hygiene.py`、`tests/test_runtime_paths.py`、`tests/test_release_version_sync.py`。

---

## Task 1: 建立安全修复基线

**Files:**
- Test: `tests/test_security_paths.py`
- Test: `tests/platform/test_input_packages.py`
- Test: `tests/test_fixture_json.py`
- Test: `tests/edit_patch/test_export_gate.py`

- [ ] **Step 1: 写最小红灯测试**

覆盖以下行为，不测试实现细节：

```python
def test_rejects_reference_outside_allowed_root(tmp_path):
    root = tmp_path / "package"
    root.mkdir()
    outside = tmp_path / "secret.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        validate_relative_reference("../secret.json", root)


def test_rejects_family_key_path_separator():
    with pytest.raises(ValueError):
        validate_safe_filename("../../outside")


def test_final_export_requires_quality_gate():
    with pytest.raises(ExportGateError):
        export_edited_three_tables(blocked_chain, output_dir, export_mode="final")
```

- [ ] **Step 2: 运行红灯测试**

Run:

```powershell
python -m pytest tests/test_security_paths.py tests/platform/test_input_packages.py tests/test_fixture_json.py tests/edit_patch/test_export_gate.py -q
```

Expected: 新增路径和 final 导出测试失败；失败原因必须是当前代码未拒绝越界路径或仍生成 final 文件，而不是测试导入错误。

- [ ] **Step 3: 提交基线测试**

```powershell
git add tests/test_security_paths.py tests/platform/test_input_packages.py tests/test_fixture_json.py tests/edit_patch/test_export_gate.py
git commit -m "test: lock down path and final export contracts"
```

---

## Task 2: 实现统一可信路径校验

**Files:**
- Create: `minos_core/security_paths.py`
- Modify: `minos_platform/utils.py`
- Modify: `minos_core/adapters/fixture_json.py`
- Test: `tests/test_security_paths.py`

- [ ] **Step 1: 实现最小接口**

实现以下接口，所有返回路径均为 canonical `Path`：

```python
def validate_trusted_path(
    value: str | Path,
    allowed_root: str | Path,
    *,
    allow_directory: bool,
    must_exist: bool = True,
) -> Path:
    """Return a canonical path strictly inside allowed_root."""


def validate_relative_reference(value: str, base_dir: str | Path) -> Path:
    """Resolve a JSON reference and reject absolute, escaping, or linked paths."""


def validate_safe_filename(value: str) -> str:
    """Return a safe single filename stem or raise ValueError."""
```

规则：

- 拒绝空字符串、NUL、绝对路径、`.`、`..` 和 Windows/Unix 分隔符穿越；
- `resolve(strict=True)` 后必须位于 allowed root；
- 源文件或其目录成员出现 symlink/reparse point 时拒绝；
- 目录复制只允许普通文件和目录；
- Windows 保留设备名和大小写不敏感冲突需要拒绝。

- [ ] **Step 2: 修复 JSON 引用读取**

在 `fixture_json.py` 中把 `base_path / str(path_value)` 替换为 `validate_relative_reference(path_value, base_path)`，再调用 `read_json_object()`。错误必须在读取文件前抛出。

- [ ] **Step 3: 修复复制工具**

在 `minos_platform/utils.py` 中：

- 校验 source 位于受信根；
- `copytree(..., symlinks=True)` 后拒绝任何 symlink 成员，或复制前递归拒绝；
- 写入失败时删除已生成目标；
- hash 校验失败时删除目标副本。

- [ ] **Step 4: 运行安全回归**

```powershell
python -m pytest tests/test_security_paths.py tests/test_fixture_json.py tests/platform/test_input_packages.py tests/platform/test_review_patches.py -q
```

Expected: 所有路径穿越、绝对路径、symlink 和 hash 失败清理用例通过。

- [ ] **Step 5: 提交**

```powershell
git add minos_core/security_paths.py minos_platform/utils.py minos_core/adapters/fixture_json.py tests
git commit -m "fix: enforce trusted file path boundaries"
```

---

## Task 3: 修复知识库任意文件写入

**Files:**
- Modify: `minos_desktop/api/routes_knowledge.py:100-141`
- Test: `tests/test_knowledge_routes.py`

- [ ] **Step 1: 写红灯测试**

覆盖：

- `family_key="../../evil"` 返回 422；
- `family_key="a\\..\\evil"` 返回 422；
- 合法 `door_hinge_01` 仍写入目标目录；
- 目标目录为 symlink 时拒绝写入。

- [ ] **Step 2: 实现校验和原子写入**

调用 `validate_safe_filename(family_key)`；对 `target_dir` 和最终 target 做 canonical containment 校验。先写同目录临时文件，成功后使用 `Path.replace()` 原子替换。

- [ ] **Step 3: 验证**

```powershell
python -m pytest tests/test_knowledge_routes.py tests/platform -q
```

Expected: 越界写入测试失败变为 422，合法 seed import 保持通过。

- [ ] **Step 4: 提交**

```powershell
git add minos_desktop/api/routes_knowledge.py tests/test_knowledge_routes.py
git commit -m "fix: prevent knowledge seed path traversal"
```

---

## Task 4: 统一 final 导出质量门

**Files:**
- Modify: `minos_core/edit_patch.py:203-248`
- Test: `tests/edit_patch/test_export_gate.py`

- [ ] **Step 1: 写 final blocked / draft allowed 测试**

```python
def test_final_export_rejects_blocked_chain(...): ...
def test_draft_export_allows_unconfirmed_chain(...): ...
def test_final_export_writes_only_after_gate(...): ...
```

断言不仅检查异常，还检查 blocked 时目标目录没有 final workbook。

- [ ] **Step 2: 实现**

`export_edited_three_tables()` 在 `export_mode == "final"` 时强制调用 `require_export_gate(source)`，禁止调用方通过默认参数绕过；`draft` 保留当前草案导出语义。

- [ ] **Step 3: 验证**

```powershell
python -m pytest tests/edit_patch/test_export_gate.py tests/test_export_modes.py -q
```

- [ ] **Step 4: 提交**

```powershell
git add minos_core/edit_patch.py tests/edit_patch/test_export_gate.py tests/test_export_modes.py
git commit -m "fix: enforce quality gate for final exports"
```

---

## Task 5: 修复 sidecar ownership 和任务防重入

**Files:**
- Modify: `apps/desktop-tauri/src-tauri/src/lib.rs`
- Modify: `minos_desktop/api/routes_runs.py`
- Modify: `minos_desktop/services/run_chain_service.py`
- Test: Rust lifecycle tests、`tests/desktop/test_sse_chain_resilience.py`、`tests/test_desktop_api_sidecar.py`

- [ ] **Step 1: 写失败测试**

覆盖：

- 旧 token sidecar 被识别为同一应用实例并清理；
- 同一 `run_id + stage` 第二次确认返回 409 或幂等成功，不启动第二个任务；
- 任务异常后 in-flight 标记清除；
- 进程重启时遗留 `running` 阶段被标记为 failed，并保留 failure message。

- [ ] **Step 2: 实现**

Rust 侧持久化并校验 PID ownership，探活 401 不再简单视为“未就绪”；Python 侧以 `run_id + stage` 为 key 加锁，所有成功、异常、取消路径使用 `try/finally` 清理。

- [ ] **Step 3: 验证**

```powershell
python -m pytest tests/desktop/test_sse_chain_resilience.py tests/test_desktop_api_sidecar.py -q
cargo test --locked
cargo check --locked
```

- [ ] **Step 4: 提交**

```powershell
git add apps/desktop-tauri/src-tauri/src/lib.rs minos_desktop/api/routes_runs.py minos_desktop/services/run_chain_service.py tests
git commit -m "fix: prevent duplicate chain jobs and orphan sidecars"
```

---

## Task 6: 修复 SQLite 和 SSE 生命周期

**Files:**
- Modify: `minos_desktop/services/sqlite_store.py`
- Modify: `minos_desktop/services/run_repository.py`
- Modify: `minos_desktop/api/sse.py`
- Modify: `minos_desktop/api/app.py`
- Modify: `apps/desktop-tauri/src/api/sse-client.ts`
- Modify: `apps/desktop-tauri/src/pages/ThreeTableWorkbench.tsx`
- Test: `tests/desktop/test_sse_chain_resilience.py`、SQLite concurrency tests、Tauri static tests

- [ ] **Step 1: 写失败测试**

覆盖：

- SQLite 启动启用 WAL；
- locked 写入进行有限退避后成功或返回明确错误；
- channel drain 后从注册表删除；
- SSE token 不进入 URL access log；
- React 卸载清理 interval；
- `getStreamToken()` 失败进入可见错误状态。

- [ ] **Step 2: 实现**

统一写事务入口，启用 WAL 和 busy timeout；channel 在 generator finalize 和 drain 完成时移除；前端保存 timer ref 并在 cleanup 清理；SSE 改为 header/cookie 传递短期 token，避免 query token。

- [ ] **Step 3: 验证**

```powershell
python -m pytest tests/desktop/test_sse_chain_resilience.py tests/test_desktop_api_sidecar.py -q
cd apps/desktop-tauri
npm run build
cd ..\..
```

- [ ] **Step 4: 提交**

```powershell
git add minos_desktop apps/desktop-tauri tests
git commit -m "fix: harden sqlite and sse lifecycle"
```

---

## Task 7: 加固 Windows 发布供应链

**Files:**
- Modify: `.github/workflows/windows-release.yml`
- Modify: `.github/workflows/ci.yml`
- Test: `tests/test_ci_contract.py`、`tests/test_desktop_installer_nsis.py`

- [ ] **Step 1: 写 CI 契约测试**

断言：

- checkout/setup-python/setup-node/rust-toolchain 都使用完整 40 位 commit SHA；
- production signing secrets 不存在 job-level `env`；
- secrets 只出现在导入证书和签名步骤；
- Windows release 使用 `requirements/locks/windows-py311.txt` 安装测试依赖；
- 缺证书时仍 fail closed。

- [ ] **Step 2: 修改 workflow**

把 Action tag 固定到经过审查的 immutable SHA，并在每个 pinned action 保留版本注释。将 PFX/password 从 job-level env 移到最小的签名步骤；优先使用短生命周期证书导入和签名步骤，不让构建/测试步骤继承 signing secrets。

- [ ] **Step 3: 验证**

```powershell
python -m pytest tests/test_ci_contract.py tests/test_desktop_installer_nsis.py -q
python scripts/check_repo_hygiene.py
```

- [ ] **Step 4: 提交**

```powershell
git add .github/workflows/windows-release.yml .github/workflows/ci.yml tests
git commit -m "fix: pin release actions and scope signing secrets"
```

---

## Task 8: 收口依赖和静态质量门

**Files:**
- Modify: `requirements/locks/linux-py311.txt`
- Modify: `requirements/locks/windows-py311.txt`
- Modify: `apps/desktop-tauri/package.json`
- Modify: `apps/desktop-tauri/package-lock.json`
- Modify: `pyproject.toml` 或 CI 配置
- Modify: `pytest.ini`
- Modify: `tests/acceptance/test_real_api_acceptance.py`
- Modify: `tests/test_ci_contract.py`

- [ ] **Step 1: 写门禁测试**

覆盖：

- `minos_platform` 被 mypy 检查；
- 至少一个真实 API 测试具有 `real_api` marker；
- 普通 CI 不收集真实 API 测试；
- lock 生成命令包含 hashes；
- npm audit 不再有 high 漏洞。

- [ ] **Step 2: 更新依赖**

使用 lock-first 流程更新受影响依赖，至少核对 `idna`、`pillow`、`pip`、`setuptools`、`starlette`、`brace-expansion`、`fast-uri`、`postcss`、`undici` 等实际解析版本；不要直接修改第三方依赖版本字符串，先重生成 lock 并检查来源。

- [ ] **Step 3: 验证**

```powershell
.\.venv\Scripts\python.exe -m mypy minos_core minos_desktop minos_platform
.\.venv\Scripts\python.exe -m pip_audit
cd apps/desktop-tauri
npm audit --audit-level=high
npm ci
npm run build
cd ..\..
```

Expected: mypy 0 errors，pip-audit 无可修复漏洞，npm audit 无 high，前端构建通过。

- [ ] **Step 4: 提交**

```powershell
git add requirements apps/desktop-tauri/package.json apps/desktop-tauri/package-lock.json pyproject.toml pytest.ini tests
git commit -m "chore: close dependency and quality gates"
```

---

## Task 9: 修复打包、质量门配置和架构文档漂移

**Files:**
- Modify: `minos-desktop-api.spec`
- Modify: `config/quality_gates.yaml` 或删除其死配置路径
- Modify: `minos_core/quality_gates/config_loader.py`、实际 evaluator 文件
- Modify: `minos_core/pfd_to_pfmea_ai.py`
- Modify: `minos_core/ocr_detection.py`、`minos_core/adapters/mineru_ocr.py`
- Modify: `docs/architecture/data-flow.md`
- Modify: `docs/architecture/modules.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/adr/002-ai-resilience.md`
- Test: `tests/test_config_loader.py`、`tests/test_runtime_paths.py`、核心 pipeline 契约测试

- [ ] **Step 1: 先选择质量门配置唯一方向**

推荐：保留 YAML 为唯一运行时配置来源，让 evaluator 接受已加载的 stage config；为每个阈值增加行为测试。禁止同时保留“YAML 配置”和“代码默认值”两套可修改权威。

- [ ] **Step 2: 修复元数据和 OCR 探测**

将规则生成的 `llm_used` 改为真实值；统一 MinerU 可执行命令解析函数，探测和执行必须使用同一候选顺序。

- [ ] **Step 3: 修复 PyInstaller 内容**

将 `config/` 纳入 spec，并增加安装包启动 smoke，确认运行时能读取质量门配置。

- [ ] **Step 4: 更新架构文档**

文档必须明确：

- `pipeline/orchestration.py` 是图纸三表主链入口；
- `pipeline_chain.py` 是 CLI/兼容入口；
- fixture/platform draft 是另一条受控输入路径；
- final export 的质量门不变量；
- `_types.py` 只描述实际被使用的类型，不宣称已替换全仓 `dict[str, Any]`。

- [ ] **Step 5: 验证**

```powershell
python -m pytest tests/test_config_loader.py tests/test_runtime_paths.py tests/test_architecture_seams.py -q
python -m minos_core.cli doctor
python -m minos_core.cli write-demo-drawing --output out\security_plan_demo.png
python -m minos_core.cli generate-three-tables --input out\security_plan_demo.png --output-dir out\security_plan_smoke
```

- [ ] **Step 6: 提交**

```powershell
git add minos-desktop-api.spec config minos_core docs CHANGELOG.md tests
git commit -m "docs: align pipeline and quality gate architecture"
```

---

## Task 10: 全量验收和发布关闭

**Files:**
- Test: 全仓测试、发布契约和安装验证脚本
- Review: `docs/release-checklist.md`
- Review: `openspec/changes/v3.8.7-production-readiness/tasks.md`

- [ ] **Step 1: 运行 Python 全量验证**

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy minos_core minos_desktop minos_platform
.\.venv\Scripts\python.exe -m pytest tests -q -m "not real_api" --cov=minos_core --cov=minos_desktop --cov=minos_platform --cov-fail-under=80
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/check_repo_hygiene.py
```

- [ ] **Step 2: 运行前端/Rust 验证**

```powershell
cd apps/desktop-tauri
npm ci
npm audit --audit-level=high
npm run build
cd src-tauri
cargo check --locked
cd ..\..
```

- [ ] **Step 3: 运行安全扫描**

```powershell
ecc security-ioc-scan --root . --json
npx ecc-agentshield scan --path . --format json
```

验收标准：无 active runtime secret、无新增路径穿越、AgentShield 不出现 critical/high runtime finding；项目本地 settings 的可选权限告警单独记录，不伪装成代码修复完成。

- [ ] **Step 4: 运行真实安装验收**

在受保护 Windows runner：

```powershell
./scripts/build_release.ps1 -Channel Internal
./scripts/verify_installer.ps1 -Installer "dist/build/out/*internal-unsigned*.exe"
```

正式发布再运行签名通道，验证 Authenticode `Valid`、SHA256、安装、无 token 401、带 token 200、卸载和证书清理。

- [ ] **Step 5: 更新交付记录**

只在所有命令产生真实输出后更新：

- `docs/release-checklist.md`
- `openspec/changes/v3.8.7-production-readiness/tasks.md`
- `docs/plans/progress.md`
- `docs/plans/findings.md`

保留未完成的真实 API、JLV、Office 打开和正式签名证据，不用本地 smoke 代替外部验收。

---

## 合并顺序

1. Task 1-4：安全边界和 final 导出；可独立发布。
2. Task 5-6：sidecar、SQLite、SSE；依赖第一阶段的路径/错误契约，但不修改核心业务规则。
3. Task 7-8：CI、Action、依赖和类型门禁；必须在前两阶段后合并，避免把新失败混入安全回归。
4. Task 9：质量门配置、打包和文档收口。
5. Task 10：完整验收，不在验收阶段继续扩展功能。

## 风险控制

- 不修改当前已有的 6 个脏工作区文件，除非任务明确涉及且先记录原始差异。
- 不执行 `git reset`、`git clean`、批量删除输出目录或回滚并行改动。
- 不把 `minos_platform` 的类型错误通过 `exclude`、`type: ignore` 或放宽 strict 隐藏。
- 不用 `npm audit fix` 直接覆盖 lock；先确认每个升级的依赖来源和构建影响。
- 不把 AgentShield 对 `.claude/settings.local.json`、`.vscode/settings.json` 的 project-local optional 告警误当成运行时漏洞，但 `CLAUDE.md` 权限问题需要在目标 Windows 文件权限模型中单独复核。
