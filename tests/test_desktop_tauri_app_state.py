from __future__ import annotations

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
    assert "updatedRun?.raw_result?.chain_stages ?? updatedRun?.current_result?.chain_stages" not in page_source
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
    assert '["special_characteristics", "special_characteristic", "special_characteristic_class", "classification"]' in table_source
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
    assert "setTimeout(connect" in sse_source
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
    assert "https://cx.allincoding.cc" in page_source
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

    assert '"tauri:nsis": "tauri build --ci --no-sign --bundles nsis"' in package_source
    assert '"release:nsis": "powershell -ExecutionPolicy Bypass -File ..\\\\..\\\\scripts\\\\build_sidecar.ps1 && npm run tauri:nsis"' in package_source
    assert "npm run tauri:nsis" in release_script
    assert '$repo = Split-Path -Parent $PSScriptRoot' in release_script
    assert 'dist\\build\\out' in release_script
    assert 'Copy-Item -Force (Join-Path $nsisDir "*.exe") $releaseOut' in release_script


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
    table_editor_source = (ROOT / "minos_desktop" / "table_editor.py").read_text(encoding="utf-8")

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
    service_source = (ROOT / "minos_desktop" / "services.py").read_text(encoding="utf-8")
    review_source = (ROOT / "minos_core" / "automation_review.py").read_text(encoding="utf-8")

    assert "评审任务收件箱" in page_source
    assert "AI 只提供线索，人工判断优先" in page_source
    assert "批量确认低风险 AI 项" not in page_source
    assert "build_automation_review(current)" in service_source
    assert 'current["automation_review"]' in service_source
    assert "_can_apply_after_control_plan_automation_review(current)" in service_source
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

    assert "app.shell().sidecar(SIDECAR_NAME)" in rust_source
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
