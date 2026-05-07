import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";
import { useMemo, useState } from "react";
import type { WorkbenchRow } from "../api/types";
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

type DraftCell = {
  rowId: string;
  field: string;
};

type DraftChange = {
  row: WorkbenchRow;
  field: string;
  value: string;
};

type WorkbenchColumnDef = ColumnDef<WorkbenchRow> & {
  editableField?: string;
};

const columns: WorkbenchColumnDef[] = [
  { accessorKey: "id", header: "编号" },
  { accessorKey: "process", header: "过程", editableField: "process" },
  { accessorKey: "characteristic", header: "特性", editableField: "characteristic" },
  { accessorKey: "risk", header: "风险", cell: ({ row }) => riskLabel(row.original.risk) },
  { accessorKey: "status", header: "状态", cell: ({ row }) => rowStatusLabel(row.original.status) },
  { accessorKey: "owner", header: "责任", editableField: "owner" },
];

type WorkbenchTableProps = {
  rows: WorkbenchRow[];
  selectedRow: WorkbenchRow | null;
  onSelectRow: (row: WorkbenchRow) => void;
  onSaveDrafts?: (changes: DraftChange[]) => Promise<void> | void;
  onSoftDeleteRows?: (rows: WorkbenchRow[]) => Promise<void> | void;
  onMarkRowsForReview?: (rows: WorkbenchRow[]) => Promise<void> | void;
  busy?: boolean;
};

export function WorkbenchTable({
  rows,
  selectedRow,
  onSelectRow,
  onSaveDrafts,
  onSoftDeleteRows,
  onMarkRowsForReview,
  busy = false
}: WorkbenchTableProps) {
  const [editingCell, setEditingCell] = useState<DraftCell | null>(null);
  const [draftChanges, setDraftChanges] = useState<Record<string, string>>({});
  const [selectedRowIds, setSelectedRowIds] = useState<Record<string, boolean>>({});
  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });
  const visibleRows = table.getRowModel().rows.map((row) => row.original);
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

  function draftKey(row: WorkbenchRow, field: string): string {
    return `${row.rowId}::${field}`;
  }

  function displayValue(row: WorkbenchRow, field: string, fallback: unknown): string {
    const key = draftKey(row, field);
    if (Object.prototype.hasOwnProperty.call(draftChanges, key)) return draftChanges[key];
    if (fallback === null || fallback === undefined) return "";
    return String(fallback);
  }

  function commitDraft(row: WorkbenchRow, field: string, value: string) {
    setDraftChanges((current) => ({ ...current, [draftKey(row, field)]: value }));
  }

  async function saveDrafts() {
    if (!onSaveDrafts || draftEntries.length === 0) return;
    await onSaveDrafts(draftEntries);
    setDraftChanges({});
    setEditingCell(null);
  }

  async function softDeleteRows() {
    if (!onSoftDeleteRows || selectedRows.length === 0) return;
    await onSoftDeleteRows(selectedRows);
    setSelectedRowIds({});
  }

  async function markRowsForReview() {
    if (!onMarkRowsForReview || selectedRows.length === 0) return;
    await onMarkRowsForReview(selectedRows);
    setSelectedRowIds({});
  }

  function toggleRow(row: WorkbenchRow, checked: boolean) {
    setSelectedRowIds((current) => ({ ...current, [row.rowId]: checked }));
  }

  function toggleAll(checked: boolean) {
    setSelectedRowIds(checked ? Object.fromEntries(visibleRows.map((row) => [row.rowId, true])) : {});
  }

  return (
    <div className="relative rounded-lg border bg-white overflow-hidden min-h-[480px]" aria-label="三表编辑画布">
      {hasContextActions && (
        <div className="absolute right-4 top-4 z-20 flex items-center gap-2 rounded-lg border bg-white/95 px-3 py-2 text-[13px] shadow-[0_10px_30px_rgba(15,23,42,0.12)] backdrop-blur" aria-label="浮动上下文工具条">
          <span className="text-muted-foreground">
            {selectedRows.length > 0 ? `已选 ${selectedRows.length} 行` : `${draftEntries.length} 项未保存`}
          </span>
          <Button size="sm" variant="outline" disabled={busy || draftEntries.length === 0} onClick={saveDrafts}>
            保存更改
          </Button>
          <Button size="sm" variant="outline" disabled={busy || selectedRows.length === 0} onClick={markRowsForReview}>
            标记评审
          </Button>
          <Button size="sm" variant="outline" disabled={busy || selectedRows.length === 0} onClick={softDeleteRows}>
            软删除
          </Button>
          <Button size="sm" variant="ghost" disabled={busy || draftEntries.length === 0} onClick={() => setDraftChanges({})}>
            撤销本轮
          </Button>
        </div>
      )}
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id}>
              <TableHead className="w-10">
                <input
                  type="checkbox"
                  aria-label="选择当前页全部行"
                  checked={visibleRows.length > 0 && selectedRows.length === visibleRows.length}
                  onChange={(event) => toggleAll(event.currentTarget.checked)}
                />
              </TableHead>
              {headerGroup.headers.map((header) => (
                <TableHead key={header.id}>
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
                className={cn(
                  "cursor-pointer",
                  selectedRow?.id === row.original.id && "bg-accent",
                  selectedRowIds[row.original.rowId] && "bg-primary/5"
                )}
                onClick={() => onSelectRow(row.original)}
              >
                <TableCell onClick={(event) => event.stopPropagation()}>
                  <input
                    type="checkbox"
                    aria-label={`选择 ${row.original.id}`}
                    checked={Boolean(selectedRowIds[row.original.rowId])}
                    onChange={(event) => toggleRow(row.original, event.currentTarget.checked)}
                  />
                </TableCell>
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id} className="align-middle">
                    <EditableCell
                      row={row.original}
                      columnDef={cell.column.columnDef as WorkbenchColumnDef}
                      value={cell.getValue()}
                      editingCell={editingCell}
                      setEditingCell={setEditingCell}
                      displayValue={displayValue}
                      commitDraft={commitDraft}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </EditableCell>
                  </TableCell>
                ))}
              </TableRow>
            ))
          ) : (
            <TableRow>
              <TableCell colSpan={columns.length} className="py-8 text-center text-muted-foreground">
                当前没有可显示的三表记录。请先在图纸导入页生成运行，或调整筛选条件。
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
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
  children: React.ReactNode;
};

function EditableCell({
  row,
  columnDef,
  value,
  editingCell,
  setEditingCell,
  displayValue,
  commitDraft,
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
        className="h-8"
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
      className="w-full rounded-md px-2 py-1 text-left hover:bg-muted focus:outline-none focus:ring-2 focus:ring-ring"
      onClick={(event) => {
        event.stopPropagation();
        setEditingCell({ rowId: row.rowId, field });
      }}
      onDoubleClick={(event) => {
        event.stopPropagation();
        setEditingCell({ rowId: row.rowId, field });
      }}
    >
      {currentValue || <span className="text-muted-foreground">点击编辑</span>}
    </button>
  );
}
