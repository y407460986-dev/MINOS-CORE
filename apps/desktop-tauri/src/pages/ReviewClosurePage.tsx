import { useEffect, useMemo, useState } from "react";
import { Check, CheckCheck, RefreshCw, X } from "lucide-react";
import {
  acceptRecommendation,
  batchConfirmAutomation,
  getClosureTasks,
  ignoreRecommendation,
  resolveAction,
  resolveChangeImpact
} from "../api/client";
import type { ClosureTask, ClosureTasksResponse, DesktopRun } from "../api/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type ReviewClosurePageProps = {
  run: DesktopRun | null;
  onRunUpdated: (run: DesktopRun) => void;
};

function objectList(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null) : [];
}

function text(value: unknown, fallback = ""): string {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function taskCategoryLabel(task: ClosureTask): string {
  const category = text(task.raw.category);
  if (category && category !== "Review Issue") return category;
  const id = task.id.toLowerCase();
  if (id.includes("drawing_recognition")) return "图纸识别复核";
  if (id.includes("process_flow_review")) return "过程流程图复核";
  if (id.includes("pfmea_review")) return "失效模式分析复核";
  if (id.includes("control_plan_review")) return "控制计划复核";
  if (id.includes("trace-link")) return "追溯关系确认";
  if (id.includes("knowledge") || id.includes("知识库推荐")) return "知识推荐处理";
  if (id.includes("row-needs-confirmation") || id.includes("人工确认")) return "人工确认";
  const labels: Record<ClosureTask["type"], string> = {
    knowledge_recommendation: "知识推荐处理",
    action_item: "行动项关闭",
    change_impact: "变更影响处理",
    manual_review: "人工复核",
    automation_review: "AI 预审",
    pfmea_action: "失效模式分析措施确认",
    linkage_sync: "三表联动同步",
    closure_task: "闭环任务"
  };
  return labels[task.type];
}

function taskSeverityLabel(task: ClosureTask): string {
  const value = text(task.raw.severity_display ?? task.raw.severity ?? task.state, "待处理");
  if (value === "blocker") return "阻断导出";
  if (value === "review") return "需复核";
  if (value === "pending") return "待处理";
  return value;
}

function taskSeverityKind(task: ClosureTask): "blocker" | "review" | "pending" {
  const value = text(task.raw.severity ?? task.state).toLowerCase();
  if (value.includes("blocker") || task.state.includes("阻断")) return "blocker";
  if (value.includes("review") || task.state.includes("复核")) return "review";
  return "pending";
}

function taskTitle(task: ClosureTask): string {
  if (task.title !== "正式导出前，所有 review_issue 都必须处理。") return task.title;
  const id = task.id.toLowerCase();
  if (id.includes("trace-link")) return "三表追溯关系尚未确认，正式导出前必须处理。";
  if (id.includes("knowledge") || id.includes("知识库推荐")) return "存在未处理的知识库推荐，正式导出前必须采纳或填写忽略原因。";
  return "存在未处理的复核问题，正式导出前必须处理。";
}

function taskTargetSummary(task: ClosureTask): string {
  const count = text(task.raw.count);
  const examples = Array.isArray(task.raw.examples)
    ? task.raw.examples.map((item) => text(item)).filter(Boolean)
    : [];
  if (examples.length) {
    const prefix = count ? `涉及 ${count} 项` : `涉及 ${examples.length} 项`;
    return `${prefix}，例如：${examples.slice(0, 3).join("、")}`;
  }
  const traceLink = /trace-link-([a-z0-9]+)-([a-z0-9]+)/i.exec(task.id);
  if (traceLink) return `对象：${traceLink[1].toUpperCase()} -> ${traceLink[2].toUpperCase()}`;
  const pfmeaRow = /pfmea-[a-z0-9-]+/i.exec(task.id);
  if (pfmeaRow) return `对象：${pfmeaRow[0].toUpperCase()}`;
  const target = text(task.targetId);
  if (target && target !== task.id) return `对象：${target}`;
  return "对象：当前运行结果";
}

function closureTasks(run: DesktopRun | null): ClosureTask[] {
  const result = run?.current_result ?? {};
  const metadata = (result.metadata ?? {}) as Record<string, unknown>;
  const manualReview = (result.manual_review ?? {}) as Record<string, unknown>;
  const tasks: ClosureTask[] = [];
  for (const item of objectList(metadata.knowledge_recommendations)) {
    const id = text(item.recommendation_id, text(item.id));
    const state = text(item.status, "待处理");
    if (id && !["已采纳", "已忽略", "accepted", "ignored"].includes(state)) {
      tasks.push({ id, type: "knowledge_recommendation", title: text(item.reason ?? item.message, "知识推荐待处理"), state, targetId: id, raw: item });
    }
  }
  for (const item of objectList(metadata.action_items)) {
    const id = text(item.action_id, text(item.id));
    const state = text(item.status, "待处理");
    if (id && !["已关闭", "closed", "ignored"].includes(state)) {
      tasks.push({ id, type: "action_item", title: text(item.description ?? item.recommended_action, "行动项待关闭"), state, targetId: id, raw: item });
    }
  }
  for (const item of objectList(metadata.change_impacts)) {
    const id = text(item.item_id, text(item.id));
    const state = text(item.status, "待处理");
    if (id && !["已处理", "无影响", "closed"].includes(state)) {
      tasks.push({ id, type: "change_impact", title: text(item.message, "变更影响待处理"), state, targetId: id, raw: item });
    }
  }
  for (const item of objectList(manualReview.items)) {
    const id = text(item.item_id, text(item.id, `MR-${tasks.length + 1}`));
    tasks.push({ id, type: "manual_review", title: text(item.message ?? item.title, "人工复核问题"), state: text(item.severity_display ?? item.severity, "待复核"), targetId: text(item.target ?? item.item_id), raw: item });
  }
  return tasks;
}

function normalizeClosureTasksResponse(response: ClosureTasksResponse): ClosureTask[] {
  const tasks = objectList(response.tasks);
  const rows = tasks.length > 0 ? tasks : objectList(response.rows);
  return rows.map((item, index) => {
    const id = text(item.id ?? item.task_id ?? item.action_id ?? item.recommendation_id ?? item.item_id ?? item.target_id, `TASK-${index + 1}`);
    const targetId = text(item.targetId ?? item.target_id ?? item.action_id ?? item.recommendation_id ?? item.item_id ?? item.pfmea_id ?? item.target, id);
    return { id, type: normalizeClosureTaskType(item), source: text(item.source), title: text(item.title ?? item.description ?? item.message ?? item.recommended_action ?? item.reason, "闭环任务待处理"), state: text(item.state ?? item.status ?? item.severity_display ?? item.severity ?? item.priority, "待处理"), targetId, raw: item };
  });
}

function normalizeClosureTaskType(item: Record<string, unknown>): ClosureTask["type"] {
  const value = text(item.type ?? item.source ?? item.category ?? item.task_type).toLowerCase();
  if (value.includes("knowledge")) return "knowledge_recommendation";
  if (value.includes("recommendation")) return "knowledge_recommendation";
  if (value.includes("change")) return "change_impact";
  if (value.includes("automation")) return "automation_review";
  if (value.includes("manual")) return "manual_review";
  if (value.includes("pfmea")) return "pfmea_action";
  if (value.includes("linkage") || value.includes("sync")) return "linkage_sync";
  if (value.includes("action")) return "action_item";
  return "closure_task";
}

function errorMessage(caught: unknown): string {
  return caught instanceof Error ? caught.message : String(caught);
}

export default function ReviewClosurePage({ run, onRunUpdated }: ReviewClosurePageProps) {
  const [apiTasks, setApiTasks] = useState<ClosureTask[] | null>(null);
  const [loadState, setLoadState] = useState("等待运行结果");
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const fallbackTasks = useMemo(() => closureTasks(run), [run]);
  const tasks = apiTasks ?? fallbackTasks;

  async function loadClosureTasks() {
    if (!run) { setApiTasks(null); setLoadState("暂无运行结果"); setLoadError(""); return; }
    setLoadState("正在读取统一闭环任务..."); setLoadError("");
    try {
      const response = await getClosureTasks(run.id);
      setApiTasks(normalizeClosureTasksResponse(response));
      setLoadState("统一闭环任务已载入");
    } catch (caught) {
      setApiTasks(null); setLoadState("统一闭环任务未载入");
      setLoadError(`GET /closure-tasks 未能返回任务：${errorMessage(caught)}`);
    }
  }

  useEffect(() => { void loadClosureTasks(); }, [run]);

  async function act(task: ClosureTask, action: "accept" | "ignore" | "resolve") {
    if (!run || !task.targetId) return;
    setActionError("");
    try {
      if (task.type === "knowledge_recommendation") {
        const updated = action === "ignore" ? await ignoreRecommendation(run.id, task.targetId, "桌面端忽略") : await acceptRecommendation(run.id, task.targetId);
        onRunUpdated(updated);
      }
      if (task.type === "change_impact") onRunUpdated(await resolveChangeImpact(run.id, task.targetId));
      if (task.type === "action_item") onRunUpdated(await resolveAction(run.id, task.targetId));
    } catch (caught) { setActionError(errorMessage(caught)); }
  }

  async function batchConfirm() {
    if (!run) return;
    setActionError("");
    try { onRunUpdated(await batchConfirmAutomation(run.id)); } catch (caught) { setActionError(errorMessage(caught)); }
  }

  return (
    <section className="grid gap-4">
      <div>
        <span className="text-primary text-xs font-bold">Review Closure</span>
        <h2 className="mt-1 mb-0 text-[22px]">复核与行动闭环</h2>
      </div>

      <div className="flex items-center gap-2.5 min-h-12">
        <Button variant="outline" disabled={!run} onClick={batchConfirm}>
          <CheckCheck size={16} className="mr-[7px]" />
          批量确认低风险 AI 项
        </Button>
        <Button variant="outline" disabled={!run} onClick={() => void loadClosureTasks()}>
          <RefreshCw size={15} className="mr-[7px]" />
          刷新统一任务
        </Button>
        <span className="text-[#56565b] text-[13px]">
          {run ? `当前运行 #${run.id}` : "暂无运行结果"}
        </span>
        <span className="text-[#56565b] text-[13px]">{loadState}</span>
      </div>

      {loadError && <pre className="m-0 p-3 border border-[#f0b4ae] rounded-lg bg-[#fff6f5] text-[#9f1c12] whitespace-pre-wrap">{loadError}</pre>}
      {actionError && <pre className="m-0 p-3 border border-[#f0b4ae] rounded-lg bg-[#fff6f5] text-[#9f1c12] whitespace-pre-wrap">{actionError}</pre>}

      <div className="rounded-lg border bg-white overflow-hidden">
        {tasks.map((task) => {
          const severity = taskSeverityKind(task);
          return (
            <article key={`${task.type}:${task.id}`}
              className="grid grid-cols-[150px_minmax(0,1fr)_auto] gap-4 items-start px-4 py-[14px] border-0 border-b border-solid border-[#ececf0] last:border-b-0"
            >
              <div className="grid gap-[7px] min-w-0">
                <strong className="text-[#1d1d1f] text-[13px] leading-[1.35]">
                  {taskCategoryLabel(task)}
                </strong>
                <Badge variant="secondary" className={cn(
                  "w-fit text-xs font-semibold",
                  severity === "blocker" && "bg-[#fff0ee] text-destructive hover:bg-[#fff0ee]",
                  severity === "review" && "bg-[#fff7e6] text-[#9a5b00] hover:bg-[#fff7e6]",
                )}>
                  {taskSeverityLabel(task)}
                </Badge>
              </div>
              <div className="min-w-0">
                <h3 className="m-0 mb-1 text-[15px] leading-[1.45] whitespace-normal">{taskTitle(task)}</h3>
                <p className="m-0 text-[13px] leading-[1.4] text-muted-foreground whitespace-normal">{taskTargetSummary(task)}</p>
                <small className="block mt-[5px] text-[#86868b] text-xs leading-[1.35] break-words">系统编号：{task.id}</small>
              </div>
              <div className="flex gap-2 items-center">
                {task.type === "knowledge_recommendation" && (
                  <>
                    <Button variant="outline" size="icon" className="w-[30px] h-[30px]" title="采纳推荐" onClick={() => void act(task, "accept")}>
                      <Check size={15} />
                    </Button>
                    <Button variant="outline" size="icon" className="w-[30px] h-[30px]" title="忽略推荐" onClick={() => void act(task, "ignore")}>
                      <X size={15} />
                    </Button>
                  </>
                )}
                {(task.type === "change_impact" || task.type === "action_item") && (
                  <Button variant="outline" size="sm" onClick={() => void act(task, "resolve")}>关闭</Button>
                )}
              </div>
            </article>
          );
        })}
        {tasks.length === 0 && <div className="p-6 text-muted-foreground">暂无待处理闭环任务。</div>}
      </div>
    </section>
  );
}
