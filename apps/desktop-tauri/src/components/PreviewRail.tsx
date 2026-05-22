import type { WorkbenchRow } from "../api/types";
import { riskLabel, rowStatusLabel, tableLabel } from "../state/workbench-display";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type PreviewRailProps = {
  row: WorkbenchRow | null;
  onJumpToRow?: (row: WorkbenchRow) => void;
};

export function PreviewRail({ row, onJumpToRow }: PreviewRailProps) {
  return (
    <div className="min-w-0 rounded-md border bg-muted/20 px-3 py-2 transition-colors duration-150">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">当前行上下文</span>
        {row && onJumpToRow && (
          <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => onJumpToRow(row)}>
            定位
          </Button>
        )}
      </div>
      {row ? (
        <div className="mt-1 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-[#303034]">
          <span className="rounded-full border px-2 py-0.5 text-[11px] text-muted-foreground">
            {tableLabel(row.table)}
          </span>
          <strong className="truncate">{row.id}</strong>
          <span className="max-w-[320px] truncate text-muted-foreground">{row.process}</span>
          <span className="max-w-[320px] truncate">{row.characteristic}</span>
          <span className={cn("rounded-full border px-2 py-0.5 text-[11px]", row.risk === "high" ? "border-destructive/30 text-destructive" : "text-muted-foreground")}>
            {riskLabel(row.risk)}
          </span>
          <span className="rounded-full border px-2 py-0.5 text-[11px] text-muted-foreground">
            {rowStatusLabel(row.status)}
          </span>
          <div className="min-w-[180px] flex-1 truncate text-muted-foreground">
            跳转链路：{row.linkedRows.join(" / ") || "暂无"}
          </div>
        </div>
      ) : (
        <div className="mt-1 text-[13px] text-[#86868b]">
          激活一行后显示表名、编号和链路。
        </div>
      )}
    </div>
  );
}
