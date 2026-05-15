import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, SlidersHorizontal } from "lucide-react";
import { applyEditPatch, confirmPfdStage, getRun, regeneratePfmeaStage } from "../api/client";
import type { DesktopRun, TableKind, WorkbenchRow } from "../api/types";
import { PreviewRail } from "../components/PreviewRail";
import { PfdFlowDiagram } from "../components/PfdFlowDiagram";
import { SegmentedControl } from "../components/SegmentedControl";
import { StatStrip } from "../components/StatStrip";
import { WorkbenchTable, type PfdNewRowDraft } from "../components/WorkbenchTable";
import { filterRows, initialFilters, processFlowStepsFromRows, rowsFromResult, softDeletedRowsFromResult, type WorkbenchFilters } from "../state/workbench-store";
import { stageStatusText } from "../state/workbench-display";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

type ThreeTableWorkbenchProps = {
  run: DesktopRun | null;
  selectedRow: WorkbenchRow | null;
  onSelectRow: (row: WorkbenchRow) => void;
  onRunUpdated?: (run: DesktopRun) => void;
};

function stepIdsFrom(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item ?? "").trim()).filter(Boolean);
  if (value === null || value === undefined || value === "") return [];
  return [String(value).trim()].filter(Boolean);
}

export default function ThreeTableWorkbench({ run, selectedRow, onSelectRow, onRunUpdated }: ThreeTableWorkbenchProps) {
  const [filters, setFilters] = useState<WorkbenchFilters>(initialFilters);
  const [saveState, setSaveState] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [lastSoftDeletedRows, setLastSoftDeletedRows] = useState<WorkbenchRow[]>([]);
  const sourceRows = useMemo(() => rowsFromResult(run?.current_result), [run]);
  const softDeletedRows = useMemo(() => softDeletedRowsFromResult(run?.current_result), [run]);
  const restorableSoftDeletedRows = lastSoftDeletedRows.length > 0 ? lastSoftDeletedRows : softDeletedRows;
  const visiblePfdRows = useMemo(() => sourceRows.filter((row) => row.table === "pfd"), [sourceRows]);
  const processFlowSteps = useMemo(() => processFlowStepsFromRows(visiblePfdRows), [visiblePfdRows]);
  const rows = useMemo(() => filterRows(sourceRows, filters), [filters, sourceRows]);
  const highRisk = sourceRows.filter((row) => row.risk === "high").length;
  const pfdPendingCount = visiblePfdRows.filter((row) => row.status !== "approved").length;
  const pfdConfirmedCount = visiblePfdRows.length - pfdPendingCount;
  const pfdConfirmSummary = visiblePfdRows.length > 0
    ? `过程流程图确认进度：已确认 ${pfdConfirmedCount} 行，待确认 ${pfdPendingCount} 行`
    : "过程流程图暂无可确认行";
  const hasRun = Boolean(run);
  const pfmeaFailed = stageStatus(run, "pfmea") === "failed";
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

  function chainStagesFromRun(updatedRun: DesktopRun | null): Record<string, unknown> | null {
    const topLevelStages = updatedRun?.chain_stages;
    if (topLevelStages && typeof topLevelStages === "object") return topLevelStages as Record<string, unknown>;
    const rawStages = updatedRun?.raw_result?.chain_stages;
    if (rawStages && typeof rawStages === "object") return rawStages as Record<string, unknown>;
    const currentStages = updatedRun?.current_result?.chain_stages;
    return currentStages && typeof currentStages === "object" ? (currentStages as Record<string, unknown>) : null;
  }

  function stageStatus(updatedRun: DesktopRun | null, stage: "pfmea" | "cp"): string {
    const chainStages = chainStagesFromRun(updatedRun);
    const stageData = chainStages?.[stage];
    if (!stageData || typeof stageData !== "object") return "";
    const status = (stageData as Record<string, unknown>).status;
    return typeof status === "string" ? status : "";
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
      pollRunUntil(updated.id, "pfmea", "过程流程图已确认，正在后台生成失效模式分析；你可以继续查看和整理当前表。");
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
      pollRunUntil(updated.id, "pfmea", "失效模式分析正在重新生成；完成后会自动刷新。");
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

  function compactChainStages() {
    const chainStages = chainStagesFromRun(run);
    const stages = [
      { key: "pfd", label: "过程流程图" },
      { key: "pfmea", label: "失效模式分析" },
      { key: "cp", label: "控制计划" }
    ];
    return stages.map((stage) => {
      const value = chainStages?.[stage.key];
      const status = value && typeof value === "object"
        ? (value as Record<string, unknown>).status
        : "";
      return { ...stage, status: typeof status === "string" ? status : "not_started" };
    });
  }

  return (
    <div className="grid gap-4">
      <StatStrip
        stats={[
          { label: "三表记录", value: sourceRows.length },
          { label: "高风险", value: highRisk, tone: "danger" },
          { label: "待确认", value: sourceRows.filter((row) => row.status === "review").length, tone: "warning" },
          { label: "已确认", value: sourceRows.filter((row) => row.status === "approved").length }
        ]}
      />

      <div className="rounded-lg border bg-white px-4 py-3" aria-label="紧凑阶段状态">
        <div className="flex items-center justify-between gap-3">
          <div className="text-[#56565b] text-[13px]">
            {run ? `当前运行 #${run.id}：${run.status_display || run.status}` : '暂无运行结果，请先在"图纸导入"中生成三表。'}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {compactChainStages().map((stage) => (
              <span key={stage.key} className="inline-flex items-center gap-1.5 rounded-full border bg-muted/40 px-2.5 py-1 text-xs text-muted-foreground">
                {stage.status === "running" ? <Loader2 size={13} className="animate-spin text-primary" /> : stage.status === "failed" ? <AlertTriangle size={13} className="text-destructive" /> : <CheckCircle2 size={13} className={stage.status === "confirmed" || stage.status === "generated" ? "text-[#34C759]" : "text-muted-foreground"} />}
                {stage.label} · {stageStatusText(stage.status)}
              </span>
            ))}
          </div>
        </div>
        {saveState && (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[#56565b] text-[13px]">
            <span>{saveState}</span>
          </div>
        )}
        {restorableSoftDeletedRows.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-2 rounded-md border border-[#f2d48a] bg-[#fff8e6] px-3 py-2 text-[13px] text-[#6f4e00]">
            <span>已软删除 {restorableSoftDeletedRows.length} 行。</span>
            <Button size="sm" variant="outline" disabled={isSaving} onClick={undoSoftDeleteRows}>
              恢复软删除行
            </Button>
          </div>
        )}
      </div>

      <section className={`flex items-center gap-2.5 min-h-12 flex-wrap ${hasRun ? "" : "pointer-events-none opacity-60"}`} aria-disabled={!hasRun}>
        <SegmentedControl<TableKind>
          value={filters.table}
          onChange={(table) => patchFilters({ table })}
          options={[
            { value: "pfd", label: "过程流程图" },
            { value: "pfmea", label: "失效模式分析" },
            { value: "cp", label: "控制计划" }
          ]}
        />
        <div className="grid gap-[5px] min-w-[240px] flex-1">
          <Input
            aria-label="搜索"
            placeholder="搜索编号、过程、特性"
            value={filters.query}
            disabled={!hasRun}
            onChange={(event) => patchFilters({ query: event.target.value })}
          />
        </div>
        <div className="flex items-center gap-1.5 min-w-[136px]">
          <SlidersHorizontal size={15} />
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
      </section>

      {filters.table === "pfd" && (
        <PfdFlowDiagram
          steps={processFlowSteps}
          selectedRow={selectedRow}
          onSelectStep={selectPfdStep}
        />
      )}

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_280px]" aria-label="三表编辑画布">
        <WorkbenchTable
          rows={rows}
          table={filters.table}
          selectedRow={selectedRow}
          onSelectRow={onSelectRow}
          onSaveDrafts={saveDraftChanges}
          onAddPfdRow={addPfdRow}
          onReorderPfdRows={reorderPfdRows}
          onSoftDeleteRows={softDeleteRows}
          onMarkRowsForReview={markRowsForReview}
          busy={isSaving || !hasRun}
        />
        <aside className="grid gap-3 content-start">
          <PreviewRail row={selectedRow} />
          <section className="grid gap-2 rounded-lg border bg-white p-3">
            <span className="text-muted-foreground text-xs">阶段操作</span>
            <div className="rounded-md border bg-muted/30 px-3 py-2 text-[12px] text-muted-foreground">
              {pfdConfirmSummary}
            </div>
            <Button disabled={!hasRun || isSaving || visiblePfdRows.length === 0 || pfdPendingCount === 0} onClick={confirmAllPfdRows}>
              {isSaving ? "确认中" : "确认全部过程流程图"}
            </Button>
            <Button variant="outline" disabled={!hasRun || isSaving || !pfmeaFailed} onClick={regeneratePfmea}>
              重新生成失效模式分析
            </Button>
            <p className="m-0 text-[12px] leading-[1.45] text-muted-foreground">
              全部确认后，失效模式分析会在后台生成；表格和流程图会用“已确认 / 待确认”标出每一行状态。
            </p>
          </section>
        </aside>
      </div>
    </div>
  );
}
