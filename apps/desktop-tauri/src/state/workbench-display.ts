import type { RiskLevel, RowStatus, TableKind } from "../api/types";

export function riskLabel(risk: RiskLevel | string): string {
  const labels: Record<string, string> = {
    high: "高风险",
    medium: "中风险",
    low: "低风险"
  };
  return labels[risk] ?? String(risk || "中风险");
}

export function rowStatusLabel(status: RowStatus | string): string {
  const labels: Record<string, string> = {
    draft: "草稿",
    review: "待确认",
    approved: "已确认"
  };
  return labels[status] ?? String(status || "草稿");
}

export function tableLabel(table: TableKind | string): string {
  const labels: Record<string, string> = {
    pfd: "过程流程图",
    pfmea: "失效模式分析",
    cp: "控制计划"
  };
  return labels[table] ?? String(table || "三表");
}

export function stageStatusText(status: string): string {
  const labels: Record<string, string> = {
    not_started: "待开始",
    running: "生成中",
    generated: "已生成",
    confirmed: "已确认",
    blocked: "已阻断",
    failed: "失败"
  };
  return labels[status] ?? String(status || "待开始");
}
