import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, SlidersHorizontal } from "lucide-react";
import { applyEditPatch, confirmPfdStage, getRun } from "../api/client";
import type { DesktopRun, TableKind, WorkbenchRow } from "../api/types";
import { PreviewRail } from "../components/PreviewRail";
import { PfdFlowDiagram } from "../components/PfdFlowDiagram";
import { SegmentedControl } from "../components/SegmentedControl";
import { StatStrip } from "../components/StatStrip";
import { WorkbenchTable } from "../components/WorkbenchTable";
import { filterRows, initialFilters, processFlowStepsFromRows, rowsFromResult, type WorkbenchFilters } from "../state/workbench-store";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

type ThreeTableWorkbenchProps = {
  run: DesktopRun | null;
  selectedRow: WorkbenchRow | null;
  onSelectRow: (row: WorkbenchRow) => void;
  onRunUpdated?: (run: DesktopRun) => void;
};

export default function ThreeTableWorkbench({ run, selectedRow, onSelectRow, onRunUpdated }: ThreeTableWorkbenchProps) {
  const [filters, setFilters] = useState<WorkbenchFilters>(initialFilters);
  const [saveState, setSaveState] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [lastSoftDeletedRows, setLastSoftDeletedRows] = useState<WorkbenchRow[]>([]);
  const sourceRows = useMemo(() => rowsFromResult(run?.current_result), [run]);
  const visiblePfdRows = useMemo(() => sourceRows.filter((row) => row.table === "pfd"), [sourceRows]);
  const processFlowSteps = useMemo(() => processFlowStepsFromRows(visiblePfdRows), [visiblePfdRows]);
  const rows = useMemo(() => filterRows(sourceRows, filters), [filters, sourceRows]);
  const highRisk = sourceRows.filter((row) => row.risk === "high").length;
  const hasRun = Boolean(run);

  function patchFilters(patch: Partial<WorkbenchFilters>) {
    setFilters((current) => ({ ...current, ...patch }));
  }

  function editableField(row: WorkbenchRow, displayField?: string): string {
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

  function stageStatus(updatedRun: DesktopRun | null, stage: "pfmea" | "cp"): string {
    const chainStages = updatedRun?.raw_result?.chain_stages ?? updatedRun?.current_result?.chain_stages;
    if (!chainStages || typeof chainStages !== "object") return "";
    const stageData = (chainStages as Record<string, unknown>)[stage];
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
    if (!run || lastSoftDeletedRows.length === 0) return;
    setSaveState(`正在恢复 ${lastSoftDeletedRows.length} 行...`);
    setIsSaving(true);
    try {
      const items = lastSoftDeletedRows.map((row) => ({
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

  async function saveAndConfirmPfd() {
    if (!run || !selectedRow || selectedRow.table !== "pfd") return;
    setSaveState("正在确认 PFD，PFMEA 将在后台生成...");
    setIsSaving(true);
    try {
      const updated = await confirmPfdStage(run.id, {
        confirmed_by: "desktop"
      });
      onRunUpdated?.(updated);
      pollRunUntil(updated.id, "pfmea", "PFD 已确认，正在后台生成 PFMEA，可继续查看和整理当前表。");
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
    const chainStages = run?.raw_result?.chain_stages ?? run?.current_result?.chain_stages;
    const stages = [
      { key: "pfd", label: "PFD" },
      { key: "pfmea", label: "PFMEA" },
      { key: "cp", label: "CP" }
    ];
    return stages.map((stage) => {
      const value = chainStages && typeof chainStages === "object"
        ? (chainStages as Record<string, unknown>)[stage.key]
        : null;
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
          { label: "待评审", value: sourceRows.filter((row) => row.status === "review").length, tone: "warning" },
          { label: "已批准", value: sourceRows.filter((row) => row.status === "approved").length }
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
            {lastSoftDeletedRows.length > 0 && (
              <Button size="sm" variant="outline" disabled={isSaving} onClick={undoSoftDeleteRows}>
                撤销软删除
              </Button>
            )}
          </div>
        )}
      </div>

      <section className={`flex items-center gap-2.5 min-h-12 flex-wrap ${hasRun ? "" : "pointer-events-none opacity-60"}`} aria-disabled={!hasRun}>
        <SegmentedControl<TableKind>
          value={filters.table}
          onChange={(table) => patchFilters({ table })}
          options={[
            { value: "pfd", label: "PFD" },
            { value: "pfmea", label: "PFMEA" },
            { value: "cp", label: "CP" }
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
              <SelectItem value="review">评审中</SelectItem>
              <SelectItem value="approved">已批准</SelectItem>
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
          selectedRow={selectedRow}
          onSelectRow={onSelectRow}
          onSaveDrafts={saveDraftChanges}
          onSoftDeleteRows={softDeleteRows}
          onMarkRowsForReview={markRowsForReview}
          busy={isSaving || !hasRun}
        />
        <aside className="grid gap-3 content-start">
          <PreviewRail row={selectedRow} />
          <section className="grid gap-2 rounded-lg border bg-white p-3">
            <span className="text-muted-foreground text-xs">阶段操作</span>
            <Button disabled={!selectedRow || selectedRow.table !== "pfd" || !hasRun || isSaving} onClick={saveAndConfirmPfd}>
              {isSaving ? "确认中" : "确认 PFD"}
            </Button>
            <p className="m-0 text-[12px] leading-[1.45] text-muted-foreground">
              PFD 确认后，PFMEA 会在后台生成；你可以继续浏览和整理当前三表。
            </p>
          </section>
        </aside>
      </div>
    </div>
  );
}

function stageStatusText(status: string): string {
  const map: Record<string, string> = {
    not_started: "待开始",
    running: "生成中",
    generated: "已生成",
    confirmed: "已确认",
    blocked: "已阻断",
    failed: "失败"
  };
  return map[status] ?? status;
}
