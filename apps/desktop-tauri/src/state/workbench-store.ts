import type { ProcessFlowStep, RowStatus, TableKind, WorkbenchRow } from "../api/types";

export type WorkbenchFilters = {
  query: string;
  table: TableKind;
  risk: "all" | WorkbenchRow["risk"];
  status: "all" | RowStatus;
};

export const initialFilters: WorkbenchFilters = {
  query: "",
  table: "pfd",
  risk: "all",
  status: "all"
};

export function filterRows(rows: WorkbenchRow[], filters: WorkbenchFilters): WorkbenchRow[] {
  const query = filters.query.trim().toLowerCase();

  return rows.filter((row) => {
    const matchesTable = row.table === filters.table;
    const matchesRisk = filters.risk === "all" || row.risk === filters.risk;
    const matchesStatus = filters.status === "all" || row.status === filters.status;
    const matchesQuery =
      !query ||
      [row.id, row.process, row.characteristic, row.owner, row.evidence]
        .join(" ")
        .toLowerCase()
        .includes(query);

    return matchesTable && matchesRisk && matchesStatus && matchesQuery;
  });
}

function text(value: unknown, fallback = ""): string {
  if (Array.isArray(value)) return value.map((item) => text(item)).filter(Boolean).join(", ");
  if (value === null || value === undefined) return fallback;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function riskFromRow(row: Record<string, unknown>): WorkbenchRow["risk"] {
  const value = text(row.risk_level ?? row.action_priority ?? row.severity).toLowerCase();
  if (["high", "h", "高", "高风险", "a"].includes(value)) return "high";
  if (["low", "l", "低", "低风险", "c"].includes(value)) return "low";
  return "medium";
}

function statusFromRow(row: Record<string, unknown>): RowStatus {
  const status = text(row.review_status ?? row.row_status ?? row.action_status);
  if (["已确认", "已批准", "已批量确认", "closed", "approved"].includes(status)) return "approved";
  if (["AI建议确认", "待确认", "需人工判断", "必须修复"].includes(status) || row.needs_confirmation) return "review";
  return "draft";
}

function rowsFromDocument(result: Record<string, unknown>, table: TableKind, includeDeleted = false): WorkbenchRow[] {
  const sourceKey = table === "pfd" ? "process_flow" : table === "cp" ? "control_plan" : "pfmea";
  const containerKey = table === "pfd" ? "steps" : "rows";
  const idKey = table === "pfd" ? "process_step_id" : table === "cp" ? "control_plan_id" : "pfmea_id";
  const document = result[sourceKey] as Record<string, unknown> | undefined;
  const rows = Array.isArray(document?.[containerKey]) ? (document?.[containerKey] as Record<string, unknown>[]) : [];

  return rows.filter((row) => includeDeleted || (!row.deleted && !row.soft_deleted)).map((row, index) => {
    const id = text(row[idKey], `${table.toUpperCase()}-${index + 1}`);
    return {
      id,
      table,
      process: text(row.operation ?? row.process_step ?? row.process_item, "-"),
      characteristic: text(
        row.product_process_characteristic ??
          row.product_characteristics ??
          row.process_characteristics ??
          row.failure_mode ??
          row.characteristic,
        "-"
      ),
      risk: riskFromRow(row),
      status: statusFromRow(row),
      owner: text(row.owner ?? row.responsibility, "-"),
      evidence: text(row.evidence_refs ?? row.document_refs, "暂无证据"),
      linkedRows: [text(row.process_step_id), text(row.pfmea_id), text(row.linked_control_plan_id)].filter(Boolean),
      rowId: id,
      rowIdField: idKey,
      raw: row
    };
  });
}

export function processFlowStepsFromResult(result: Record<string, unknown> | null | undefined): ProcessFlowStep[] {
  const processFlow = result?.process_flow as Record<string, unknown> | undefined;
  return Array.isArray(processFlow?.steps) ? (processFlow.steps as ProcessFlowStep[]) : [];
}

export function processFlowStepsFromRows(rows: WorkbenchRow[]): ProcessFlowStep[] {
  return rows
    .filter((row) => row.table === "pfd")
    .map((row) => row.raw as ProcessFlowStep);
}

export function rowsFromResult(result: Record<string, unknown> | null | undefined): WorkbenchRow[] {
  if (!result) return [];
  return [
    ...rowsFromDocument(result, "pfd"),
    ...rowsFromDocument(result, "pfmea"),
    ...rowsFromDocument(result, "cp")
  ];
}

export function softDeletedRowsFromResult(result: Record<string, unknown> | null | undefined): WorkbenchRow[] {
  if (!result) return [];
  return [
    ...rowsFromDocument(result, "pfd", true),
    ...rowsFromDocument(result, "pfmea", true),
    ...rowsFromDocument(result, "cp", true)
  ].filter((row) => Boolean(row.raw.deleted || row.raw.soft_deleted));
}
