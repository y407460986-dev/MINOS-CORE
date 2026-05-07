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
    assert 'selectedRow.table !== "pfd"' in page_source
    assert 'selectedRow.table !== "pfd" || !hasRun || isSaving' in page_source
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
    assert "正在确认 PFD，PFMEA 将在后台生成" in page_source
    assert "getRun" in page_source
    assert "window.setInterval" in page_source
    assert "export function getRun" in client_source


def test_workbench_clean_editing_surface_contract() -> None:
    page_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "pages" / "ThreeTableWorkbench.tsx"
    ).read_text(encoding="utf-8")
    table_source = (
        ROOT / "apps" / "desktop-tauri" / "src" / "components" / "WorkbenchTable.tsx"
    ).read_text(encoding="utf-8")

    assert "compactChainStages" in page_source
    assert "三表编辑画布" in page_source
    assert "底部批量操作条" not in page_source
    assert "浮动上下文工具条" in table_source
    assert "editingCell" in table_source
    assert "draftChanges" in table_source
    assert "selectedRowIds" in table_source
    assert "onSaveDrafts" in table_source
    assert "onSoftDeleteRows" in table_source
    assert "onMarkRowsForReview" in table_source
    assert "position:absolute" in table_source or "absolute" in table_source


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
