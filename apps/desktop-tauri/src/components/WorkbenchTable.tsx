import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";
import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent, type PointerEvent, type ReactNode } from "react";
import type { TableKind, WorkbenchRow } from "../api/types";
import { riskLabel, rowStatusLabel } from "../state/workbench-display";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { ArrowDown, ArrowUp, ClipboardCheck, GripVertical, Plus, RotateCcw, Save, Trash2 } from "lucide-react";
import { StickyHorizontalScrollbar } from "./StickyHorizontalScrollbar";
import { useDragScroll } from "../hooks/useDragScroll";
import { specialCharacteristicColumnText } from "../state/special-characteristic-display";

type DraftCell = {
  rowId: string;
  field: string;
};

type DraftChange = {
  row: WorkbenchRow;
  field: string;
  value: string;
};

export type PfdNewRowDraft = {
  process_step_id: string;
  operation: string;
  operation_type: string;
  process_function: string;
  equipment: string;
  product_characteristic: string;
  process_characteristic: string;
  special_characteristic: string;
  responsibility: string;
};

type WorkbenchColumnDef = ColumnDef<WorkbenchRow> & {
  editableField?: string;
};

type RawColumnFormatter = (row: WorkbenchRow, fields: string[]) => string;

type TableWorkspaceState = {
  activeRowId: string | null;
  editingCell: DraftCell | null;
  draftChanges: Record<string, string>;
  selectedRowIds: Record<string, boolean>;
  isAddingPfdRow: boolean;
  pfdDraft: PfdNewRowDraft;
};

const emptyPfdDraft: PfdNewRowDraft = {
  process_step_id: "",
  operation: "",
  operation_type: "",
  process_function: "",
  equipment: "",
  product_characteristic: "",
  process_characteristic: "",
  special_characteristic: "",
  responsibility: ""
};

function createTableWorkspaceState(): TableWorkspaceState {
  return {
    activeRowId: null,
    editingCell: null,
    draftChanges: {},
    selectedRowIds: {},
    isAddingPfdRow: false,
    pfdDraft: { ...emptyPfdDraft }
  };
}

function createInitialTableWorkspaceState(): Record<TableKind, TableWorkspaceState> {
  return {
    pfd: createTableWorkspaceState(),
    pfmea: createTableWorkspaceState(),
    cp: createTableWorkspaceState()
  };
}

function text(value: unknown, fallback = ""): string {
  if (Array.isArray(value)) return value.map((item) => text(item)).filter(Boolean).join(", ");
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function firstText(row: WorkbenchRow, fields: string[], fallback = "-"): string {
  for (const field of fields) {
    const value = text(row.raw[field]);
    if (value) return value;
  }
  return fallback;
}

function rawColumn(
  id: string,
  header: string,
  fields: string[],
  editableField?: string,
  valueFormatter?: RawColumnFormatter
): WorkbenchColumnDef {
  return {
    id,
    header,
    accessorFn: (row) => valueFormatter ? valueFormatter(row, fields) : firstText(row, fields),
    editableField,
  };
}

function columnsForTable(table: TableKind): WorkbenchColumnDef[] {
  if (table === "pfmea") {
    return [
      { ...rawColumn("id", "编号", ["pfmea_id"]), header: "编号" },
      { ...rawColumn("structure_process_item", "结构-过程项", ["structure_process_item", "process_item"]), header: "结构-过程项" },
      { ...rawColumn("structure_process_step", "结构-过程步骤", ["structure_process_step", "process_step_name", "operation", "process_step", "process_step_id"]), header: "结构-过程步骤" },
      { ...rawColumn("structure_work_element", "结构-工作要素", ["structure_work_element", "process_work_element", "work_element_4m"]), header: "结构-工作要素" },
      { ...rawColumn("function_process_item", "功能-过程项", ["function_process_item", "process_item"]), header: "功能-过程项" },
      { ...rawColumn("function_process_step", "功能-过程步骤", ["function_process_step", "function_requirement", "process_function"]), header: "功能-过程步骤" },
      { ...rawColumn("function_work_element", "功能-工作要素", ["function_work_element", "process_characteristics", "process_characteristic"]), header: "功能-工作要素" },
      { ...rawColumn("failure_effect", "失效后果", ["failure_effect", "effect"]), header: "失效后果" },
      { ...rawColumn("severity", "严重度", ["severity"]), header: "严重度" },
      { ...rawColumn("failure_mode", "失效模式", ["failure_mode"], "failure_mode"), header: "失效模式" },
      { ...rawColumn("failure_cause", "失效原因", ["failure_cause", "cause"], "failure_cause"), header: "失效原因" },
      { ...rawColumn("cause_process_parameter", "原因过程参数", ["cause_process_parameter"], "cause_process_parameter"), header: "原因过程参数" },
      { ...rawColumn("prevention_control", "预防控制", ["prevention_control", "current_prevention_control"], "prevention_control"), header: "预防控制" },
      { ...rawColumn("prevention_control_target", "预防控制对象", ["prevention_control_target"], "prevention_control_target"), header: "预防控制对象" },
      { ...rawColumn("prevention_control_timing", "预防控制时机", ["prevention_control_timing"], "prevention_control_timing"), header: "预防控制时机" },
      { ...rawColumn("occurrence", "发生度", ["occurrence"]), header: "发生度" },
      { ...rawColumn("detection_control", "探测控制", ["detection_control", "current_detection_control"], "detection_control"), header: "探测控制" },
      { ...rawColumn("detection_control_target", "探测对象", ["detection_control_target"], "detection_control_target"), header: "探测对象" },
      { ...rawColumn("detection_control_timing", "探测时机", ["detection_control_timing"], "detection_control_timing"), header: "探测时机" },
      { ...rawColumn("detection", "探测度", ["detection"]), header: "探测度" },
      { ...rawColumn("ap", "AP", ["action_priority", "ap"]), header: "AP" },
      { ...rawColumn("control_logic_review", "控制逻辑复核", ["control_logic_review"], "control_logic_review"), header: "控制逻辑复核" },
      { ...rawColumn("special_characteristics", "特殊特性", ["special_characteristics", "special_characteristic", "special_characteristic_class", "classification"], undefined, specialCharacteristicColumnText), header: "特殊特性" },
      { ...rawColumn("preventive_action", "预防措施", ["preventive_action"], "preventive_action"), header: "预防措施" },
      { ...rawColumn("detection_action", "探测措施", ["detection_action"], "detection_action"), header: "探测措施" },
      { ...rawColumn("responsible_person", "责任人", ["responsible_person", "responsibility", "owner"], "responsible_person"), header: "责任人" },
      { ...rawColumn("target_date", "目标日期", ["target_date"], "target_date"), header: "目标日期" },
      { accessorKey: "status", header: "状态", cell: ({ row }) => rowStatusLabel(row.original.status) },
    ];
  }

  if (table === "cp") {
    return [
      rawColumn("id", "编号", ["control_plan_id"]),
      rawColumn("process_step", "过程步骤", ["process_name", "process_step_name", "operation", "process_step", "process_step_id"]),
      rawColumn("pfmea_id", "PFMEA 来源", ["pfmea_id"]),
      rawColumn("characteristic", "产品/过程特性", ["product_process_characteristic", "product_characteristic", "process_characteristic"], "product_process_characteristic"),
      rawColumn("special_characteristic_class", "特殊特性分类", ["special_characteristic_class", "classification", "special_characteristics"], undefined, specialCharacteristicColumnText),
      rawColumn("specification", "规范/公差", ["specification_tolerance", "specification", "tolerance"], "specification_tolerance"),
      rawColumn("process_parameter", "过程参数", ["process_parameter"], "process_parameter"),
      rawColumn("parameter_specification", "参数规格", ["parameter_specification"], "parameter_specification"),
      rawColumn("process_control_method", "过程控制方法", ["process_control_method"], "process_control_method"),
      rawColumn("setup_verification", "首件/换型确认", ["setup_verification"], "setup_verification"),
      rawColumn("poka_yoke_device", "防错装置", ["poka_yoke_device"], "poka_yoke_device"),
      rawColumn("poka_yoke_verification", "防错验证", ["poka_yoke_verification"], "poka_yoke_verification"),
      rawColumn("process_record", "过程记录", ["process_record", "record_form"], "process_record"),
      rawColumn("method", "测量方法", ["measurement_method", "evaluation_measurement_technique"], "measurement_method"),
      rawColumn("frequency", "频次", ["sample_frequency", "frequency"], "sample_frequency"),
      rawColumn("control_method", "控制方法", ["control_method"], "control_method"),
      rawColumn("reaction_plan", "反应计划", ["reaction_plan"], "reaction_plan"),
      { accessorKey: "status", header: "状态", cell: ({ row }) => rowStatusLabel(row.original.status) },
      rawColumn("owner", "责任", ["owner", "responsibility"], "responsibility"),
    ];
  }

  return [
    rawColumn("sequence", "工序编号", ["sequence", "operation_no", "process_step_id"]),
    rawColumn("flow_symbol", "流程符号", ["flow_type_display", "flow_symbol", "flow_type", "operation_type"], "operation_type"),
    rawColumn("process", "工序名称", ["operation", "process_step", "process_step_name"], "operation"),
    rawColumn("process_function", "过程功能", ["process_function", "description"], "process_function"),
    rawColumn("equipment", "设备/工装", ["equipment", "machine", "tooling"], "equipment"),
    rawColumn("product_characteristic", "产品特性", ["product_characteristic", "product_characteristics"], "product_characteristic"),
    rawColumn("process_characteristic", "过程特性", ["process_characteristic", "process_characteristics"], "process_characteristic"),
    rawColumn("special_characteristic", "特殊特性", ["special_characteristics", "special_characteristic", "special_characteristic_class", "classification"], undefined, specialCharacteristicColumnText),
    rawColumn("owner", "责任", ["owner", "responsibility"], "responsibility"),
    { accessorKey: "status", header: "复核状态", cell: ({ row }) => rowStatusLabel(row.original.status) },
  ];
}

export function columnsForRows(rows: WorkbenchRow[], fallbackTable: TableKind = "pfd"): WorkbenchColumnDef[] {
  const table = rows.find(Boolean)?.table ?? fallbackTable;
  return columnsForTable(table);
}

type WorkbenchTableProps = {
  rows: WorkbenchRow[];
  table: TableKind;
  selectedRow: WorkbenchRow | null;
  onSelectRow: (row: WorkbenchRow) => void;
  onSaveDrafts?: (changes: DraftChange[]) => Promise<void> | void;
  onAddPfdRow?: (row: PfdNewRowDraft) => Promise<boolean | void> | boolean | void;
  onReorderPfdRows?: (rows: WorkbenchRow[]) => Promise<void> | void;
  canReorderRows?: boolean;
  onSoftDeleteRows?: (rows: WorkbenchRow[]) => Promise<void> | void;
  onMarkRowsForReview?: (rows: WorkbenchRow[]) => Promise<void> | void;
  busy?: boolean;
};

export function WorkbenchTable({
  rows,
  table: tableKind,
  selectedRow,
  onSelectRow,
  onSaveDrafts,
  onAddPfdRow,
  onReorderPfdRows,
  canReorderRows = true,
  onSoftDeleteRows,
  onMarkRowsForReview,
  busy = false
}: WorkbenchTableProps) {
  const [tableStateByKind, setTableStateByKind] = useState<Record<TableKind, TableWorkspaceState>>(createInitialTableWorkspaceState);
  const [draggedRowId, setDraggedRowId] = useState<string | null>(null);
  const draggedRowIdRef = useRef<string | null>(null);
  const pointerDragRowIdRef = useRef<string | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Shift+drag to scroll horizontally (like Figma)
  useDragScroll(scrollContainerRef, { requireShiftKey: true });

  // Keyboard shortcuts for horizontal scrolling
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "ArrowLeft") { el.scrollLeft -= e.shiftKey ? 200 : 50; e.preventDefault(); }
      if (e.key === "ArrowRight") { el.scrollLeft += e.shiftKey ? 200 : 50; e.preventDefault(); }
      if (e.key === "Home") { el.scrollLeft = 0; e.preventDefault(); }
      if (e.key === "End") { el.scrollLeft = el.scrollWidth; e.preventDefault(); }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);
  const columns = useMemo(() => columnsForRows(rows, tableKind), [rows, tableKind]);
  const table = useReactTable({
    data: rows,
    columns,
    getRowId: (row) => row.rowId,
    getCoreRowModel: getCoreRowModel(),
  });
  const tableState = tableStateByKind[tableKind];
  const { editingCell, draftChanges, selectedRowIds, isAddingPfdRow, pfdDraft } = tableState;
  const visibleRows = table.getRowModel().rows.map((row) => row.original);
  const activeRow = visibleRows.find((row) => row.rowId === tableState.activeRowId) ?? null;
  const selectedRows = useMemo(
    () => visibleRows.filter((row) => selectedRowIds[row.rowId]),
    [selectedRowIds, visibleRows]
  );
  const draftEntries = useMemo(() => {
    return Object.entries(draftChanges)
      .map(([key, value]) => {
        const [rowId, field] = key.split("::");
        const row = rows.find((item) => item.rowId === rowId);
        return row && field ? { row, field, value } : null;
      })
      .filter(Boolean) as DraftChange[];
  }, [draftChanges, rows]);
  const hasContextActions = selectedRows.length > 0 || draftEntries.length > 0;

  const updateCurrentTableState = useCallback((update: (current: TableWorkspaceState) => TableWorkspaceState) => {
    setTableStateByKind((current) => ({
      ...current,
      [tableKind]: update(current[tableKind])
    }));
  }, [tableKind]);

  useEffect(() => {
    const rememberedRow = activeRow;
    if (rememberedRow && (selectedRow?.table !== tableKind || selectedRow?.rowId !== rememberedRow.rowId)) {
      onSelectRow(rememberedRow);
    }
  }, [activeRow, onSelectRow, selectedRow?.rowId, selectedRow?.table, tableKind]);

  useEffect(() => {
    if (!selectedRow || selectedRow.table !== tableKind || selectedRow.rowId === tableState.activeRowId) return;
    updateCurrentTableState((current) => ({
      ...current,
      activeRowId: selectedRow.rowId
    }));
  }, [selectedRow, tableKind, tableState.activeRowId, updateCurrentTableState]);

  useEffect(() => {
    async function finishWindowPointerDrag(event: globalThis.PointerEvent) {
      if (!pointerDragRowIdRef.current) return;
      await finishPointerDragAt(event.clientX, event.clientY);
    }

    window.addEventListener("pointerup", finishWindowPointerDrag);
    window.addEventListener("pointercancel", finishWindowPointerDrag);
    return () => {
      window.removeEventListener("pointerup", finishWindowPointerDrag);
      window.removeEventListener("pointercancel", finishWindowPointerDrag);
    };
  });

  function draftKey(row: WorkbenchRow, field: string): string {
    return `${row.rowId}::${field}`;
  }

  function displayValue(row: WorkbenchRow, field: string, fallback: unknown): string {
    const key = draftKey(row, field);
    if (Object.prototype.hasOwnProperty.call(draftChanges, key)) return draftChanges[key];
    if (fallback === null || fallback === undefined) return "";
    return String(fallback);
  }

  function isDraftCell(row: WorkbenchRow, field?: string): boolean {
    return Boolean(field && Object.prototype.hasOwnProperty.call(draftChanges, draftKey(row, field)));
  }

  function commitDraft(row: WorkbenchRow, field: string, value: string) {
    updateCurrentTableState((current) => ({
      ...current,
      draftChanges: { ...current.draftChanges, [draftKey(row, field)]: value }
    }));
  }

  async function saveDrafts() {
    if (!onSaveDrafts || draftEntries.length === 0) return;
    await onSaveDrafts(draftEntries);
    updateCurrentTableState((current) => ({
      ...current,
      draftChanges: {},
      editingCell: null
    }));
  }

  async function addPfdDraft() {
    if (!onAddPfdRow) return;
    const saved = await onAddPfdRow(pfdDraft);
    if (saved === false) return;
    updateCurrentTableState((current) => ({
      ...current,
      pfdDraft: { ...emptyPfdDraft },
      isAddingPfdRow: false
    }));
  }

  async function softDeleteRows() {
    if (!onSoftDeleteRows || selectedRows.length === 0) return;
    await onSoftDeleteRows(selectedRows);
    updateCurrentTableState((current) => ({
      ...current,
      selectedRowIds: {}
    }));
  }

  async function markRowsForReview() {
    if (!onMarkRowsForReview || selectedRows.length === 0) return;
    await onMarkRowsForReview(selectedRows);
    updateCurrentTableState((current) => ({
      ...current,
      selectedRowIds: {}
    }));
  }

  function toggleRow(row: WorkbenchRow, checked: boolean) {
    updateCurrentTableState((current) => ({
      ...current,
      selectedRowIds: { ...current.selectedRowIds, [row.rowId]: checked }
    }));
  }

  function activateRow(row: WorkbenchRow) {
    updateCurrentTableState((current) => ({
      ...current,
      activeRowId: row.rowId
    }));
    onSelectRow(row);
  }

  function toggleAll(checked: boolean) {
    updateCurrentTableState((current) => ({
      ...current,
      selectedRowIds: checked ? Object.fromEntries(visibleRows.map((row) => [row.rowId, true])) : {}
    }));
  }

  function updatePfdDraft(field: keyof PfdNewRowDraft, value: string) {
    updateCurrentTableState((current) => ({
      ...current,
      pfdDraft: { ...current.pfdDraft, [field]: value }
    }));
  }

  function setCurrentEditingCell(cell: DraftCell | null) {
    updateCurrentTableState((current) => ({
      ...current,
      editingCell: cell
    }));
  }

  async function reorderPfdRowToTarget(sourceRowId: string | null, targetRow: WorkbenchRow) {
    if (!sourceRowId || sourceRowId === targetRow.rowId || !onReorderPfdRows) {
      draggedRowIdRef.current = null;
      pointerDragRowIdRef.current = null;
      setDraggedRowId(null);
      return;
    }

    const fromIndex = visibleRows.findIndex((row) => row.rowId === sourceRowId);
    const toIndex = visibleRows.findIndex((row) => row.rowId === targetRow.rowId);
    if (fromIndex < 0 || toIndex < 0) {
      draggedRowIdRef.current = null;
      pointerDragRowIdRef.current = null;
      setDraggedRowId(null);
      return;
    }

    const reorderedRows = [...visibleRows];
    const [movedRow] = reorderedRows.splice(fromIndex, 1);
    reorderedRows.splice(toIndex, 0, movedRow);
    draggedRowIdRef.current = null;
    pointerDragRowIdRef.current = null;
    setDraggedRowId(null);
    await onReorderPfdRows(reorderedRows);
  }

  async function dropPfdRow(targetRow: WorkbenchRow) {
    await reorderPfdRowToTarget(draggedRowIdRef.current || draggedRowId, targetRow);
  }

  async function movePfdRow(row: WorkbenchRow, direction: -1 | 1) {
    if (!canDragReorderPfdRows || !onReorderPfdRows) return;
    const fromIndex = visibleRows.findIndex((item) => item.rowId === row.rowId);
    const toIndex = fromIndex + direction;
    if (fromIndex < 0 || toIndex < 0 || toIndex >= visibleRows.length) return;
    const reorderedRows = [...visibleRows];
    const [movedRow] = reorderedRows.splice(fromIndex, 1);
    reorderedRows.splice(toIndex, 0, movedRow);
    await onReorderPfdRows(reorderedRows);
  }

  function startDrag(row: WorkbenchRow, event: DragEvent<HTMLElement>) {
    if (!canDragReorderPfdRows) return;
    draggedRowIdRef.current = row.rowId;
    setDraggedRowId(row.rowId);
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", row.rowId);
  }

  function endDrag() {
    draggedRowIdRef.current = null;
    setDraggedRowId(null);
  }

  function startPointerDrag(row: WorkbenchRow, event: PointerEvent<HTMLElement>) {
    if (!canDragReorderPfdRows) return;
    pointerDragRowIdRef.current = row.rowId;
    draggedRowIdRef.current = row.rowId;
    setDraggedRowId(row.rowId);
    event.currentTarget.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  }

  async function finishPointerDragAt(clientX: number, clientY: number) {
    const sourceRowId = pointerDragRowIdRef.current;
    if (!sourceRowId) return;
    const element = document.elementFromPoint(clientX, clientY);
    const rowElement = element?.closest("[data-pfd-row-id]");
    const targetRowId = rowElement?.getAttribute("data-pfd-row-id") || "";
    const targetRow = visibleRows.find((row) => row.rowId === targetRowId);
    pointerDragRowIdRef.current = null;
    draggedRowIdRef.current = null;
    setDraggedRowId(null);
    if (targetRow) {
      await reorderPfdRowToTarget(sourceRowId, targetRow);
    }
  }

  async function finishPointerDrag(event: PointerEvent<HTMLElement>) {
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    await finishPointerDragAt(event.clientX, event.clientY);
  }

  const canAddPfdRow = tableKind === "pfd" && Boolean(onAddPfdRow);
  const canDragReorderPfdRows = tableKind === "pfd" && Boolean(onReorderPfdRows) && canReorderRows && !busy;
  const canSavePfdDraft = Boolean(
    pfdDraft.process_step_id.trim() &&
    pfdDraft.operation.trim() &&
    pfdDraft.operation_type.trim() &&
    pfdDraft.process_function.trim() &&
    pfdDraft.responsibility.trim()
  );

  return (
    <div className="relative min-h-[520px] overflow-hidden rounded-lg border bg-white shadow-[0_18px_45px_rgba(15,23,42,0.06)]" aria-label="三表编辑画布">
      {canAddPfdRow && (
        <div className="border-b bg-muted/20 px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-[13px] font-medium text-foreground">过程流程图</span>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => updateCurrentTableState((current) => ({ ...current, isAddingPfdRow: !current.isAddingPfdRow }))}>
              <Plus size={14} aria-hidden="true" />
              新增行
            </Button>
          </div>
          {isAddingPfdRow && (
            <div className="mt-3 grid gap-2 rounded-md border bg-white p-3 sm:grid-cols-2 xl:grid-cols-5">
              <Input aria-label="新增行编号" placeholder="编号" value={pfdDraft.process_step_id} onChange={(event) => updatePfdDraft("process_step_id", event.target.value)} />
              <Input aria-label="新增行流程符号" placeholder="流程符号" value={pfdDraft.operation_type} onChange={(event) => updatePfdDraft("operation_type", event.target.value)} />
              <Input aria-label="新增行工序名称" placeholder="工序名称" value={pfdDraft.operation} onChange={(event) => updatePfdDraft("operation", event.target.value)} />
              <Input aria-label="新增行过程功能" placeholder="过程功能" value={pfdDraft.process_function} onChange={(event) => updatePfdDraft("process_function", event.target.value)} />
              <Input aria-label="新增行设备工装" placeholder="设备/工装" value={pfdDraft.equipment} onChange={(event) => updatePfdDraft("equipment", event.target.value)} />
              <Input aria-label="新增行产品特性" placeholder="产品特性" value={pfdDraft.product_characteristic} onChange={(event) => updatePfdDraft("product_characteristic", event.target.value)} />
              <Input aria-label="新增行过程特性" placeholder="过程特性" value={pfdDraft.process_characteristic} onChange={(event) => updatePfdDraft("process_characteristic", event.target.value)} />
              <Input aria-label="新增行特殊特性" placeholder="特殊特性" value={pfdDraft.special_characteristic} onChange={(event) => updatePfdDraft("special_characteristic", event.target.value)} />
              <Input aria-label="新增行责任" placeholder="责任" value={pfdDraft.responsibility} onChange={(event) => updatePfdDraft("responsibility", event.target.value)} />
              <div className="flex gap-2 sm:col-span-2 xl:col-span-5">
                <Button size="sm" disabled={busy || !canSavePfdDraft} onClick={addPfdDraft}>
                  保存新增行
                </Button>
                <Button size="sm" variant="ghost" disabled={busy} onClick={() => {
                  updateCurrentTableState((current) => ({
                    ...current,
                    pfdDraft: { ...emptyPfdDraft },
                    isAddingPfdRow: false
                  }));
                }}>
                  取消
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
      {hasContextActions && (
        <div className="absolute right-4 top-4 z-20 flex max-w-[calc(100%-2rem)] flex-wrap items-center justify-end gap-2 rounded-full border bg-white/95 px-3 py-2 text-[13px] shadow-[0_14px_36px_rgba(15,23,42,0.14)] backdrop-blur" aria-label="浮动上下文工具条">
          <span className="text-muted-foreground">
            {selectedRows.length > 0 ? `已选 ${selectedRows.length} 行` : `${draftEntries.length} 项未保存`}
          </span>
          <Button size="sm" variant="outline" disabled={busy || draftEntries.length === 0} onClick={saveDrafts}>
            <Save size={14} aria-hidden="true" />
            保存更改
          </Button>
          <Button size="sm" variant="outline" disabled={busy || selectedRows.length === 0} onClick={markRowsForReview}>
            <ClipboardCheck size={14} aria-hidden="true" />
            标记评审
          </Button>
          <Button size="sm" variant="outline" disabled={busy || selectedRows.length === 0} onClick={softDeleteRows}>
            <Trash2 size={14} aria-hidden="true" />
            软删除
          </Button>
          <Button size="sm" variant="ghost" disabled={busy || draftEntries.length === 0} onClick={() => updateCurrentTableState((current) => ({ ...current, draftChanges: {} }))}>
            <RotateCcw size={14} aria-hidden="true" />
            撤销本轮
          </Button>
        </div>
      )}
      <div
        ref={scrollContainerRef}
        className="max-h-[calc(100vh-330px)] min-h-[440px] overflow-auto"
      >
        <Table className="min-w-max">
          <TableHeader className="sticky top-0 z-10 bg-white shadow-[0_1px_0_rgba(15,23,42,0.08)]">
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id} className="hover:bg-transparent">
                <TableHead className="sticky left-0 z-20 w-10 bg-white" />
                <TableHead className="sticky left-10 z-20 w-10 bg-white">
                  <input
                    type="checkbox"
                    aria-label="选择当前页全部行"
                    checked={visibleRows.length > 0 && selectedRows.length === visibleRows.length}
                    onChange={(event) => toggleAll(event.currentTarget.checked)}
                  />
                </TableHead>
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id} className="bg-white text-[12px] text-muted-foreground">
                    {flexRender(header.column.columnDef.header, header.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.length > 0 ? (
              table.getRowModel().rows.map((row) => (
                <TableRow
                  key={row.original.id}
                  data-pfd-row-id={row.original.rowId}
                  data-workbench-row-id={row.original.rowId}
                  draggable={canDragReorderPfdRows}
                  className={cn(
                    "cursor-pointer transition-[background-color,opacity,transform] duration-150",
                    canDragReorderPfdRows && "cursor-grab",
                    draggedRowId === row.original.rowId && "scale-[0.998] opacity-50",
                    tableState.activeRowId === row.original.rowId && "bg-accent/80",
                    selectedRowIds[row.original.rowId] && "bg-primary/5"
                  )}
                  onClick={() => activateRow(row.original)}
                  onDragStart={(event) => startDrag(row.original, event)}
                  onDragOver={(event) => {
                    if (canDragReorderPfdRows) event.preventDefault();
                  }}
                  onDrop={(event) => {
                    if (!canDragReorderPfdRows) return;
                    event.preventDefault();
                    const transferredRowId = event.dataTransfer.getData("text/plain");
                    if (transferredRowId) {
                      draggedRowIdRef.current = transferredRowId;
                    }
                    void dropPfdRow(row.original);
                  }}
                  onDragEnd={endDrag}
                >
                  <TableCell className="sticky left-0 z-[1] bg-inherit whitespace-nowrap" onClick={(event) => event.stopPropagation()}>
                    <div className="inline-flex items-center gap-1">
                      <span
                        data-pfd-drag-handle
                        aria-label={`整行拖拽调整 ${row.original.id} 顺序`}
                        aria-disabled={!canDragReorderPfdRows}
                        className={cn(
                          "inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors",
                          canDragReorderPfdRows && "cursor-grab hover:bg-muted hover:text-foreground"
                        )}
                        onPointerDown={(event) => startPointerDrag(row.original, event)}
                        onPointerUp={(event) => void finishPointerDrag(event)}
                        onPointerCancel={endDrag}
                      >
                        <GripVertical size={15} aria-hidden="true" />
                      </span>
                      <button
                        type="button"
                        aria-label={`${row.original.id} 上移`}
                        disabled={!canDragReorderPfdRows}
                        className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted disabled:opacity-40"
                        onClick={() => void movePfdRow(row.original, -1)}
                      >
                        <ArrowUp size={14} aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        aria-label={`${row.original.id} 下移`}
                        disabled={!canDragReorderPfdRows}
                        className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted disabled:opacity-40"
                        onClick={() => void movePfdRow(row.original, 1)}
                      >
                        <ArrowDown size={14} aria-hidden="true" />
                      </button>
                    </div>
                  </TableCell>
                  <TableCell className="sticky left-10 z-[1] bg-inherit" onClick={(event) => event.stopPropagation()}>
                    <input
                      type="checkbox"
                      aria-label={`选择 ${row.original.id}`}
                      checked={Boolean(selectedRowIds[row.original.rowId])}
                      onChange={(event) => toggleRow(row.original, event.currentTarget.checked)}
                    />
                  </TableCell>
                  {row.getVisibleCells().map((cell) => {
                    const columnDef = cell.column.columnDef as WorkbenchColumnDef;
                    const dirty = isDraftCell(row.original, columnDef.editableField);

                    return (
                      <TableCell
                        key={cell.id}
                        className={cn(
                          "align-middle transition-colors",
                          dirty && "bg-amber-50/70 shadow-[inset_0_0_0_1px_rgba(245,158,11,0.24)]"
                        )}
                      >
                        <EditableCell
                          row={row.original}
                        columnDef={columnDef}
                        value={cell.getValue()}
                        editingCell={editingCell}
                        setEditingCell={setCurrentEditingCell}
                        displayValue={displayValue}
                        commitDraft={commitDraft}
                        isDirty={dirty}
                      >
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </EditableCell>
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length + 2} className="py-8 text-center text-muted-foreground">
                  当前没有可显示的三表记录。请先在图纸导入页生成运行，或调整筛选条件。
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <StickyHorizontalScrollbar targetRef={scrollContainerRef} />
    </div>
  );
}

type EditableCellProps = {
  row: WorkbenchRow;
  columnDef: WorkbenchColumnDef;
  value: unknown;
  editingCell: DraftCell | null;
  setEditingCell: (cell: DraftCell | null) => void;
  displayValue: (row: WorkbenchRow, field: string, fallback: unknown) => string;
  commitDraft: (row: WorkbenchRow, field: string, value: string) => void;
  isDirty: boolean;
  children: ReactNode;
};

function EditableCell({
  row,
  columnDef,
  value,
  editingCell,
  setEditingCell,
  displayValue,
  commitDraft,
  isDirty,
  children
}: EditableCellProps) {
  const field = columnDef.editableField;
  const isEditing = field && editingCell?.rowId === row.rowId && editingCell.field === field;
  const currentValue = field ? displayValue(row, field, value) : "";

  if (!field) return <>{children}</>;

  if (isEditing) {
    return (
      <Input
        autoFocus
        className={cn("h-8", isDirty && "border-amber-300 bg-amber-50")}
        defaultValue={currentValue}
        onBlur={(event) => {
          commitDraft(row, field, event.target.value);
          setEditingCell(null);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === "Tab") {
            commitDraft(row, field, event.currentTarget.value);
            setEditingCell(null);
          }
          if (event.key === "Escape") {
            setEditingCell(null);
          }
        }}
      />
    );
  }

  return (
    <button
      type="button"
      className={cn(
        "relative min-h-8 w-full rounded-md border border-transparent px-2 py-1 text-left transition-colors hover:bg-muted focus:outline-none focus:ring-2 focus:ring-ring",
        isDirty && "border-amber-200 bg-amber-50 pr-5 shadow-[inset_3px_0_0_rgba(245,158,11,0.55)] hover:bg-amber-50"
      )}
      onClick={(event) => {
        event.stopPropagation();
        setEditingCell({ rowId: row.rowId, field });
      }}
      onDoubleClick={(event) => {
        event.stopPropagation();
        setEditingCell({ rowId: row.rowId, field });
      }}
    >
      {isDirty && <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-amber-500" aria-label="未保存更改" />}
      {currentValue || <span className="text-muted-foreground">点击编辑</span>}
    </button>
  );
}
