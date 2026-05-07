import type { WorkbenchRow } from "../api/types";

type PreviewRailProps = {
  row: WorkbenchRow | null;
};

export function PreviewRail({ row }: PreviewRailProps) {
  return (
    <div className="grid gap-2 p-3 bg-white border border-border rounded-lg">
      <span className="text-muted-foreground text-xs">选中行摘要</span>
      {row ? (
        <div className="grid gap-1.5 text-[#303034] text-[13px]">
          <div className="flex items-center gap-2.5">
            <strong>{row.id}</strong>
            <span className="text-muted-foreground">{row.process}</span>
          </div>
          <span className="text-muted-foreground">{row.characteristic}</span>
          <span>{row.linkedRows.join(" / ") || "暂无链路"}</span>
        </div>
      ) : (
        <div className="text-[#86868b] text-[13px]">
          选择记录后显示链路摘要
        </div>
      )}
    </div>
  );
}
