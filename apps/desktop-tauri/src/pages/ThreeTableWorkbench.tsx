import { useEffect, useMemo, useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import { applyEditPatch, confirmPfdStage, getRun } from "../api/client";
import type { DesktopRun, TableKind, WorkbenchRow } from "../api/types";
import { PreviewRail } from "../components/PreviewRail";
import { PfdFlowDiagram } from "../components/PfdFlowDiagram";
import { SegmentedControl } from "../components/SegmentedControl";
import { StatStrip } from "../components/StatStrip";
import { WorkbenchTable } from "../components/WorkbenchTable";
import { filterRows, initialFilters, processFlowStepsFromResult, rowsFromResult, type WorkbenchFilters } from "../state/workbench-store";
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
  const [editValue, setEditValue] = useState("");
  const [saveState, setSaveState] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const sourceRows = useMemo(() => rowsFromResult(run?.current_result), [run]);
  const processFlowSteps = useMemo(() => processFlowStepsFromResult(run?.current_result), [run]);
  const rows = useMemo(() => filterRows(sourceRows, filters), [filters, sourceRows]);
  const highRisk = sourceRows.filter((row) => row.risk === "high").length;
  const hasRun = Boolean(run);

  useEffect(() => {
    setEditValue(selectedRow ? currentEditableValue(selectedRow) : "");
  }, [selectedRow]);

  function patchFilters(patch: Partial<WorkbenchFilters>) {
    setFilters((current) => ({ ...current, ...patch }));
  }

  function editableField(row: WorkbenchRow): string {
    if (row.table === "pfd") return "operation";
    if (row.table === "pfmea") return "failure_mode";
    return "control_method";
  }

  function currentEditableValue(row: WorkbenchRow): string {
    const value = row.raw[editableField(row)];
    if (value === null || value === undefined) return "";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  }

  function buildSelectedRowPatch(row: WorkbenchRow, value: string): Record<string, unknown> {
    const table = row.table === "pfd" ? "process_flow" : row.table === "cp" ? "control_plan" : "pfmea";
    const field = editableField(row);
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

  async function saveSelectedRow() {
    if (!run || !selectedRow || !editValue.trim()) return;
    setSaveState("正在保存编辑...");
    setIsSaving(true);
    try {
      const updated = await applyEditPatch(run.id, buildSelectedRowPatch(selectedRow, editValue));
      onRunUpdated?.(updated);
      setSaveState("已保存编辑并刷新三表");
      setEditValue("");
    } catch (caught) {
      setSaveState(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setIsSaving(false);
    }
  }

  async function softDeleteSelectedRow() {
    if (!run || !selectedRow) return;
    setSaveState("正在软删除此行...");
    setIsSaving(true);
    try {
      const updated = await applyEditPatch(run.id, buildSoftDeletePatch(selectedRow));
      onRunUpdated?.(updated);
      setSaveState("已软删除此行，下游关联会重新计算。");
      setEditValue("");
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
      const patch = editValue.trim()
        ? buildSelectedRowPatch(selectedRow, editValue)
        : undefined;
      const updated = await confirmPfdStage(run.id, {
        confirmed_by: "desktop",
        ...(patch ? { edit_patch: patch } : {})
      });
      onRunUpdated?.(updated);
      pollRunUntil(updated.id, "pfmea", "PFD 已确认，正在后台生成 PFMEA，可继续查看和整理当前表。");
      setEditValue("");
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

      <div className="text-[#56565b] text-[13px]">
        {run ? `当前运行 #${run.id}：${run.status_display || run.status}` : '暂无运行结果，请先在"图纸导入"中生成三表。'}
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

      <WorkbenchTable rows={rows} selectedRow={selectedRow} onSelectRow={onSelectRow} />

      <section className="grid grid-cols-1 md:grid-cols-[auto_minmax(180px,1fr)_minmax(240px,2fr)_auto_auto] items-center gap-2.5 p-3 bg-white border border-border rounded-lg">
        <strong>行编辑</strong>
        <span className="text-muted-foreground text-[13px]">
          {selectedRow ? `正在编辑 ${selectedRow.id}` : hasRun ? "选择一行后编辑关键字段" : "先生成三表再编辑"}
        </span>
        <Input
          value={editValue}
          disabled={!selectedRow || !hasRun || isSaving}
          placeholder={selectedRow ? `修改 ${editableField(selectedRow)}` : "暂无选中行"}
          onChange={(event) => setEditValue(event.target.value)}
        />
        <Button variant="outline" disabled={!selectedRow || !hasRun || !editValue.trim() || isSaving} onClick={saveSelectedRow}>
          {isSaving ? "处理中" : "保存编辑"}
        </Button>
        <Button variant="outline" disabled={!selectedRow || !hasRun || isSaving} onClick={softDeleteSelectedRow}>
          软删除此行
        </Button>
        <Button disabled={!selectedRow || selectedRow.table !== "pfd" || !hasRun || isSaving} onClick={saveAndConfirmPfd}>
          {isSaving ? "确认中" : editValue.trim() ? "保存并确认 PFD" : "确认 PFD"}
        </Button>
        {saveState && <span className="text-[#56565b] text-[13px] md:col-span-6">{saveState}</span>}
      </section>

      <PreviewRail row={selectedRow} />
    </div>
  );
}
