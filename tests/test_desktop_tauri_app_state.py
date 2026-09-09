from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_drawing_import_page_stays_mounted_across_navigation() -> None:
    app_source = (ROOT / "apps" / "desktop-tauri" / "src" / "App.tsx").read_text(encoding="utf-8")

    assert '{page === "import" && (' not in app_source
    assert '<div hidden={page !== "import"}>' in app_source
    assert "<DrawingImportPage" in app_source


def test_drawing_import_page_uses_chain_start_feedback() -> None:
    page_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "DrawingImportPage.tsx"
    ).read_text(encoding="utf-8")

    assert "chainStartFeedback(run, cs)" in page_source
    assert 'setStatus("PFD 已生成，请确认过程流程图。");' not in page_source


def test_drawing_import_page_lets_backend_default_hybrid_analysis_for_sc_cc_detection() -> None:
    page_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "DrawingImportPage.tsx"
    ).read_text(encoding="utf-8")

    assert 'const analysisMode: DrawingAnalysisMode = "ocr_only";' not in page_source
    assert "analysis_mode: analysisMode" not in page_source
    assert 'context: { source: "tauri-react-desktop", ocr_engine: "auto" }' in page_source


def test_drawing_import_page_displays_actual_analysis_metadata_before_input_context() -> None:
    page_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "DrawingImportPage.tsx"
    ).read_text(encoding="utf-8")

    assert (
        (
            "const analysisMode = text(analysisMetadata.analysis_mode ?? metadata.analysis_mode "
            '?? context.analysis_mode, "hybrid");'
        )
        in page_source
    )
    assert (
        "const analysisMode = text(context.analysis_mode ?? metadata.analysis_mode"
        not in page_source
    )


def test_drawing_import_page_refreshes_stage_context_and_shows_failure() -> None:
    page_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "DrawingImportPage.tsx"
    ).read_text(encoding="utf-8")
    type_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "api" / "types.ts"
    ).read_text(encoding="utf-8")

    assert "getRun" in page_source
    assert "refreshVisibleRun" in page_source
    assert "getRun(visibleRun.id)" in page_source
    assert "任务上下文已刷新" in page_source
    assert "生成未完成" in page_source
    assert "failure_message" in page_source
    assert "chain_stages?: ChainState" in type_source


def test_workbench_pfd_confirm_allows_direct_confirm_and_responsive_editor() -> None:
    page_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "ThreeTableWorkbench.tsx"
    ).read_text(encoding="utf-8")
    store_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "state" / "workbench-store.ts"
    ).read_text(encoding="utf-8")

    assert 'table: "pfd"' in store_source
    assert "saveDraftChanges" in page_source
    assert "onSaveDrafts={saveDraftChanges}" in page_source
    assert "confirmAllPfdRows" in page_source
    assert "visiblePfdRows.length === 0" in page_source
    assert "editValue" not in page_source
    assert 'aria-label="三表编辑画布"' in page_source


def test_workbench_rows_can_be_soft_deleted_and_chain_generation_is_polled() -> None:
    page_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "ThreeTableWorkbench.tsx"
    ).read_text(encoding="utf-8")
    client_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "api" / "client.ts"
    ).read_text(encoding="utf-8")

    assert "softDeleteRows" in page_source
    assert "onSoftDeleteRows={softDeleteRows}" in page_source
    assert "软删除" in page_source
    assert 'action: "soft_delete"' in page_source
    assert "isSaving" in page_source
    assert "正在确认全部过程流程图，失效模式分析将在后台生成" in page_source
    assert "getRun" in page_source
    assert "window.setInterval" in page_source
    assert "export function getRun" in client_source


def test_workbench_uses_top_level_chain_stages_and_hides_legacy_pfmea_placeholders() -> None:
    page_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "ThreeTableWorkbench.tsx"
    ).read_text(encoding="utf-8")
    store_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "state" / "workbench-store.ts"
    ).read_text(encoding="utf-8")

    assert "chainStagesFromRun" in page_source
    assert "updatedRun?.chain_stages" in page_source
    assert (
        "updatedRun?.raw_result?.chain_stages ?? updatedRun?.current_result?.chain_stages"
        not in page_source
    )
    assert "PFMEA-SYNC-" in store_source
    assert "待工程人员填写失效模式" in store_source
    assert "联动新增" in store_source


def test_workbench_pfmea_columns_follow_aiag_vda_core_fields() -> None:
    table_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "components" / "WorkbenchTable.tsx"
    ).read_text(encoding="utf-8")

    assert "columnsForRows" in table_source
    assert 'header: "结构-过程项"' in table_source
    assert 'header: "结构-过程步骤"' in table_source
    assert 'header: "结构-工作要素"' in table_source
    assert 'header: "功能-过程项"' in table_source
    assert 'header: "功能-过程步骤"' in table_source
    assert 'header: "功能-工作要素"' in table_source
    assert 'header: "失效后果"' in table_source
    assert 'header: "严重度"' in table_source
    assert 'header: "失效模式"' in table_source
    assert 'header: "失效原因"' in table_source
    assert 'header: "原因过程参数"' in table_source
    assert 'header: "预防控制"' in table_source
    assert 'header: "预防控制对象"' in table_source
    assert 'header: "预防控制时机"' in table_source
    assert 'header: "发生度"' in table_source
    assert 'header: "探测控制"' in table_source
    assert 'header: "探测对象"' in table_source
    assert 'header: "探测时机"' in table_source
    assert 'header: "探测度"' in table_source
    assert 'header: "AP"' in table_source
    assert 'header: "控制逻辑复核"' in table_source
    assert 'header: "特殊特性"' in table_source
    assert (
        '["special_characteristics", "special_characteristic", '
        '"special_characteristic_class", "classification"]'
        in table_source
    )
    assert 'header: "预防措施"' in table_source
    assert 'header: "探测措施"' in table_source
    assert 'header: "责任人"' in table_source
    assert 'header: "目标日期"' in table_source
    assert 'header: "RPN"' not in table_source
    assert 'const columns: WorkbenchColumnDef[] = [' not in table_source


def test_app_does_not_auto_open_failed_pfmea_run_as_latest_workbench_state() -> None:
    app_source = (ROOT / "apps" / "desktop-tauri" / "src" / "App.tsx").read_text(encoding="utf-8")

    assert "getRecentRuns(5)" in app_source
    assert "autoRestorableRun" in app_source
    assert "blocked_stage !== \"pfmea\"" in app_source
    assert "runs[0]) setActiveRun(runs[0])" not in app_source


def test_workbench_can_regenerate_failed_pfmea_stage() -> None:
    page_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "ThreeTableWorkbench.tsx"
    ).read_text(encoding="utf-8")

    assert "regeneratePfmeaStage" in page_source
    assert "regeneratePfmea" in page_source
    assert "重新生成失效模式分析" in page_source or "重新生成 PFMEA" in page_source
    assert 'const pfmeaStatus = stageStatus(run, "pfmea")' in page_source
    assert 'pfmeaStatus === "running"' in page_source


def test_workbench_refreshes_stale_run_when_reopened_or_toolbar_refresh_clicked() -> None:
    app_source = (ROOT / "apps" / "desktop-tauri" / "src" / "App.tsx").read_text(encoding="utf-8")
    page_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "ThreeTableWorkbench.tsx"
    ).read_text(encoding="utf-8")

    assert "refreshActiveRun" in app_source
    assert "onClick={() => void refreshActiveRun()}" in app_source
    assert "onRunRefresh={refreshActiveRun}" in app_source
    assert "onRunRefresh?: () => Promise<void>" in page_source
    assert "refreshRunSnapshot" in page_source
    assert "document.visibilityState === \"visible\"" in page_source
    assert "window.addEventListener(\"focus\", handleFocus)" in page_source
    assert "onRunRefresh().catch" in page_source


def test_chain_sse_client_reconnects_and_workbench_handles_step_failed() -> None:
    sse_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "api" / "sse-client.ts"
    ).read_text(encoding="utf-8")
    page_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "ThreeTableWorkbench.tsx"
    ).read_text(encoding="utf-8")

    assert "export type StepFailedEvent" in sse_source
    assert "export type HeartbeatEvent" in sse_source
    assert 'es.addEventListener("step_failed"' in sse_source
    assert 'es.addEventListener("heartbeat"' in sse_source
    assert "MAX_RETRIES" in sse_source
    assert "retryCount < MAX_RETRIES" in sse_source
    assert "setTimeout(() => void connect()" in sse_source
    assert "onConnectionStateChange" in sse_source
    assert "handlers.onStepFailed?.(data)" in sse_source
    assert "handlers.onHeartbeat?.(data)" in sse_source
    assert 'handlers.onError("连接中断")' not in sse_source
    assert "onStepFailed" in page_source
    assert "继续生成中" in page_source
    assert "正在自动重连" in page_source
    assert "已获取最终状态" not in page_source


def test_workbench_pfd_can_add_row_with_process_flow_patch() -> None:
    page_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "ThreeTableWorkbench.tsx"
    ).read_text(encoding="utf-8")
    table_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "components" / "WorkbenchTable.tsx"
    ).read_text(encoding="utf-8")

    assert "新增行" in table_source
    assert "onAddPfdRow" in table_source
    assert "saved === false" in table_source
    assert "addPfdRow" in page_source
    assert "return true" in page_source
    assert "return false" in page_source
    assert 'action: "add"' in page_source
    assert 'table: "process_flow"' in page_source
    assert "target_id: processStepId" in page_source
    assert "row_id: processStepId" in page_source
    assert "process_step_id" in page_source
    assert "operation_type" in page_source
    assert "flow_symbol" in page_source
    assert "process_function" in page_source
    assert "equipment" in page_source
    assert "product_characteristic" in page_source
    assert "process_characteristic" in page_source
    assert "special_characteristics" in page_source
    assert "responsibility" in page_source
    assert 'review_status: "待确认"' in page_source
    assert "needs_confirmation: true" in page_source


def test_workbench_pfd_rows_can_be_drag_reordered_by_sequence_patch() -> None:
    page_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "ThreeTableWorkbench.tsx"
    ).read_text(encoding="utf-8")
    table_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "components" / "WorkbenchTable.tsx"
    ).read_text(encoding="utf-8")
    store_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "state" / "workbench-store.ts"
    ).read_text(encoding="utf-8")

    assert "onReorderPfdRows" in table_source
    assert "GripVertical" in table_source
    assert "ArrowUp" in table_source
    assert "ArrowDown" in table_source
    assert "整行拖拽调整" in table_source
    assert "上移" in table_source
    assert "下移" in table_source
    assert "useRef" in table_source
    assert "draggedRowIdRef" in table_source
    assert 'event.dataTransfer.getData("text/plain")' in table_source
    assert "movePfdRow" in table_source
    assert "startPointerDrag" in table_source
    assert "finishPointerDrag" in table_source
    assert "document.elementFromPoint" in table_source
    assert "data-pfd-row-id" in table_source
    assert "data-pfd-drag-handle" in table_source
    assert "onPointerDown" in table_source
    assert "window.addEventListener(\"pointerup\"" in table_source
    assert "releasePointerCapture" in table_source
    assert "draggable={canDragReorderPfdRows}" in table_source
    assert "onDragStart" in table_source
    assert "onDrop" in table_source
    assert "reorderPfdRows" in page_source
    assert "buildPfdReorderPatch" in page_source
    assert "fullPfdRowsFromVisibleReorder" in page_source
    assert "visibleOrderIds" in page_source
    assert "visibleQueue.shift()" in page_source
    assert "hasPfdReorderFilter" not in page_source
    assert "canReorderRows={!hasPfdReorderFilter}" not in page_source
    assert "Array.isArray(items) || items.length === 0" in page_source
    assert "const sequence = (index + 1) * 10" in page_source
    assert "previousRow = reorderedRows[index - 1]" in page_source
    assert "nextRow = reorderedRows[index + 1]" in page_source
    assert "previousStepIds" in page_source
    assert "nextStepIds" in page_source
    assert "previous_step_ids: item.previousStepIds" in page_source
    assert "next_step_ids: item.nextStepIds" in page_source
    assert "changes: { sequence: item.sequence }" not in page_source
    assert "sortPfdRowsBySequence" in store_source
    assert "processFlowStepsFromResult" not in store_source


def test_quiet_focused_ui_motion_tokens_are_centralized() -> None:
    globals_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "styles" / "globals.css"
    ).read_text(encoding="utf-8")

    assert "--motion-fast" in globals_source
    assert "--motion-base" in globals_source
    assert "--motion-slow" in globals_source
    assert "--motion-ease" in globals_source
    assert "--motion-reduced: 1ms" in globals_source
    assert "@media (prefers-reduced-motion: reduce)" in globals_source
    assert "--motion-fast: var(--motion-reduced)" in globals_source
    assert "transition-duration: var(--motion-reduced)" in globals_source
    assert "animation-duration: var(--motion-reduced)" in globals_source


def test_secondary_pages_use_shared_experience_primitives() -> None:
    review_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "ReviewClosurePage.tsx"
    ).read_text(encoding="utf-8")
    export_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "ExportPage.tsx"
    ).read_text(encoding="utf-8")
    settings_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "SettingsPage.tsx"
    ).read_text(encoding="utf-8")
    experience_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "components" / "ui" / "experience.tsx"
    ).read_text(encoding="utf-8")

    for primitive in ("Surface", "Notice", "StatusPill", "EmptyState"):
        assert f"function {primitive}" in experience_source

    for source in (review_source, export_source, settings_source):
        assert 'from "@/components/ui/experience"' in source
        assert "Surface" in source
        assert "Notice" in source
        assert "StatusPill" in source

    assert "EmptyState" in review_source
    assert "EmptyState" in export_source
    assert "批量确认低风险 AI 项" not in review_source
    assert "草案包" in export_source and "正式提交包" in export_source
    assert "危险操作" in settings_source


def test_quiet_focused_ui_experience_contract_stays_intact() -> None:
    app_source = (ROOT / "apps" / "desktop-tauri" / "src" / "App.tsx").read_text(encoding="utf-8")
    shell_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "components" / "AppShell.tsx"
    ).read_text(encoding="utf-8")
    sidebar_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "components" / "Sidebar.tsx"
    ).read_text(encoding="utf-8")
    page_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "ThreeTableWorkbench.tsx"
    ).read_text(encoding="utf-8")
    table_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "components" / "WorkbenchTable.tsx"
    ).read_text(encoding="utf-8")

    assert 'aria-label="三表状态栏"' in page_source
    assert 'aria-label="三表上下文栏"' in page_source
    assert "SegmentedControl" in page_source
    assert "PreviewRail" in page_source
    assert 'aria-label="三表编辑画布"' in page_source
    assert 'aria-label="三表编辑画布"' in table_source
    assert 'aria-label="浮动上下文工具条"' in table_source
    assert "onSaveDrafts" in table_source
    assert "onSoftDeleteRows" in table_source
    assert "onMarkRowsForReview" in table_source
    assert "activeRowId" in table_source
    assert "tableState.activeRowId === row.original.rowId" in table_source
    assert "selectedRowIds[row.original.rowId]" in table_source
    assert "已选 ${selectedRows.length} 行" in table_source
    assert "InspectorPanel" not in app_source
    assert "inspector=" not in app_source
    assert "inspector:" not in shell_source
    assert "grid-cols-[236px_minmax(620px,1fr)_300px]" not in shell_source
    assert "bg-[hsl(var(--shell))]" in shell_source
    assert "bg-[hsl(var(--sidebar))]" in sidebar_source
    assert '<div hidden={page !== "import"}>' in app_source
    assert "{page === \"import\" && (" not in app_source
    assert "key={page}" not in app_source


def test_settings_page_exposes_local_data_management_actions() -> None:
    page_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "SettingsPage.tsx"
    ).read_text(encoding="utf-8")
    client_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "api" / "client.ts"
    ).read_text(encoding="utf-8")
    types_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "api" / "types.ts"
    ).read_text(encoding="utf-8")
    tauri_source = (
        ROOT / "apps" / "desktop-tauri" / "src-tauri" / "src" / "lib.rs"
    ).read_text(encoding="utf-8")

    assert "数据管理" in page_source
    assert "本地数据位于 Windows 用户数据目录" in page_source
    assert "打开数据目录" in page_source
    assert "打开输出目录" in page_source
    assert "备份数据" in page_source
    assert "清空项目与运行记录" in page_source
    assert "恢复初始状态" in page_source
    assert "getDataManagementStatus" in client_source
    assert "backupDataManagement" in client_source
    assert "clearDataManagement" in client_source
    assert "openPath" in client_source
    assert "DesktopDataManagementStatus" in types_source
    assert "DesktopDataClearScope" in types_source
    assert "fn open_path" in tauri_source
    assert "open_path," in tauri_source


def test_tauri_open_paths_are_guarded_by_allowlist() -> None:
    rust_source = (
        ROOT / "apps" / "desktop-tauri" / "src-tauri" / "src" / "lib.rs"
    ).read_text(encoding="utf-8")

    assert "struct OpenPathAllowlist" in rust_source
    assert "fn remember_allowed_path" in rust_source
    assert "fn ensure_open_path_allowed" in rust_source
    assert ".manage(OpenPathAllowlist::default())" in rust_source
    assert (
        "fn open_output_dir(app: tauri::AppHandle, open_paths: tauri::State<OpenPathAllowlist>, path: String)"
        in rust_source
    )
    assert (
        "fn open_path(app: tauri::AppHandle, open_paths: tauri::State<OpenPathAllowlist>, path: String)"
        in rust_source
    )
    assert (
        "fn reveal_file(app: tauri::AppHandle, open_paths: tauri::State<OpenPathAllowlist>, path: String)"
        in rust_source
    )
    assert ".open_path(path, None::<&str>)" not in rust_source
    assert ".reveal_item_in_dir(path)" not in rust_source


def test_tauri_select_commands_register_user_selected_paths() -> None:
    rust_source = (
        ROOT / "apps" / "desktop-tauri" / "src-tauri" / "src" / "lib.rs"
    ).read_text(encoding="utf-8")
    cargo_source = (
        ROOT / "apps" / "desktop-tauri" / "src-tauri" / "Cargo.toml"
    ).read_text(encoding="utf-8")

    assert (
        "fn select_drawing_file(app: tauri::AppHandle, open_paths: tauri::State<OpenPathAllowlist>)"
        in rust_source
    )
    assert (
        "fn select_output_dir(app: tauri::AppHandle, open_paths: tauri::State<OpenPathAllowlist>)"
        in rust_source
    )
    assert (
        "fn select_component_drawings(app: tauri::AppHandle, open_paths: tauri::State<OpenPathAllowlist>)"
        in rust_source
    )
    assert '.add_filter("图纸文件", &["pdf", "png", "jpg", "jpeg"])' in rust_source
    assert ".blocking_pick_file()" in rust_source
    assert ".blocking_pick_folder()" in rust_source
    assert ".blocking_pick_files()" in rust_source
    assert "remember_allowed_path(&open_paths" in rust_source
    assert "dunce" not in cargo_source
    assert "path-clean" not in cargo_source


def test_settings_page_exposes_ai_service_config_controls() -> None:
    page_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "SettingsPage.tsx"
    ).read_text(encoding="utf-8")
    client_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "api" / "client.ts"
    ).read_text(encoding="utf-8")
    types_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "api" / "types.ts"
    ).read_text(encoding="utf-8")

    assert 'title="AI"' in page_source
    assert "覆盖桌面端 AI 服务地址、API Key 和模型名" in page_source
    assert "保存 AI 配置" in page_source
    assert "清除自定义" in page_source
    assert "已被环境变量接管" in page_source
    assert "已自定义" in page_source
    assert "https://allincode.top" in page_source
    assert "已配置请留空保持不变" in page_source
    assert "未配置则填入" in page_source
    assert "gpt-5.5" in page_source
    assert "type=\"password\"" in page_source
    assert "updateAiConfig" in client_source
    assert '"/api/settings/ai-config"' in client_source
    assert "base_url_override" in types_source
    assert "api_key_override_set" in types_source
    assert "model_override" in types_source
    assert "base_url_locked_by_env" in types_source
    assert "api_key_locked_by_env" in types_source
    assert "model_locked_by_env" in types_source
    assert "AIConfigUpdatePayload" in types_source


def test_tauri_build_script_does_not_pollute_real_sidecar_internal_dir() -> None:
    build_script = (
        ROOT / "apps" / "desktop-tauri" / "src-tauri" / "build.rs"
    ).read_text(encoding="utf-8")

    assert "if !internal.exists()" in build_script
    assert "if is_empty_dir(&internal)" in build_script
    assert "fn is_empty_dir" in build_script


def test_release_npm_script_rebuilds_sidecar_before_nsis() -> None:
    package_source = (ROOT / "apps" / "desktop-tauri" / "package.json").read_text(
        encoding="utf-8"
    )
    release_script = (ROOT / "scripts" / "build_release.ps1").read_text(encoding="utf-8")

    assert '"tauri:nsis:unsigned": "tauri build --ci --no-sign --bundles nsis"' in package_source
    assert '"tauri:nsis:signed": "tauri build --ci --bundles nsis"' in package_source
    assert (
        '"release:nsis": "powershell -ExecutionPolicy Bypass -File '
        '..\\\\..\\\\scripts\\\\build_release.ps1 -Channel Internal"'
        in package_source
    )
    assert "npm run tauri:nsis:unsigned" in release_script
    assert "npm run tauri:nsis:signed -- --config $temporarySigningConfig" in release_script
    assert '& "$PSScriptRoot\\build_sidecar.ps1"' in release_script
    assert '$repo = Split-Path -Parent $PSScriptRoot' in release_script
    assert 'dist\\build\\out' in release_script
    assert '$installerName = "$($tauriConfig.productName)_$($tauriConfig.version)_x64-setup.exe"' in release_script
    assert 'Copy-Item -Force $expectedInstaller (Join-Path $releaseOut $installerName)' in release_script


def test_sidecar_injected_token_is_redacted_by_testable_helper() -> None:
    rust_source = (ROOT / "apps" / "desktop-tauri" / "src-tauri" / "src" / "lib.rs").read_text(
        encoding="utf-8"
    )

    assert "fn redact_sidecar_log" in rust_source
    assert 'text.replace(token, "***REDACTED***")' in rust_source
    assert "fn sidecar_log_redacts_injected_token" in rust_source


def test_workbench_pfd_columns_follow_normal_apqp_process_flow_content() -> None:
    table_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "components" / "WorkbenchTable.tsx"
    ).read_text(encoding="utf-8")
    page_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "ThreeTableWorkbench.tsx"
    ).read_text(encoding="utf-8")

    assert 'rawColumn("sequence", "工序编号"' in table_source
    assert 'rawColumn("flow_symbol", "流程符号"' in table_source
    assert 'rawColumn("process", "工序名称"' in table_source
    assert 'rawColumn("process_function", "过程功能"' in table_source
    assert 'rawColumn("equipment", "设备/工装"' in table_source
    assert 'rawColumn("product_characteristic", "产品特性"' in table_source
    assert 'rawColumn("process_characteristic", "过程特性"' in table_source
    assert 'rawColumn("special_characteristic", "特殊特性"' in table_source
    assert 'header: "复核状态"' in table_source
    assert '"输入"' not in table_source
    assert '"输出"' not in table_source
    assert "input_material" not in table_source
    assert "output_result" not in table_source
    assert "input_material" not in page_source
    assert "output_result" not in page_source


def test_workbench_pfd_special_characteristic_display_filters_ptc_candidates() -> None:
    table_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "components" / "WorkbenchTable.tsx"
    ).read_text(encoding="utf-8")
    display_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "state" / "special-characteristic-display.ts"
    ).read_text(encoding="utf-8")
    types_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "api" / "types.ts"
    ).read_text(encoding="utf-8")

    assert "specialCharacteristicColumnText" in table_source
    assert "specialCharacteristicColumnText" in display_source
    assert "sanitizeSpecialCharacteristicDisplay" in display_source
    assert "AI裁判" not in display_source
    assert "return `候选待确认" not in display_source
    assert "special_characteristic_judgments" not in table_source
    assert "special_characteristic_candidates" not in table_source
    assert "special_characteristic_judgments" in types_source
    assert "PTC候选" in display_source
    assert "特殊特性候选" in display_source


def test_workbench_surfaces_declared_special_count_mismatch() -> None:
    (
        ROOT / "apps" / "desktop-tauri" / "src" / "components" / "WorkbenchTable.tsx"
    ).read_text(encoding="utf-8")
    display_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "state" / "special-characteristic-display.ts"
    ).read_text(encoding="utf-8")
    types_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "api" / "types.ts"
    ).read_text(encoding="utf-8")
    store_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "state" / "workbench-store.ts"
    ).read_text(encoding="utf-8")

    assert "declared_special_characteristics" in types_source
    assert "declared_totals" in types_source
    assert "special_characteristic_locations" in types_source
    assert "special_characteristic_discovery" in types_source
    assert "extra_counts?: DeclaredSpecialTotals" in types_source
    assert "risks?: Record<string, unknown>[]" in types_source
    assert "SpecialCharacteristicSearchCoverage" in types_source
    assert "声明CC" in display_source
    assert "声明SC" in display_source
    assert "缺少CC" in display_source
    assert "缺少SC" in display_source
    assert "specialCharacteristicCount" in display_source
    assert "Number.isFinite(count)" in display_source
    assert 'if (declaredCc <= 0 && declaredSc <= 0) return "";' in display_source
    assert "declaredParts.push(`声明CC=${declaredCc}`)" in display_source
    assert "declaredParts.push(`声明SC=${declaredSc}`)" in display_source
    assert "`声明CC=${declaredCc}/SC=${declaredSc}`" not in display_source
    assert "if (declaredCc > 0 && missingCc > 0)" in display_source
    assert "if (declaredSc > 0 && missingSc > 0)" in display_source
    assert "SPCC" in display_source
    assert "formatDeclaredSpecialDiscovery(row.raw)" not in display_source
    assert "drawingAnalysisContextFromResult" not in store_source
    assert "const drawingAnalysis = asRecord(result.drawing_analysis)" not in store_source
    assert "raw: { ...row }" in store_source


def test_workbench_store_does_not_smear_drawing_special_fields_into_rows() -> None:
    store_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "state" / "workbench-store.ts"
    ).read_text(encoding="utf-8")

    for field in (
        "special_characteristic_judgments",
        "declared_special_characteristics",
        "declared_totals",
        "special_characteristic_locations",
        "special_characteristic_discovery",
    ):
        assert f'"{field}"' not in store_source

    assert "function drawingAnalysisContextFromResult" not in store_source
    assert "const drawingAnalysisContext = drawingAnalysisContextFromResult(result);" not in store_source
    assert "raw: { ...row }" in store_source
    assert "raw: row" not in store_source


def test_workbench_special_characteristic_display_priority_and_guards() -> None:
    display_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "state" / "special-characteristic-display.ts"
    ).read_text(encoding="utf-8")
    table_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "components" / "WorkbenchTable.tsx"
    ).read_text(encoding="utf-8")

    body = display_source[
        display_source.index("export function specialCharacteristicColumnText") :
    ]

    assert body.index("formatFormalSpecialCharacteristic") < body.index("formatConfirmedAiJudgment")
    assert "formatPendingCandidate" not in body
    assert "formatDeclaredSpecialDiscovery" not in body
    assert "const specialCharacteristicDiscovery = asRecord(raw.special_characteristic_discovery);" in display_source
    assert (
        "const declaredTotals = asRecord(raw.declared_totals) ?? "
        "asRecord(specialCharacteristicDiscovery?.declared_totals);"
        in display_source
    )
    assert r"if (/^SPCC(?:$|-|:|\uFF1A)/i.test(trimmed))" in display_source
    assert "if (rawClassification && !classification) return \"\";" in display_source
    assert (
        (
            'rawColumn("special_characteristics", "特殊特性", '
            '["special_characteristics", "special_characteristic", '
            '"special_characteristic_class", "classification"], undefined, '
            'specialCharacteristicColumnText)'
        )
        in table_source
    )
    assert (
        (
            'rawColumn("special_characteristic_class", "特殊特性分类", '
            '["special_characteristic_class", "classification", '
            '"special_characteristics"], undefined, specialCharacteristicColumnText)'
        )
        in table_source
    )


def test_workbench_special_characteristic_display_runtime_contract(tmp_path: Path) -> None:
    desktop_root = ROOT / "apps" / "desktop-tauri"
    esbuild = desktop_root / "node_modules" / ".bin" / "esbuild.cmd"
    if not esbuild.exists():
        esbuild = desktop_root / "node_modules" / ".bin" / "esbuild"

    script = tmp_path / "workbench-special-characteristics-contract.ts"
    bundle = tmp_path / "workbench-special-characteristics-contract.mjs"
    script.write_text(
        f"""
import assert from "node:assert/strict";
import {{ rowsFromResult }} from "{(desktop_root / "src" / "state" / "workbench-store.ts").as_posix()}";
import {{
  formatDeclaredSpecialDiscovery,
  specialCharacteristicColumnText,
  specialCharacteristicCount,
}} from "{(desktop_root / "src" / "state" / "special-characteristic-display.ts").as_posix()}";

const result = {{
  drawing_analysis: {{
    special_characteristic_judgments: [
      {{ classification: "CC", verdict: "confirmed", linked_feature: "global hole" }},
    ],
    declared_special_characteristics: [
      {{ classification: "CC", expected_count: 2 }},
      {{ classification: "SC", expected_count: 1 }},
    ],
    declared_totals: {{ CC: "2", SC: 1 }},
    special_characteristic_locations: [],
    special_characteristic_discovery: {{
      missing_counts: {{ CC: "1", SC: 1, PTC: 9 }},
    }},
  }},
  process_flow: {{
    steps: [
      {{ process_step_id: "P1", operation: "press" }},
      {{ process_step_id: "P2", operation: "row override", declared_totals: {{ CC: 5, SC: 0 }} }},
    ],
  }},
  pfmea: {{ rows: [{{ pfmea_id: "PF1", failure_mode: "crack" }}] }},
  control_plan: {{ rows: [{{ control_plan_id: "CP1", special_characteristic_class: "SPCC" }}] }},
}};

const rows = rowsFromResult(result);
assert.equal(rows.length, 4);
for (const row of rows) {{
  assert.ok(!("special_characteristic_judgments" in row.raw));
  assert.ok(!("declared_special_characteristics" in row.raw));
  assert.ok(!("special_characteristic_locations" in row.raw));
  assert.ok(!("special_characteristic_discovery" in row.raw));
}}
assert.equal(rows[0].raw.declared_totals, undefined);
assert.deepEqual(rows[1].raw.declared_totals, {{ CC: 5, SC: 0 }});
assert.equal(specialCharacteristicColumnText(rows[0]), "-");
assert.equal(specialCharacteristicColumnText(rows[1]), "-");

assert.equal(
  specialCharacteristicColumnText({{ raw: {{
    special_characteristics: [{{ classification: "SC", linked_feature: "diameter" }}],
    special_characteristic_judgments: [{{
      classification: "CC", verdict: "confirmed", linked_feature: "hole",
    }}],
  }} }}),
  "SC / diameter",
);
assert.equal(
  specialCharacteristicColumnText({{ raw: {{
    special_characteristics: ["CC: 右下角视图中的孔特征，星形符号，图纸声明CC 2个"],
  }} }}),
  "CC / 右下角视图中的孔特征，星形符号",
);
assert.equal(
  specialCharacteristicColumnText({{ raw: {{ special_characteristics: ["SC候选: 三角形符号 / 槽"] }} }}),
  "-",
);
assert.equal(
  specialCharacteristicColumnText({{ raw: {{
    special_characteristic_judgments: [{{
      classification: "CC", verdict: "confirmed", linked_feature: "hole",
    }}],
  }} }}),
  "CC / hole",
);
assert.equal(
  specialCharacteristicColumnText({{ raw: {{
    special_characteristic_candidates: [
      {{ candidate_type: "PTC", linked_feature: "ignore" }},
      {{ candidate_type: "SC", symbol_text_or_shape: "SC", linked_feature: "slot" }},
    ],
  }} }}),
  "-",
);
assert.equal(
  specialCharacteristicColumnText({{ raw: {{
    declared_totals: {{ CC: "2", SC: 0 }},
    special_characteristic_discovery: {{ missing_counts: {{ CC: "1", SC: "3" }} }},
  }} }}),
  "-",
);
assert.equal(
  formatDeclaredSpecialDiscovery({{ special_characteristic_discovery: {{
    declared_totals: {{ CC: 0, SC: "3" }},
    missing_counts: {{ CC: 2, SC: "1" }},
  }} }}),
  "声明SC=3, 缺少SC=1",
);
assert.equal(specialCharacteristicColumnText({{ raw: {{ classification: "SPCC" }} }}), "-");
assert.equal(specialCharacteristicColumnText({{ raw: {{ classification: "PTC" }} }}), "-");
assert.equal(specialCharacteristicColumnText({{ raw: {{ classification: "SC" }} }}), "SC");
assert.equal(specialCharacteristicCount(undefined), 0);
assert.equal(specialCharacteristicCount(null), 0);
assert.equal(specialCharacteristicCount("NaN"), 0);
assert.equal(specialCharacteristicCount("2.9"), 2);
""",
        encoding="utf-8",
    )

    subprocess.run(
        [
            str(esbuild),
            str(script),
            "--bundle",
            "--platform=node",
            "--format=esm",
            f"--outfile={bundle}",
        ],
        cwd=desktop_root,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(["node", str(bundle)], cwd=desktop_root, check=True, capture_output=True, text=True)


def test_exports_use_normal_process_flow_headers() -> None:
    split_source = (
        ROOT / "minos_core" / "exporters" / "three_table_workbooks.py"
    ).read_text(encoding="utf-8")
    workbook_source = (
        ROOT / "minos_core" / "exporters" / "apqp_workbook.py"
    ).read_text(encoding="utf-8")

    for source in (split_source, workbook_source):
        assert "工序编号" in source
        assert "流程符号" in source
        assert "工序名称" in source
        assert "过程功能" in source
        assert "设备/工装" in source
        assert "产品特性" in source
        assert "过程特性" in source
        assert "特殊特性" in source


def test_workbench_cp_columns_show_process_controls_separate_from_result_checks() -> None:
    table_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "components" / "WorkbenchTable.tsx"
    ).read_text(encoding="utf-8")
    table_editor_source = (ROOT / "minos_desktop" / "table_editor" / "specs.py").read_text(encoding="utf-8")

    for source in (table_source, table_editor_source):
        assert "过程参数" in source
        assert "参数规格" in source
        assert "过程控制方法" in source
        assert "首件/换型确认" in source
        assert "防错装置" in source
        assert "防错验证" in source
        assert "过程记录" in source

    assert 'rawColumn("process_parameter", "过程参数"' in table_source
    assert 'rawColumn("parameter_specification", "参数规格"' in table_source
    assert 'rawColumn("process_control_method", "过程控制方法"' in table_source
    assert 'rawColumn("setup_verification", "首件/换型确认"' in table_source
    assert 'rawColumn("poka_yoke_device", "防错装置"' in table_source
    assert 'rawColumn("poka_yoke_verification", "防错验证"' in table_source
    assert 'rawColumn("process_record", "过程记录"' in table_source


def test_review_closure_happens_after_control_plan_with_human_priority() -> None:
    page_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "ReviewClosurePage.tsx"
    ).read_text(encoding="utf-8")
    service_source = (
        ROOT / "minos_desktop" / "services" / "run_chain_service.py"
    ).read_text(encoding="utf-8")
    edit_service_source = (
        ROOT / "minos_desktop" / "services" / "run_edit_service.py"
    ).read_text(encoding="utf-8")
    review_source = (ROOT / "minos_core" / "automation_review.py").read_text(encoding="utf-8")

    assert "评审任务收件箱" in page_source
    assert "AI 只提供线索，人工判断优先" in page_source
    assert "批量确认低风险 AI 项" not in page_source
    assert "build_automation_review(current)" in service_source
    assert 'current["automation_review"]' in service_source
    assert "_can_apply_after_control_plan_automation_review(current)" in edit_service_source
    assert '"review_stage": "after_control_plan"' in review_source
    assert '"human_decision_priority": True' in review_source


def test_workbench_clean_editing_surface_contract() -> None:
    page_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "ThreeTableWorkbench.tsx"
    ).read_text(encoding="utf-8")
    table_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "components" / "WorkbenchTable.tsx"
    ).read_text(encoding="utf-8")

    assert "<ChainStepper" in page_source
    assert 'compact' in page_source
    assert 'title="阶段"' in page_source
    assert "三表编辑画布" in page_source
    assert "底部批量操作条" not in page_source
    assert "浮动上下文工具条" in table_source
    assert "editingCell" in table_source
    assert "draftChanges" in table_source
    assert "selectedRowIds" in table_source
    assert "activeRowId" in table_source
    assert "onSaveDrafts" in table_source
    assert "onSoftDeleteRows" in table_source
    assert "onMarkRowsForReview" in table_source
    assert "onJumpToRow" in page_source
    assert "position:absolute" in table_source or "absolute" in table_source


def test_workbench_removes_right_inspector_panel_and_keeps_preview_summary() -> None:
    app_source = (ROOT / "apps" / "desktop-tauri" / "src" / "App.tsx").read_text(encoding="utf-8")
    shell_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "components" / "AppShell.tsx"
    ).read_text(encoding="utf-8")
    page_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "ThreeTableWorkbench.tsx"
    ).read_text(encoding="utf-8")
    table_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "components" / "WorkbenchTable.tsx"
    ).read_text(encoding="utf-8")
    preview_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "components" / "PreviewRail.tsx"
    ).read_text(encoding="utf-8")
    diagram_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "components" / "PfdFlowDiagram.tsx"
    ).read_text(encoding="utf-8")
    display_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "state" / "workbench-display.ts"
    ).read_text(encoding="utf-8")

    assert "riskLabel" in table_source
    assert "rowStatusLabel" in table_source
    assert "InspectorPanel" not in app_source
    assert "inspector=" not in app_source
    assert "inspector:" not in shell_source
    assert "{inspector}" not in shell_source
    assert "grid-cols-[236px_minmax(620px,1fr)_300px]" not in shell_source
    assert "grid-cols-[220px_minmax(0,1fr)]" in shell_source
    assert "当前行上下文" in preview_source
    assert "跳转链路" in preview_source
    assert "tableLabel" in preview_source
    assert "<PreviewRail" in page_source
    assert "确认全部过程流程图" in page_source
    assert "pfdConfirmSummary" in page_source
    assert "待确认" in page_source and "已确认" in page_source
    assert 'code: "加工"' in diagram_source
    assert 'code: "检验"' in diagram_source
    assert 'medium: "中风险"' in display_source
    assert 'approved: "已确认"' in display_source


def test_workbench_soft_delete_can_be_undone_and_pfd_diagram_uses_visible_rows() -> None:
    page_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "ThreeTableWorkbench.tsx"
    ).read_text(encoding="utf-8")
    store_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "state" / "workbench-store.ts"
    ).read_text(encoding="utf-8")

    assert "lastSoftDeletedRows" in page_source
    assert "softDeletedRowsFromResult" in page_source
    assert "restorableSoftDeletedRows" in page_source
    assert "undoSoftDeleteRows" in page_source
    assert "已软删除" in page_source
    assert 'action: "update"' in page_source
    assert "deleted: false" in page_source
    assert "soft_deleted: false" in page_source
    assert "processFlowStepsFromRows" in page_source
    assert "processFlowStepsFromRows" in store_source
    assert "softDeletedRowsFromResult" in store_source
    assert "visiblePfdRows" in page_source


def test_desktop_sidecar_starts_without_windows_console_window() -> None:
    rust_source = (
        ROOT / "apps" / "desktop-tauri" / "src-tauri" / "src" / "lib.rs"
    ).read_text(encoding="utf-8")
    spec_source = (ROOT / "minos-desktop-api.spec").read_text(encoding="utf-8")

    assert ".sidecar(SIDECAR_NAME)" in rust_source
    assert 'const SIDECAR_NAME: &str = "minos-desktop-api";' in rust_source
    assert "console=False" in spec_source
    assert 'name="minos-desktop-api-x86_64-pc-windows-msvc"' in spec_source


def test_desktop_sidecar_uses_owned_port_instead_of_stale_8000() -> None:
    rust_source = (
        ROOT / "apps" / "desktop-tauri" / "src-tauri" / "src" / "lib.rs"
    ).read_text(encoding="utf-8")

    assert "SidecarProcess" in rust_source
    assert "find_available_sidecar_port" in rust_source
    assert "format!(\"http://127.0.0.1:{}\", port)" in rust_source
    assert "if is_api_port_open() {\n        return false;" not in rust_source
    assert 'arg("8000")' not in rust_source
    assert "unwrap_or(SIDECAR_PORT_START)" not in rust_source


def test_desktop_sidecar_owns_only_the_child_it_spawned() -> None:
    rust_source = (
        ROOT / "apps" / "desktop-tauri" / "src-tauri" / "src" / "lib.rs"
    ).read_text(encoding="utf-8")

    assert "taskkill" not in rust_source
    assert "pkill" not in rust_source
    assert "kill_stale_sidecars" not in rust_source
    assert "let pid = child.pid();" in rust_source
    assert "current.pid == pid" in rust_source


def test_desktop_sidecar_readiness_is_authenticated_and_requires_healthy_body() -> None:
    rust_source = (
        ROOT / "apps" / "desktop-tauri" / "src-tauri" / "src" / "lib.rs"
    ).read_text(encoding="utf-8")

    assert '"GET /api/health HTTP/1.1\\r\\nHost:' in rust_source
    assert "Authorization: Bearer {token}" in rust_source
    assert "HTTP/1.1 200" in rust_source
    assert 'body.contains("\\\"ok\\\":true")' in rust_source
    assert 'body.contains("\\\"status\\\":\\\"ok\\\"")' in rust_source
    assert "Err(\"Sidecar readiness timed out\".to_string())" in rust_source
    assert "fn get_bootstrap(app: tauri::AppHandle) -> Result<BootstrapPayload, String>" in rust_source


def test_desktop_sidecar_serializes_lifecycle_and_registers_close_listener_once() -> None:
    rust_source = (
        ROOT / "apps" / "desktop-tauri" / "src-tauri" / "src" / "lib.rs"
    ).read_text(encoding="utf-8")
    ensure_source = rust_source[
        rust_source.index("fn ensure_sidecar_running") : rust_source.index("fn generate_api_token")
    ]

    assert "let mut guard = process_slot.lock()" in ensure_source
    assert "*process_state.borrow_mut() = Some(SidecarProcess" in ensure_source
    assert ensure_source.count("tauri://close-requested") == 0
    assert rust_source.count("tauri://close-requested") == 1
    assert ".setup(|app|" in rust_source


def test_desktop_sidecar_prefers_explicit_e2e_token_before_generating_one() -> None:
    rust_source = (
        ROOT / "apps" / "desktop-tauri" / "src-tauri" / "src" / "lib.rs"
    ).read_text(encoding="utf-8")

    assert '"MINOS_DESKTOP_API_TOKEN").unwrap_or_else(|_| generate_api_token())' in rust_source


def test_special_characteristic_regex_does_not_emit_tailwind_arbitrary_property() -> None:
    source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "state" / "special-characteristic-display.ts"
    ).read_text(encoding="utf-8")

    assert "[-:：]" not in source
    assert r"/^PTC(?:$|-|:|\uFF1A)/i" in source
    assert r"/^SPCC(?:$|-|:|\uFF1A)/i" in source


def test_desktop_binary_uses_windows_gui_subsystem_in_release() -> None:
    main_source = (
        ROOT / "apps" / "desktop-tauri" / "src-tauri" / "src" / "main.rs"
    ).read_text(encoding="utf-8")

    assert "windows_subsystem = \"windows\"" in main_source
    assert "not(debug_assertions)" in main_source


def test_workbench_uses_pfd_flow_diagram_for_standard_process_fields() -> None:
    page_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "ThreeTableWorkbench.tsx"
    ).read_text(encoding="utf-8")
    component_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "components" / "PfdFlowDiagram.tsx"
    ).read_text(encoding="utf-8")
    store_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "state" / "workbench-store.ts"
    ).read_text(encoding="utf-8")
    types_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "api" / "types.ts"
    ).read_text(encoding="utf-8")

    assert 'import { PfdFlowDiagram } from "../components/PfdFlowDiagram";' in page_source
    assert "<PfdFlowDiagram" in page_source
    assert 'filters.table === "pfd"' in page_source
    assert "processFlowStepsFromRows" in page_source
    assert "processFlowStepsFromRows" in store_source
    assert "next_step_ids" in component_source
    assert "input_material" in component_source
    assert "output_result" in component_source
    assert "flow_symbol" in component_source
    assert "flow_type" in component_source
    assert "operation_type" in component_source
    assert "ProcessFlowStep" in types_source


def test_pfd_flow_diagram_uses_standard_symbol_meta_and_display_label() -> None:
    component_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "components" / "PfdFlowDiagram.tsx"
    ).read_text(encoding="utf-8")

    assert "FLOW_SYMBOL_META" in component_source
    assert "operation" in component_source
    assert "inspection" in component_source
    assert "transport" in component_source
    assert "storage" in component_source
    assert "rework" in component_source
    assert "outsourced" in component_source
    assert "flow_type_display" in component_source


def test_pfd_flow_diagram_renders_next_step_topology_edges() -> None:
    component_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "components" / "PfdFlowDiagram.tsx"
    ).read_text(encoding="utf-8")

    assert "buildProcessFlowLayout" in component_source
    assert "ProcessFlowEdge" in component_source
    assert "<svg" in component_source
    assert "<marker" in component_source
    assert "data-edge-kind" in component_source
    assert any(edge_kind in component_source for edge_kind in ("branch", "backlink", "rework"))
    assert "index < steps.length - 1" not in component_source
