import type { BootstrapPayload, HealthResponse, WorkbenchRow } from "../api/types";
import { riskLabel, rowStatusLabel } from "../state/workbench-display";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";

type InspectorPanelProps = {
  row: WorkbenchRow | null;
  health: HealthResponse | null;
  bootstrap: BootstrapPayload | null;
  emptyHint: string;
};

export function InspectorPanel({ row, health, bootstrap, emptyHint }: InspectorPanelProps) {
  return (
    <aside className="bg-white/82 border-0 border-l border-solid border-border p-[18px]">
      <div className="grid gap-[3px] mb-4">
        <strong>检查器</strong>
        <span className="text-muted-foreground">证据、状态与本地服务</span>
      </div>

      {row ? (
        <section className="grid gap-3 py-[14px] border-0 border-t border-solid border-[#e2e2e7]">
          <span className="text-primary text-xs font-bold">{row.id}</span>
          <h2 className="m-0 text-base leading-[1.35]">{row.characteristic}</h2>
          <dl className="grid gap-[9px] m-0">
            {[
              ["过程", row.process],
              ["风险", riskLabel(row.risk)],
              ["状态", rowStatusLabel(row.status)],
              ["责任", row.owner],
            ].map(([label, value]) => (
              <div key={label} className="flex justify-between gap-2.5">
                <dt className="text-muted-foreground">{label}</dt>
                <dd className="m-0 text-right">{value}</dd>
              </div>
            ))}
          </dl>
          <div className="grid gap-1.5 rounded-lg border border-border bg-muted/40 p-3">
            <span className="text-xs font-semibold text-primary">证据摘要</span>
            <p className="m-0 text-[#303034] text-[13px] leading-[1.5]">{row.evidence}</p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {row.linkedRows.map((item) => (
              <Badge key={item} variant="secondary" className="text-primary">
                {item}
              </Badge>
            ))}
          </div>
          <div className="text-[#56565b] text-[13px] leading-[1.45]">
            当前选中行的证据和状态都在这里看，左侧工作台只保留表格本身。
          </div>
        </section>
      ) : (
        <section className="py-6 text-muted-foreground">{emptyHint}</section>
      )}

      <Separator className="my-[14px]" />

      <section className="grid gap-3">
        <span className="text-primary text-xs font-bold">本地服务</span>
        <dl className="grid gap-[9px] m-0">
          <div className="flex justify-between gap-2.5">
            <dt className="text-muted-foreground">健康检查</dt>
            <dd className="m-0 text-right">{health?.ok ? "通过" : "未连接"}</dd>
          </div>
          <div className="flex justify-between gap-2.5">
            <dt className="text-muted-foreground">本地后端</dt>
            <dd className="m-0 text-right">{bootstrap?.sidecarManaged ? "托管" : "未托管"}</dd>
          </div>
          <div className="flex justify-between gap-2.5">
            <dt className="text-muted-foreground">地址</dt>
            <dd className="m-0 text-right">{bootstrap?.apiBaseUrl ?? "127.0.0.1:8000"}</dd>
          </div>
        </dl>
      </section>
    </aside>
  );
}
