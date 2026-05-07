import type { ProcessFlowStep, WorkbenchRow } from "../api/types";
import { cn } from "@/lib/utils";

type PfdFlowDiagramProps = {
  steps: ProcessFlowStep[];
  selectedRow: WorkbenchRow | null;
  onSelectStep: (stepId: string) => void;
};

type FlowSymbolMeta = {
  code: string;
  label: string;
  shapeClassName: string;
  textClassName: string;
};

type ProcessFlowNode = {
  id: string;
  step: ProcessFlowStep;
  index: number;
  x: number;
  y: number;
};

type ProcessFlowEdgeKind = "sequence" | "branch" | "backlink" | "rework";

type ProcessFlowEdge = {
  id: string;
  fromId: string;
  toId: string;
  fromIndex: number;
  toIndex: number;
  kind: ProcessFlowEdgeKind;
  path: string;
};

type ProcessFlowLayout = {
  nodes: ProcessFlowNode[];
  edges: ProcessFlowEdge[];
  width: number;
  height: number;
};

const NODE_WIDTH = 220;
const NODE_HEIGHT = 154;
const NODE_GAP = 78;
const NODE_TOP = 64;
const NODE_LEFT = 12;
const LAYOUT_RIGHT_PAD = 24;
const LAYOUT_HEIGHT = 286;

const FLOW_SYMBOL_META: Record<string, FlowSymbolMeta> = {
  operation: {
    code: "OP",
    label: "加工",
    shapeClassName: "rounded-sm border-[#2563eb] bg-[#eff6ff]",
    textClassName: "text-[#1d4ed8]"
  },
  inspection: {
    code: "INSP",
    label: "检验",
    shapeClassName: "rotate-45 border-[#7c3aed] bg-[#f5f3ff]",
    textClassName: "-rotate-45 text-[#6d28d9]"
  },
  transport: {
    code: "TR",
    label: "运输",
    shapeClassName: "rounded-full border-[#0891b2] bg-[#ecfeff]",
    textClassName: "text-[#0e7490]"
  },
  storage: {
    code: "ST",
    label: "存储",
    shapeClassName: "border-x-[18px] border-t-[32px] border-x-transparent border-t-[#fef3c7]",
    textClassName: "absolute top-[9px] text-[#92400e]"
  },
  rework: {
    code: "RW",
    label: "返工",
    shapeClassName: "rounded-full border-[#dc2626] bg-[#fef2f2]",
    textClassName: "text-[#b91c1c]"
  },
  outsourced: {
    code: "OS",
    label: "外协",
    shapeClassName: "rounded-sm border-dashed border-[#16a34a] bg-[#f0fdf4]",
    textClassName: "text-[#15803d]"
  }
};

function text(value: unknown, fallback = "-"): string {
  if (Array.isArray(value)) return value.map((item) => text(item)).filter(Boolean).join(", ");
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function stepId(step: ProcessFlowStep, index: number): string {
  return text(step.process_step_id ?? step.step_id ?? step.id, `PFD-${index + 1}`);
}

function nextStepIds(step: ProcessFlowStep, nextStep: ProcessFlowStep | undefined, index: number): string[] {
  if (Array.isArray(step.next_step_ids)) {
    return step.next_step_ids.map((item) => text(item, "")).filter(Boolean);
  }
  const singleNext = text(step.next_step_ids, "");
  if (singleNext) return [singleNext];
  return nextStep ? [stepId(nextStep, index + 1)] : [];
}

function explicitNextStepIds(step: ProcessFlowStep): string[] {
  if (Array.isArray(step.next_step_ids)) {
    return step.next_step_ids.map((item) => text(item, "")).filter(Boolean);
  }
  const singleNext = text(step.next_step_ids, "");
  return singleNext ? [singleNext] : [];
}

function flowSymbolKey(step: ProcessFlowStep): string {
  const raw = text(step.flow_symbol ?? step.flow_type ?? step.operation_type, "operation").toLowerCase();
  if (raw.includes("inspect") || raw.includes("检")) return "inspection";
  if (raw.includes("transport") || raw.includes("move") || raw.includes("运输") || raw.includes("搬运")) return "transport";
  if (raw.includes("storage") || raw.includes("store") || raw.includes("库存") || raw.includes("存储")) return "storage";
  if (raw.includes("rework") || raw.includes("返工")) return "rework";
  if (raw.includes("outsourced") || raw.includes("supplier") || raw.includes("外协") || raw.includes("外发")) return "outsourced";
  return FLOW_SYMBOL_META[raw] ? raw : "operation";
}

function symbolLabel(step: ProcessFlowStep, meta: FlowSymbolMeta): string {
  return text(step.flow_type_display ?? meta.label ?? step.flow_symbol ?? step.flow_type ?? step.operation_type, meta.label);
}

function processFlowEdgeKind(source: ProcessFlowStep, fromIndex: number, toIndex: number): ProcessFlowEdgeKind {
  if (flowSymbolKey(source) === "rework") return "rework";
  if (toIndex < fromIndex) return "backlink";
  if (toIndex > fromIndex + 1) return "branch";
  return "sequence";
}

function processFlowEdgePath(from: ProcessFlowNode, to: ProcessFlowNode, kind: ProcessFlowEdgeKind): string {
  const fromX = from.x + NODE_WIDTH;
  const toX = to.x;
  const midY = from.y + NODE_HEIGHT / 2;

  if (kind === "sequence") {
    return `M ${fromX} ${midY} L ${toX} ${midY}`;
  }

  if (kind === "backlink" || kind === "rework") {
    const sourceX = from.x + NODE_WIDTH * 0.5;
    const targetX = to.x + NODE_WIDTH * 0.5;
    const y = from.y - 18;
    const arcY = Math.max(18, y - 28 - Math.abs(from.index - to.index) * 8);
    return `M ${sourceX} ${y} C ${sourceX} ${arcY}, ${targetX} ${arcY}, ${targetX} ${y}`;
  }

  const sourceX = from.x + NODE_WIDTH * 0.5;
  const targetX = to.x + NODE_WIDTH * 0.5;
  const y = from.y + NODE_HEIGHT + 18;
  const arcY = Math.min(LAYOUT_HEIGHT - 18, y + 28 + Math.abs(to.index - from.index) * 8);
  return `M ${sourceX} ${y} C ${sourceX} ${arcY}, ${targetX} ${arcY}, ${targetX} ${y}`;
}

export function buildProcessFlowLayout(steps: ProcessFlowStep[]): ProcessFlowLayout {
  const nodes = steps.map((step, index) => ({
    id: stepId(step, index),
    step,
    index,
    x: NODE_LEFT + index * (NODE_WIDTH + NODE_GAP),
    y: NODE_TOP
  }));
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const edges: ProcessFlowEdge[] = [];

  nodes.forEach((node) => {
    explicitNextStepIds(node.step).forEach((targetId, edgeIndex) => {
      const target = nodeById.get(targetId);
      if (!target) return;

      const kind = processFlowEdgeKind(node.step, node.index, target.index);
      edges.push({
        id: `${node.id}-${target.id}-${edgeIndex}`,
        fromId: node.id,
        toId: target.id,
        fromIndex: node.index,
        toIndex: target.index,
        kind,
        path: processFlowEdgePath(node, target, kind)
      });
    });
  });

  return {
    nodes,
    edges,
    width: Math.max(NODE_LEFT + steps.length * NODE_WIDTH + Math.max(0, steps.length - 1) * NODE_GAP + LAYOUT_RIGHT_PAD, NODE_WIDTH),
    height: LAYOUT_HEIGHT
  };
}

export function PfdFlowDiagram({ steps, selectedRow, onSelectStep }: PfdFlowDiagramProps) {
  if (steps.length === 0) {
    return (
      <section className="rounded-lg border bg-white px-3 py-4 text-center text-[13px] text-muted-foreground">
        PFD 暂无流程步骤。
      </section>
    );
  }

  const layout = buildProcessFlowLayout(steps);

  return (
    <section className="rounded-lg border bg-white overflow-x-auto" aria-label="PFD 标准过程流程图">
      <div className="relative min-w-max p-3" style={{ width: layout.width, height: layout.height }}>
        <svg
          className="pointer-events-none absolute left-0 top-0 z-0"
          width={layout.width}
          height={layout.height}
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          aria-hidden="true"
        >
          <defs>
            <marker id="pfd-flow-arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto" markerUnits="strokeWidth">
              <path d="M 0 0 L 9 4.5 L 0 9 z" className="fill-muted-foreground" />
            </marker>
          </defs>
          {layout.edges.map((edge) => (
            <path
              key={edge.id}
              d={edge.path}
              data-edge-kind={edge.kind}
              className={cn(
                "fill-none stroke-muted-foreground",
                edge.kind === "sequence" && "stroke-[1.5]",
                edge.kind === "branch" && "stroke-[1.5] [stroke-dasharray:5_4]",
                edge.kind === "backlink" && "stroke-[1.5] stroke-[#7c3aed] [stroke-dasharray:4_3]",
                edge.kind === "rework" && "stroke-2 stroke-[#dc2626] [stroke-dasharray:3_3]"
              )}
              markerEnd="url(#pfd-flow-arrow)"
            />
          ))}
        </svg>
        {layout.nodes.map(({ step, id, index, x, y }) => {
          const outgoing = nextStepIds(step, steps[index + 1], index);
          const selected = selectedRow?.table === "pfd" && selectedRow.rowId === id;
          const symbolMeta = FLOW_SYMBOL_META[flowSymbolKey(step)];

          return (
            <div key={`${id}-${index}`} className="absolute z-10" style={{ left: x, top: y }}>
              <button
                type="button"
                onClick={() => onSelectStep(id)}
                className={cn(
                  "grid w-[220px] min-h-[154px] content-start gap-1.5 rounded-md border px-3 py-2.5 text-left text-[12px] leading-snug transition-colors",
                  selected ? "border-primary bg-accent" : "border-border bg-white hover:bg-muted/50"
                )}
              >
                <div className="flex items-start gap-2">
                  <div className="relative grid h-9 w-11 shrink-0 place-items-center">
                    {flowSymbolKey(step) === "transport" && (
                      <div className="absolute right-0 h-0 w-0 border-y-[8px] border-l-[14px] border-y-transparent border-l-[#0891b2]" />
                    )}
                    {flowSymbolKey(step) === "rework" && <span className="absolute -right-1 -top-1 text-[16px] text-[#b91c1c]">↻</span>}
                    {flowSymbolKey(step) === "outsourced" && <span className="absolute -right-0.5 -top-1 text-[14px] text-[#15803d]">↗</span>}
                    <span className={cn("grid h-8 w-10 place-items-center border text-[10px] font-semibold", symbolMeta.shapeClassName)}>
                      <span className={cn("leading-none", symbolMeta.textClassName)}>{symbolMeta.code}</span>
                    </span>
                  </div>
                  <div className="min-w-0">
                    <strong className="block text-[13px] text-foreground">{id}</strong>
                    <span className="block truncate text-[11px] text-muted-foreground">{symbolLabel(step, symbolMeta)}</span>
                  </div>
                </div>
                <div className="font-medium text-[#303034]">{text(step.operation ?? step.process_step ?? step.process_item)}</div>
                <div className="grid gap-1 text-muted-foreground">
                  <span>输入：{text(step.input_material)}</span>
                  <span>输出：{text(step.output_result)}</span>
                  <span>设备：{text(step.equipment)}</span>
                </div>
              </button>
              {outgoing.length > 0 && (
                <span className="mt-1 block max-w-[220px] truncate text-[11px] text-muted-foreground" aria-label={`${id} 指向 ${outgoing.join(", ")}`}>
                  → {outgoing.join(", ")}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
