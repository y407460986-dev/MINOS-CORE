import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";
import type { WorkbenchRow } from "../api/types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

const columns: ColumnDef<WorkbenchRow>[] = [
  { accessorKey: "id", header: "编号" },
  { accessorKey: "process", header: "过程" },
  { accessorKey: "characteristic", header: "特性" },
  { accessorKey: "risk", header: "风险" },
  { accessorKey: "status", header: "状态" },
  { accessorKey: "owner", header: "责任" },
];

type WorkbenchTableProps = {
  rows: WorkbenchRow[];
  selectedRow: WorkbenchRow | null;
  onSelectRow: (row: WorkbenchRow) => void;
};

export function WorkbenchTable({ rows, selectedRow, onSelectRow }: WorkbenchTableProps) {
  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="rounded-lg border bg-white overflow-hidden">
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id}>
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
                  selectedRow?.id === row.original.id && "bg-accent"
                )}
                onClick={() => onSelectRow(row.original)}
              >
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
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
