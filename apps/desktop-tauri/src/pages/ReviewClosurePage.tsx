import { useEffect, useMemo, useState, type ReactNode } from "react";
import { AlertTriangle, Check, CheckCircle2, Inbox, ListChecks, RefreshCw, X, type LucideIcon } from "lucide-react";
import {
  acceptRecommendation,
  getClosureTasks,
  ignoreRecommendation,
  resolveAction,
  resolveChangeImpact
} from "../api/client";
import type { ClosureTask, ClosureTasksResponse, DesktopRun } from "../api/types";
import { Button } from "@/components/ui/button";
import { EmptyState, Notice, StatusPill, Surface } from "@/components/ui/experience";
import { cn } from "@/lib/utils";

type ReviewClosurePageProps = {
  run: DesktopRun | null;
  onRunUpdated: (run: DesktopRun) => void;
};

type TaskFilter = "all" | "blocker" | "review" | "pending";

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

function taskSeverityStatusTone(task: ClosureTask): "danger" | "warning" | "info" {
  const severity = taskSeverityKind(task);
  if (severity === "blocker") return "danger";
  if (severity === "review") return "warning";
  return "info";
}

function taskSeverityIcon(task: ClosureTask): LucideIcon {
  const severity = taskSeverityKind(task);
  if (severity === "blocker") return AlertTriangle;
  if (severity === "review") return ListChecks;
  return CheckCircle2;
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
  const [filter, setFilter] = useState<TaskFilter>("all");
  const [selectedTaskId, setSelectedTaskId] = useState("");
  const [loadState, setLoadState] = useState("等待运行结果");
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const fallbackTasks = useMemo(() => closureTasks(run), [run]);
  const tasks = apiTasks ?? fallbackTasks;
  const summary = useMemo(() => {
    const blocker = tasks.filter((task) => taskSeverityKind(task) === "blocker").length;
    const review = tasks.filter((task) => taskSeverityKind(task) === "review").length;
    const pending = tasks.length - blocker - review;
    const actionable = tasks.filter((task) =>
      task.type === "knowledge_recommendation" ||
      task.type === "change_impact" ||
      task.type === "action_item"
    ).length;
    return { blocker, review, pending, actionable, total: tasks.length };
  }, [tasks]);
  const filteredTasks = useMemo(() => (
    filter === "all" ? tasks : tasks.filter((task) => taskSeverityKind(task) === filter)
  ), [filter, tasks]);
  const selectedTask = filteredTasks.find((task) => task.id === selectedTaskId) ?? filteredTasks[0] ?? null;

  useEffect(() => {
    if (selectedTask && selectedTask.id !== selectedTaskId) setSelectedTaskId(selectedTask.id);
    if (!selectedTask && selectedTaskId) setSelectedTaskId("");
  }, [selectedTask, selectedTaskId]);

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
      setApiTasks((current) => current ? current.filter((item) => `${item.type}:${item.id}` !== `${task.type}:${task.id}`) : current);
    } catch (caught) { setActionError(errorMessage(caught)); }
  }

  return (
    <section className="grid gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <span className="text-primary text-xs font-bold">Review Closure</span>
          <h2 className="mt-1 mb-0 text-[22px]">评审任务收件箱</h2>
          <p className="m-0 mt-1 text-[13px] text-muted-foreground">
            把正式导出前必须处理的复核、推荐和行动项集中到一个队列；AI 只提供线索，人工判断优先。
          </p>
        </div>
        <Button variant="outline" disabled={!run} onClick={() => void loadClosureTasks()}>
          <RefreshCw size={15} className="mr-[7px]" />
          刷新任务
        </Button>
      </div>

      <div className="grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-2.5">
        <InboxStat label="待处理总数" value={summary.total} icon={<Inbox size={16} />} />
        <InboxStat label="阻断导出" value={summary.blocker} tone="danger" icon={<AlertTriangle size={16} />} />
        <InboxStat label="需要复核" value={summary.review} tone="warning" icon={<ListChecks size={16} />} />
        <InboxStat label="可直接处理" value={summary.actionable} tone="success" icon={<CheckCircle2 size={16} />} />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <StatusPill tone={run ? "info" : "neutral"}>{run ? `当前运行 #${run.id}` : "暂无运行结果"}</StatusPill>
        <StatusPill tone="neutral">{loadState}</StatusPill>
      </div>

      {loadError && <Notice tone="danger" title="闭环任务未载入">{loadError}</Notice>}
      {actionError && <Notice tone="danger" title="任务操作失败">{actionError}</Notice>}

      <div className="grid grid-cols-[minmax(280px,0.95fr)_minmax(320px,1.05fr)] gap-4 max-[920px]:grid-cols-1">
        <Surface inset="none" className="overflow-hidden">
          <div className="border-0 border-b border-solid border-[#ececf0] p-3">
            <div className="grid grid-cols-4 gap-1 rounded-md bg-muted/50 p-1">
              {[
                ["all", "全部", summary.total],
                ["blocker", "阻断", summary.blocker],
                ["review", "复核", summary.review],
                ["pending", "待办", summary.pending],
              ].map(([value, label, count]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setFilter(value as TaskFilter)}
                  className={cn(
                    "rounded px-2 py-1.5 text-xs font-semibold transition-colors",
                    filter === value ? "bg-white text-[#1d1d1f] shadow-sm" : "text-[#56565b] hover:bg-white/70"
                  )}
                >
                  {label} {count}
                </button>
              ))}
            </div>
          </div>

          <div className="max-h-[560px] overflow-y-auto">
            {filteredTasks.map((task) => {
              const selected = selectedTask?.id === task.id;
              return (
                <button
                  key={`${task.type}:${task.id}`}
                  type="button"
                  onClick={() => setSelectedTaskId(task.id)}
                  className={cn(
                    "grid w-full gap-2 border-0 border-b border-solid border-[#ececf0] bg-white px-4 py-3 text-left transition-colors last:border-b-0 hover:bg-muted/40",
                    selected && "bg-[#f7fbff]"
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <strong className="min-w-0 truncate text-[13px] text-[#1d1d1f]">{taskCategoryLabel(task)}</strong>
                    <StatusPill tone={taskSeverityStatusTone(task)} icon={taskSeverityIcon(task)} className="h-6 shrink-0">
                      {taskSeverityLabel(task)}
                    </StatusPill>
                  </div>
                  <span className="line-clamp-2 text-[13px] leading-[1.45] text-[#2b2b2f]">{taskTitle(task)}</span>
                  <span className="truncate text-xs text-muted-foreground">{taskTargetSummary(task)}</span>
                </button>
              );
            })}
            {filteredTasks.length === 0 && (
              <EmptyState
                icon={CheckCircle2}
                title={tasks.length === 0 ? "暂无待处理闭环任务。" : "当前筛选下没有任务。"}
                className="min-h-[220px] rounded-none border-0 bg-transparent"
              />
            )}
          </div>
        </Surface>

        <Surface inset="none" className="p-5">
          {selectedTask ? (
            <div className="grid gap-4">
              <div className="flex flex-wrap items-center gap-2">
                <StatusPill tone={taskSeverityStatusTone(selectedTask)} icon={taskSeverityIcon(selectedTask)}>
                  {taskSeverityLabel(selectedTask)}
                </StatusPill>
                <span className="text-xs font-semibold text-primary">{taskCategoryLabel(selectedTask)}</span>
              </div>
              <div>
                <h3 className="m-0 text-[19px] leading-[1.35]">{taskTitle(selectedTask)}</h3>
                <p className="m-0 mt-2 text-[13px] leading-[1.55] text-muted-foreground">{taskTargetSummary(selectedTask)}</p>
              </div>
              <div className="grid gap-2 rounded-lg bg-muted/35 p-3 text-[13px]">
                <DetailRow label="任务状态" value={selectedTask.state} />
                <DetailRow label="目标对象" value={selectedTask.targetId || "当前运行结果"} />
                <DetailRow label="系统编号" value={selectedTask.id} />
              </div>
              <div className="flex flex-wrap gap-2 pt-1">
                {selectedTask.type === "knowledge_recommendation" && (
                  <>
                    <Button onClick={() => void act(selectedTask, "accept")}>
                      <Check size={15} className="mr-[7px]" />
                      采纳推荐
                    </Button>
                    <Button variant="outline" onClick={() => void act(selectedTask, "ignore")}>
                      <X size={15} className="mr-[7px]" />
                      忽略推荐
                    </Button>
                  </>
                )}
                {(selectedTask.type === "change_impact" || selectedTask.type === "action_item") && (
                  <Button onClick={() => void act(selectedTask, "resolve")}>
                    <Check size={15} className="mr-[7px]" />
                    关闭任务
                  </Button>
                )}
                {!["knowledge_recommendation", "change_impact", "action_item"].includes(selectedTask.type) && (
                  <Notice tone="neutral" icon={false} className="py-2 text-[13px]">
                    该任务需要回到三表工作台确认具体内容。
                  </Notice>
                )}
              </div>
            </div>
          ) : (
            <EmptyState icon={CheckCircle2} title="收件箱已清空。" className="h-full min-h-[260px] border-0 bg-transparent" />
          )}
        </Surface>
      </div>
    </section>
  );
}

function InboxStat({
  label,
  value,
  icon,
  tone = "default"
}: {
  label: string;
  value: number;
  icon: ReactNode;
  tone?: "default" | "danger" | "warning" | "success";
}) {
  return (
    <Surface inset="sm">
      <div className={cn(
        "mb-2 flex items-center gap-2 text-xs font-semibold text-muted-foreground",
        tone === "danger" && "text-destructive",
        tone === "warning" && "text-[#9a5b00]",
        tone === "success" && "text-[#1f8f3a]"
      )}>
        {icon}
        {label}
      </div>
      <strong className="text-2xl leading-none">{value}</strong>
    </Surface>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[72px_1fr] gap-3">
      <span className="text-muted-foreground">{label}</span>
      <strong className="break-words font-semibold text-[#2b2b2f]">{value}</strong>
    </div>
  );
}
