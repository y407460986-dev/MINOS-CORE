import { useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, Redo2, Search, SlidersHorizontal, Undo2 } from "lucide-react";
import { applyEditPatch, confirmPfdStage, confirmPfmeaStage, confirmCpStage, getRun, redoRun, regeneratePfmeaStage, regenerateCpStage, undoRun } from "../api/client";
import { subscribeToChainStream } from "../api/sse-client";
import type { ChainState, DesktopRun, TableKind, WorkbenchRow } from "../api/types";
import { PreviewRail } from "../components/PreviewRail";
import { PfdFlowDiagram } from "../components/PfdFlowDiagram";
import { SegmentedControl } from "../components/SegmentedControl";
import { ChainStepper } from "../components/ChainStepper";
import { WorkbenchTable, type PfdNewRowDraft } from "../components/WorkbenchTable";
import { filterRows, initialFilters, processFlowStepsFromRows, rowsFromResult, softDeletedRowsFromResult, type WorkbenchFilters } from "../state/workbench-store";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

type ThreeTableWorkbenchProps = {
  run: DesktopRun | null;
  selectedRow: WorkbenchRow | null;
  onSelectRow: (row: WorkbenchRow) => void;
  onRunUpdated?: (run: DesktopRun) => void;
  onRunRefresh?: () => Promise<void>;
};

function stepIdsFrom(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item ?? "").trim()).filter(Boolean);
  if (value === null || value === undefined || value === "") return [];
  return [String(value).trim()].filter(Boolean);
}

export default function ThreeTableWorkbench({ run, selectedRow, onSelectRow, onRunUpdated, onRunRefresh }: ThreeTableWorkbenchProps) {
  const [filters, setFilters] = useState<WorkbenchFilters>(initialFilters);
  const [saveState, setSaveState] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [lastSoftDeletedRows, setLastSoftDeletedRows] = useState<WorkbenchRow[]>([]);
  const sourceRows = useMemo(() => rowsFromResult(run?.current_result), [run]);
  const softDeletedRows = useMemo(() => softDeletedRowsFromResult(run?.current_result), [run]);
  const restorableSoftDeletedRows = lastSoftDeletedRows.length > 0 ? lastSoftDeletedRows : softDeletedRows;
  const visiblePfdRows = useMemo(() => sourceRows.filter((row) => row.table === "pfd"), [sourceRows]);
  const visiblePfmeaRows = useMemo(() => sourceRows.filter((row) => row.table === "pfmea"), [sourceRows]);
  const visibleCpRows = useMemo(() => sourceRows.filter((row) => row.table === "cp"), [sourceRows]);
  const processFlowSteps = useMemo(() => processFlowStepsFromRows(visiblePfdRows), [visiblePfdRows]);
  const rows = useMemo(() => filterRows(sourceRows, filters), [filters, sourceRows]);
  const highRisk = sourceRows.filter((row) => row.risk === "high").length;
  const pfdPendingCount = visiblePfdRows.filter((row) => row.status !== "approved").length;
  const pfdConfirmedCount = visiblePfdRows.length - pfdPendingCount;
  const pfmeaPendingCount = visiblePfmeaRows.filter((row) => row.status !== "approved").length;
  const cpPendingCount = visibleCpRows.filter((row) => row.status !== "approved").length;
  const reviewCount = sourceRows.filter((row) => row.status === "review").length;
  const approvedCount = sourceRows.filter((row) => row.status === "approved").length;
  const activeTableLabel = filters.table === "pfd" ? "过程流程图" : filters.table === "pfmea" ? "失效模式分析" : "控制计划";
  const activeTableRows = filters.table === "pfd" ? visiblePfdRows : filters.table === "pfmea" ? visiblePfmeaRows : visibleCpRows;
  const activePendingCount = filters.table === "pfd" ? pfdPendingCount : filters.table === "pfmea" ? pfmeaPendingCount : cpPendingCount;
  const currentTableRow = selectedRow?.table === filters.table ? selectedRow : null;
  const pfdConfirmSummary = visiblePfdRows.length > 0
    ? `过程流程图确认进度：已确认 ${pfdConfirmedCount} 行，待确认 ${pfdPendingCount} 行`
    : "过程流程图暂无可确认行";
  const hasRun = Boolean(run);
  const pfmeaStatus = stageStatus(run, "pfmea");
  const cpStatus = stageStatus(run, "cp");
  const pfmeaNotStarted = pfmeaStatus === "" || pfmeaStatus === "not_started";
  const cpNotStarted = cpStatus === "" || cpStatus === "not_started";
  const pfdReadyToConfirm = pfdPendingCount === 0 && visiblePfdRows.length > 0 && pfmeaNotStarted;
  function patchFilters(patch: Partial<WorkbenchFilters>) {
    setFilters((current) => ({ ...current, ...patch }));
  }

  function editableField(row: WorkbenchRow, displayField?: string): string {
    if (displayField) return displayField;
    if (row.table === "pfd") return "operation";
    if (row.table === "pfmea") {
      if (displayField === "owner") return "responsibility";
      return "failure_mode";
    }
    if (row.table === "cp" && displayField === "owner") return "responsibility";
    return "control_method";
  }

  function buildSelectedRowPatch(row: WorkbenchRow, value: string, displayField?: string): Record<string, unknown> {
    const table = row.table === "pfd" ? "process_flow" : row.table === "cp" ? "control_plan" : "pfmea";
    const field = editableField(row, displayField);
    return {
      edit_patch_version: "minos-core.edit_patch.v1",
      items: [
        {
          action: "update",
          table,
          target_id: row.rowId,
          row_id: row.rowId,
          changes: { [field]: value }
        }
      ]
    };
  }

  function tableKey(row: WorkbenchRow): string {
    return row.table === "pfd" ? "process_flow" : row.table === "cp" ? "control_plan" : "pfmea";
  }

  function buildSoftDeletePatch(row: WorkbenchRow): Record<string, unknown> {
    return {
      edit_patch_version: "minos-core.edit_patch.v1",
      items: [
        {
          action: "soft_delete",
          table: tableKey(row),
          target_id: row.rowId,
          row_id: row.rowId,
          reason: "桌面端软删除 AI 生成行"
        }
      ]
    };
  }

  function buildRowsPatch(items: Record<string, unknown>[]): Record<string, unknown> {
    return {
      edit_patch_version: "minos-core.edit_patch.v1",
      items
    };
  }

  function buildPfdAddRowPatch(row: PfdNewRowDraft): Record<string, unknown> {
    const processStepId = row.process_step_id.trim();
    return buildRowsPatch([
      {
        action: "add",
        table: "process_flow",
        target_id: processStepId,
        row_id: processStepId,
        row: {
          process_step_id: processStepId,
          operation: row.operation.trim(),
          operation_type: row.operation_type.trim(),
          flow_type: row.operation_type.trim(),
          flow_symbol: row.operation_type.trim(),
          process_function: row.process_function.trim(),
          equipment: row.equipment.trim(),
          product_characteristic: row.product_characteristic.trim(),
          process_characteristic: row.process_characteristic.trim(),
          special_characteristics: row.special_characteristic.trim() ? [row.special_characteristic.trim()] : [],
          responsibility: row.responsibility.trim(),
          review_status: "待确认",
          needs_confirmation: true
        }
      }
    ]);
  }

  function buildPfdReorderPatch(reorderedRows: WorkbenchRow[]): Record<string, unknown> {
    return buildRowsPatch(
      reorderedRows
        .map((row, index) => {
          const previousRow = reorderedRows[index - 1];
          const nextRow = reorderedRows[index + 1];
          const sequence = (index + 1) * 10;
          const previousStepIds = previousRow ? [previousRow.rowId] : [];
          const nextStepIds = nextRow ? [nextRow.rowId] : [];
          return { row, sequence, previousStepIds, nextStepIds };
        })
        .filter((item) =>
          Number(item.row.raw.sequence ?? 0) !== item.sequence ||
          JSON.stringify(stepIdsFrom(item.row.raw.previous_step_ids)) !== JSON.stringify(item.previousStepIds) ||
          JSON.stringify(stepIdsFrom(item.row.raw.next_step_ids)) !== JSON.stringify(item.nextStepIds)
        )
        .map((item) => ({
          action: "update",
          table: "process_flow",
          target_id: item.row.rowId,
          row_id: item.row.rowId,
          changes: {
            sequence: item.sequence,
            previous_step_ids: item.previousStepIds,
            next_step_ids: item.nextStepIds
          }
        }))
    );
  }

  function fullPfdRowsFromVisibleReorder(reorderedRows: WorkbenchRow[]): WorkbenchRow[] {
    const visibleOrderIds = new Set(reorderedRows.map((row) => row.rowId));
    const visibleQueue = [...reorderedRows];
    return visiblePfdRows.map((row) => visibleOrderIds.has(row.rowId) ? (visibleQueue.shift() ?? row) : row);
  }

  function chainStagesFromRun(updatedRun: DesktopRun | null): ChainState | null {
    const topLevelStages = updatedRun?.chain_stages;
    if (topLevelStages && typeof topLevelStages === "object") return topLevelStages as ChainState;
    const rawStages = updatedRun?.raw_result?.chain_stages;
    if (rawStages && typeof rawStages === "object") return rawStages as ChainState;
    const currentStages = updatedRun?.current_result?.chain_stages;
    return currentStages && typeof currentStages === "object" ? (currentStages as ChainState) : null;
  }

  function stageStatus(updatedRun: DesktopRun | null, stage: "pfmea" | "cp"): string {
    const chainStages = chainStagesFromRun(updatedRun);
    const stageData = chainStages?.[stage];
    if (!stageData || typeof stageData !== "object") return "";
    const status = (stageData as Record<string, unknown>).status;
    return typeof status === "string" ? status : "";
  }

  const sseCleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    return () => { sseCleanupRef.current?.(); };
  }, []);

  function refreshRunSnapshot() {
    if (!onRunRefresh) return;
    onRunRefresh().catch((caught) => {
      setSaveState(caught instanceof Error ? caught.message : String(caught));
    });
  }

  useEffect(() => {
    if (!run || !onRunRefresh) return;
    refreshRunSnapshot();

    function handleFocus() {
      refreshRunSnapshot();
    }

    function handleVisibility() {
      if (document.visibilityState === "visible") refreshRunSnapshot();
    }

    window.addEventListener("focus", handleFocus);
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      window.removeEventListener("focus", handleFocus);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [run?.id, onRunRefresh]);

  function startStreamingProgress(runId: number, stage: "pfmea" | "cp", runningMessage: string) {
    sseCleanupRef.current?.();
    setSaveState(runningMessage);

    const cleanup = subscribeToChainStream(runId, stage, {
      onProgress: (event) => {
        setSaveState(`${runningMessage}（${event.step_index + 1}/${event.total_steps} 步，已生成 ${event.rows_so_far} 行）`);
      },
      onStepFailed: (event) => {
        setSaveState(`${runningMessage}（${event.step_id} 生成失败，继续生成中；已生成 ${event.rows_so_far} 行）`);
      },
      onConnectionStateChange: (state, retryCount) => {
        if (state === "reconnecting") {
          setSaveState(`连接中断，正在自动重连${retryCount ? `（第 ${retryCount} 次）` : ""}...`);
        }
      },
      onDone: async (event) => {
        sseCleanupRef.current = null;
        try {
          const latest = await getRun(runId);
          onRunUpdated?.(latest);
        } catch {
          sseCleanupRef.current = null;
          setSaveState("生成完成，获取状态失败，请手动刷新。");
          return;
        }
        setSaveState(event.status === "failed"
          ? `生成失败：${event.failure_message || "未知错误"}`
          : `已完成，共生成 ${event.total_rows} 行。`
        );
      },
      onError: async () => {
        sseCleanupRef.current = null;
        try {
          const latest = await getRun(runId);
          onRunUpdated?.(latest);
          const status = stageStatus(latest, stage);
          setSaveState(status === "failed" ? "下游生成失败，请查看阶段卡片错误后重试。" : "阶段状态已刷新。");
          if (status === "running") {
            pollRunUntil(runId, stage, "连接中断，已切换为阶段状态轮询...");
          }
          return;
        } catch { /* ignore */ }
        setSaveState("连接中断，自动重连失败。");
      },
    });

    sseCleanupRef.current = cleanup;
  }

  function pollRunUntil(runId: number, stage: "pfmea" | "cp", runningMessage: string) {
    setSaveState(runningMessage);
    const timer = window.setInterval(async () => {
      try {
        const latest = await getRun(runId);
        onRunUpdated?.(latest);
        const status = stageStatus(latest, stage);
        if (status && status !== "running") {
          window.clearInterval(timer);
          setSaveState(status === "failed" ? "下游生成失败，请查看阶段卡片错误后重试。" : "下游表已生成，可以继续确认。");
        }
      } catch (caught) {
        window.clearInterval(timer);
        setSaveState(caught instanceof Error ? caught.message : String(caught));
      }
    }, 2500);
  }

  async function saveDraftChanges(changes: Array<{ row: WorkbenchRow; field: string; value: string }>) {
    if (!run || changes.length === 0) return;
    setSaveState(`正在保存 ${changes.length} 项表格编辑...`);
    setIsSaving(true);
    try {
      const items = changes.map((change) => ({
        action: "update",
        table: tableKey(change.row),
        target_id: change.row.rowId,
        row_id: change.row.rowId,
        changes: { [editableField(change.row, change.field)]: change.value }
      }));
      const updated = await applyEditPatch(run.id, buildRowsPatch(items));
      onRunUpdated?.(updated);
      setSaveState("已保存表格编辑并刷新三表。");
    } catch (caught) {
      setSaveState(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setIsSaving(false);
    }
  }

  async function addPfdRow(row: PfdNewRowDraft) {
    if (!run) return false;
    setSaveState(`正在新增过程流程图行 ${row.process_step_id.trim()}...`);
    setIsSaving(true);
    try {
      const updated = await applyEditPatch(run.id, buildPfdAddRowPatch(row));
      onRunUpdated?.(updated);
      setSaveState("已新增过程流程图行，下游状态会重新计算。");
      return true;
    } catch (caught) {
      setSaveState(caught instanceof Error ? caught.message : String(caught));
      return false;
    } finally {
      setIsSaving(false);
    }
  }

  async function reorderPfdRows(reorderedRows: WorkbenchRow[]) {
    if (!run || reorderedRows.length === 0) return;
    const patch = buildPfdReorderPatch(fullPfdRowsFromVisibleReorder(reorderedRows));
    const items = patch.items;
    if (!Array.isArray(items) || items.length === 0) return;
    setSaveState("正在保存过程流程图顺序...");
    setIsSaving(true);
    try {
      const updated = await applyEditPatch(run.id, patch);
      onRunUpdated?.(updated);
      setSaveState("已保存过程流程图顺序，下游状态会重新计算。");
    } catch (caught) {
      setSaveState(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setIsSaving(false);
    }
  }

  async function softDeleteRows(targetRows: WorkbenchRow[]) {
    if (!run || targetRows.length === 0) return;
    setSaveState(`正在软删除 ${targetRows.length} 行...`);
    setIsSaving(true);
    try {
      const items = targetRows.map((row) => (buildSoftDeletePatch(row).items as Record<string, unknown>[])[0]);
      const updated = await applyEditPatch(run.id, buildRowsPatch(items));
      setLastSoftDeletedRows(targetRows);
      onRunUpdated?.(updated);
      setSaveState("已软删除选中行，下游关联会重新计算。");
    } catch (caught) {
      setSaveState(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setIsSaving(false);
    }
  }

  async function undoSoftDeleteRows() {
    if (!run || restorableSoftDeletedRows.length === 0) return;
    setSaveState(`正在恢复 ${restorableSoftDeletedRows.length} 行...`);
    setIsSaving(true);
    try {
      const items = restorableSoftDeletedRows.map((row) => ({
        action: "update",
        table: tableKey(row),
        target_id: row.rowId,
        row_id: row.rowId,
        changes: {
          deleted: false,
          soft_deleted: false,
          review_status: "待确认"
        }
      }));
      const updated = await applyEditPatch(run.id, buildRowsPatch(items));
      setLastSoftDeletedRows([]);
      onRunUpdated?.(updated);
      setSaveState("已恢复刚才软删除的行。");
    } catch (caught) {
      setSaveState(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setIsSaving(false);
    }
  }

  async function markRowsForReview(targetRows: WorkbenchRow[]) {
    if (!run || targetRows.length === 0) return;
    setSaveState(`正在标记 ${targetRows.length} 行为评审中...`);
    setIsSaving(true);
    try {
      const items = targetRows.map((row) => ({
        action: "update",
        table: tableKey(row),
        target_id: row.rowId,
        row_id: row.rowId,
        changes: { review_status: "待确认" }
      }));
      const updated = await applyEditPatch(run.id, buildRowsPatch(items));
      onRunUpdated?.(updated);
      setSaveState("已标记为评审中。");
    } catch (caught) {
      setSaveState(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setIsSaving(false);
    }
  }

  async function confirmAllPfdRows() {
    if (!run || visiblePfdRows.length === 0) return;
    setSaveState("正在确认全部过程流程图，失效模式分析将在后台生成...");
    setIsSaving(true);
    try {
      const updated = await confirmPfdStage(run.id, {
        confirmed_by: "desktop"
      });
      onRunUpdated?.(updated);
      startStreamingProgress(updated.id, "pfmea", "过程流程图已确认，正在后台生成失效模式分析；你可以继续查看和整理当前表。");
    } catch (caught) {
      setSaveState(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setIsSaving(false);
    }
  }

  async function regeneratePfmea() {
    if (!run) return;
    setSaveState("正在根据已确认的过程流程图重新生成失效模式分析...");
    setIsSaving(true);
    try {
      const updated = await regeneratePfmeaStage(run.id);
      onRunUpdated?.(updated);
      startStreamingProgress(updated.id, "pfmea", "失效模式分析正在重新生成");
    } catch (caught) {
      setSaveState(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setIsSaving(false);
    }
  }

  async function confirmAllPfmeaRows() {
    if (!run || visiblePfmeaRows.length === 0) return;
    setSaveState("正在确认全部失效模式分析，控制计划将在后台生成...");
    setIsSaving(true);
    try {
      const updated = await confirmPfmeaStage(run.id, {});
      onRunUpdated?.(updated);
      startStreamingProgress(updated.id, "cp", "失效模式分析已确认，正在后台生成控制计划");
    } catch (caught) {
      setSaveState(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setIsSaving(false);
    }
  }

  async function regenerateCp() {
    if (!run) return;
    setSaveState("正在根据已确认的失效模式分析重新生成控制计划...");
    setIsSaving(true);
    try {
      const updated = await regenerateCpStage(run.id);
      onRunUpdated?.(updated);
      startStreamingProgress(updated.id, "cp", "控制计划正在重新生成");
    } catch (caught) {
      setSaveState(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleUndo() {
    if (!run) return;
    setSaveState("正在撤销...");
    setIsSaving(true);
    try {
      const updated = await undoRun(run.id);
      onRunUpdated?.(updated);
      setSaveState("已撤销。");
    } catch (caught) {
      setSaveState(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleRedo() {
    if (!run) return;
    setSaveState("正在重做...");
    setIsSaving(true);
    try {
      const updated = await redoRun(run.id);
      onRunUpdated?.(updated);
      setSaveState("已重做。");
    } catch (caught) {
      setSaveState(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setIsSaving(false);
    }
  }

  async function confirmAllCpRows() {
    if (!run || visibleCpRows.length === 0) return;
    setSaveState("正在确认全部控制计划...");
    setIsSaving(true);
    try {
      const updated = await confirmCpStage(run.id, {});
      onRunUpdated?.(updated);
      setSaveState("控制计划已确认，三表全部完成。");
    } catch (caught) {
      setSaveState(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setIsSaving(false);
    }
  }

  function selectPfdStep(stepId: string) {
    const row = sourceRows.find((item) => item.table === "pfd" && item.rowId === stepId);
    if (row) onSelectRow(row);
  }

  function jumpToRow(row: WorkbenchRow) {
    onSelectRow(row);
    const element = document.querySelector(`[data-workbench-row-id="${CSS.escape(row.rowId)}"]`);
    element?.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
  }

  return (
    <div className="grid gap-3">
      <section className="grid gap-3 rounded-lg border bg-white/90 px-4 py-3 shadow-[0_12px_30px_rgba(15,23,42,0.04)]" aria-label="三表状态栏">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-3">
          <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-muted-foreground">
            <span className="font-medium text-foreground">
              {run ? `运行 #${run.id}` : "暂无运行"}
            </span>
            <span>{run ? (run.status_display || run.status) : '请先在"图纸导入"中生成三表'}</span>
            <span>记录 {sourceRows.length}</span>
            <span className={highRisk > 0 ? "text-destructive" : ""}>高风险 {highRisk}</span>
            <span>待确认 {reviewCount}</span>
            <span>已确认 {approvedCount}</span>
          </div>
        </div>
        <ChainStepper
          chainState={chainStagesFromRun(run)}
          run={run}
          isGenerating={pfmeaStatus === "running" || cpStatus === "running"}
          compact
          readOnly
          title="阶段"
          className="border-0 bg-transparent p-0"
        />
        {(saveState || restorableSoftDeletedRows.length > 0) && (
          <div className="mt-2 flex flex-wrap items-center gap-2 border-t pt-2 text-[13px] text-muted-foreground">
            {saveState && <span>{saveState}</span>}
            {restorableSoftDeletedRows.length > 0 && (
              <>
                <span className="text-[#6f4e00]">已软删除 {restorableSoftDeletedRows.length} 行。</span>
                <Button size="sm" variant="outline" disabled={isSaving} onClick={undoSoftDeleteRows}>
                  恢复软删除行
                </Button>
              </>
            )}
          </div>
        )}
      </section>

      <section className={`rounded-lg border bg-white px-3 py-3 ${hasRun ? "" : "pointer-events-none opacity-60"}`} aria-label="三表上下文栏" aria-disabled={!hasRun}>
        <div className="flex flex-wrap items-center gap-2.5">
          <SegmentedControl<TableKind>
            value={filters.table}
            onChange={(table) => patchFilters({ table })}
            options={[
              { value: "pfd", label: "过程流程图" },
              { value: "pfmea", label: "失效模式分析" },
              { value: "cp", label: "控制计划" }
            ]}
          />
          <div className="relative min-w-[240px] flex-1">
            <Search size={15} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input
              className="pl-8"
              aria-label="搜索"
              placeholder="搜索编号、过程、特性"
              value={filters.query}
              disabled={!hasRun}
              onChange={(event) => patchFilters({ query: event.target.value })}
            />
          </div>
          <div className="flex items-center gap-1.5 min-w-[136px]">
            <SlidersHorizontal size={15} className="text-muted-foreground" aria-hidden="true" />
            <Select value={filters.risk} disabled={!hasRun} onValueChange={(risk) => patchFilters({ risk: risk as WorkbenchFilters["risk"] })}>
              <SelectTrigger className="min-w-[118px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部风险</SelectItem>
                <SelectItem value="high">高风险</SelectItem>
                <SelectItem value="medium">中风险</SelectItem>
                <SelectItem value="low">低风险</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-1.5 min-w-[136px]">
            <Select value={filters.status} disabled={!hasRun} onValueChange={(status) => patchFilters({ status: status as WorkbenchFilters["status"] })}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部状态</SelectItem>
                <SelectItem value="draft">草稿</SelectItem>
                <SelectItem value="review">待确认</SelectItem>
                <SelectItem value="approved">已确认</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="mt-3 grid gap-3 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-center">
          <PreviewRail row={currentTableRow} onJumpToRow={jumpToRow} />
          <div className="flex flex-wrap items-center gap-2 rounded-md bg-muted/20 px-3 py-2 text-[12px] text-muted-foreground">
            <span className="mr-1 font-medium text-foreground">{activeTableLabel}</span>
            <span>{activeTableRows.length} 行</span>
            <span>待确认 {activePendingCount}</span>
            {filters.table === "pfd" && (
              <>
                <span className="hidden text-muted-foreground md:inline">{pfdConfirmSummary}</span>
                <Button size="sm" disabled={!hasRun || isSaving || visiblePfdRows.length === 0 || (pfdPendingCount === 0 && !pfdReadyToConfirm)} onClick={confirmAllPfdRows}>
                  <CheckCircle2 size={14} aria-hidden="true" />
                  {isSaving ? "确认中" : pfdReadyToConfirm ? "确认并生成 PFMEA" : "确认全部 PFD"}
                </Button>
                <Button size="sm" variant="outline" disabled={!hasRun || isSaving || pfmeaStatus === "running" || pfmeaNotStarted} onClick={regeneratePfmea}>
                  重新生成 PFMEA
                </Button>
              </>
            )}
            {filters.table === "pfmea" && (
              <>
                <Button size="sm" disabled={!hasRun || isSaving || visiblePfmeaRows.length === 0 || (pfmeaPendingCount === 0 && !cpNotStarted)} onClick={confirmAllPfmeaRows}>
                  <CheckCircle2 size={14} aria-hidden="true" />
                  {isSaving ? "确认中" : "确认并生成 CP"}
                </Button>
                <Button size="sm" variant="outline" disabled={!hasRun || isSaving || cpStatus === "running" || cpNotStarted} onClick={regenerateCp}>
                  重新生成 CP
                </Button>
              </>
            )}
            {filters.table === "cp" && (
              <>
              <Button size="sm" disabled={!hasRun || isSaving || visibleCpRows.length === 0} onClick={confirmAllCpRows}>
                <CheckCircle2 size={14} aria-hidden="true" />
                {isSaving ? "确认中" : "确认全部控制计划"}
              </Button>
              <Button size="sm" variant="outline" disabled={!hasRun || isSaving} onClick={handleUndo}>
                <Undo2 size={14} aria-hidden="true" />
                撤销
              </Button>
              <Button size="sm" variant="outline" disabled={!hasRun || isSaving} onClick={handleRedo}>
                <Redo2 size={14} aria-hidden="true" />
                重做
              </Button>
              </>
            )}
          </div>
        </div>
      </section>

      {filters.table === "pfd" && (
        <PfdFlowDiagram
          steps={processFlowSteps}
          selectedRow={currentTableRow}
          onSelectStep={selectPfdStep}
        />
      )}

      <div className="grid gap-3" aria-label="三表编辑画布">
        <WorkbenchTable
          rows={rows}
          table={filters.table}
          selectedRow={currentTableRow}
          onSelectRow={onSelectRow}
          onSaveDrafts={saveDraftChanges}
          onAddPfdRow={addPfdRow}
          onReorderPfdRows={reorderPfdRows}
          onSoftDeleteRows={softDeleteRows}
          onMarkRowsForReview={markRowsForReview}
          busy={isSaving || !hasRun}
        />
      </div>
    </div>
  );
}
