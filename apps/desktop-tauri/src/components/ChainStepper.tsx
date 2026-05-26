import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Loader2,
  Lock,
  RefreshCw,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ChainState, ChainStageKey, DesktopRun, StageStatus } from "@/api/types";

type StepDef = {
  key: ChainStageKey;
  label: string;
  description: string;
};

const STEPS: StepDef[] = [
  { key: "pfd", label: "过程流程图", description: "从图纸分析推理生成工序流程" },
  { key: "pfmea", label: "失效模式分析", description: "基于已确认的过程流程图推理潜在失效" },
  { key: "cp", label: "控制计划", description: "基于已确认的失效模式分析生成控制措施" },
];

type ChainStepperProps = {
  chainState: ChainState | null;
  run: DesktopRun | null;
  isGenerating?: boolean;
  liveProgress?: Partial<Record<ChainStageKey, GenerationProgress>>;
  onConfirm?: (stage: ChainStageKey) => Promise<void>;
  onRegenerate?: (stage: ChainStageKey) => Promise<void>;
  onViewTable?: () => void;
  compact?: boolean;
  readOnly?: boolean;
  title?: string;
  className?: string;
};

export type GenerationProgress = {
  stepIndex?: number;
  totalSteps?: number;
  rowsSoFar?: number;
  stepId?: string;
  failedStepId?: string;
};

export function ChainStepper({
  chainState,
  run,
  isGenerating = false,
  liveProgress,
  onConfirm,
  onRegenerate,
  onViewTable,
  compact = false,
  readOnly = false,
  title = "链式阶段",
  className,
}: ChainStepperProps) {
  const [confirming, setConfirming] = useState<ChainStageKey | null>(null);
  const [regenerating, setRegenerating] = useState<ChainStageKey | null>(null);
  const [message, setMessage] = useState("");

  if (!chainState) {
    return (
      <div className={cn("rounded-lg border bg-[hsl(var(--surface))] px-4 py-3 text-[13px] text-muted-foreground", className)}>
        阶段状态等待同步。启动任务后会显示过程流程图、失效模式分析和控制计划的生成进度。
      </div>
    );
  }

  const currentStage = chainState.current_stage as ChainStageKey | "complete";
  const canOperate = !readOnly && Boolean(onConfirm && onRegenerate);

  async function handleConfirm(stage: ChainStageKey) {
    if (!onConfirm) return;
    setConfirming(stage);
    setMessage("");
    try {
      await onConfirm(stage);
      setMessage(stageLabel(stage) + " 已确认，已自动生成下一阶段。");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "确认失败");
    } finally {
      setConfirming(null);
    }
  }

  async function handleRegenerate(stage: ChainStageKey) {
    if (!onRegenerate) return;
    setRegenerating(stage);
    setMessage("");
    try {
      await onRegenerate(stage);
      setMessage(stageLabel(stage) + " 已重新生成。");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "重新生成失败");
    } finally {
      setRegenerating(null);
    }
  }

  if (chainState.pipeline_mode === "batch") {
    return (
      <Card className={className}>
        <CardContent className="p-6 text-center text-muted-foreground">
          此运行使用旧版"一次性生成"模式，不支持链式确认流程。
          {run && onViewTable && (
            <Button variant="outline" size="sm" className="ml-4" onClick={onViewTable}>
              查看三表工作台
            </Button>
          )}
        </CardContent>
      </Card>
    );
  }

  if (compact) {
    return (
      <section className={cn("rounded-lg border bg-[hsl(var(--surface))] px-3 py-2.5", className)} aria-label="链式阶段状态">
        <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
          <div>
            <div className="text-[11px] font-bold uppercase text-primary">{title}</div>
            <div className="mt-0.5 text-xs text-muted-foreground">
              {currentStage === "complete" ? "三个阶段均已完成确认。" : `当前阶段：${stageLabel(currentStage)}`}
            </div>
          </div>
          {run && onViewTable && (
            <Button variant="outline" size="sm" onClick={onViewTable}>
              打开三表工作台
            </Button>
          )}
        </div>

        <div className="grid gap-2.5 lg:grid-cols-3">
          {STEPS.map((step, index) => {
            const info = chainState[step.key];
            const isActive = currentStage === step.key;
            const isRunning = info.status === "running" || (isActive && isGenerating);
            const isDone = info.status === "confirmed";
            const isReady = info.status === "generated";
            const isFailed = info.status === "failed";
            const isBlocked = info.status === "blocked";
            const progress = liveProgress?.[step.key];

            return (
              <div key={step.key} className="flex min-w-0 items-center gap-2">
                <div
                  className={cn(
                    "min-w-0 flex-1 rounded-md border px-2.5 py-2 transition-all",
                    isActive && "border-primary bg-primary/5 shadow-sm",
                    isDone && "border-[#34C759] bg-[#f4fbf6]",
                    isReady && "border-primary/50 bg-primary/5",
                    isFailed && "border-destructive bg-destructive/5",
                    isBlocked && "border-[#f2d48a] bg-[#fff8e6]",
                    isRunning && "animate-pulse"
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      {stageIcon(info.status, isActive, isGenerating)}
                      <strong className="truncate text-[13px]">{step.label}</strong>
                    </div>
                    <Badge
                      variant="outline"
                      className={cn(
                        "h-5 shrink-0 px-2 text-[10px]",
                        (isReady || isActive) && "border-primary text-primary",
                        isDone && "border-[#34C759] text-[#1f8f3a]",
                        isFailed && "border-destructive text-destructive",
                        isBlocked && "border-[#d29b14] text-[#7a5600]"
                      )}
                    >
                      {stageStatusLabel(info.status)}
                    </Badge>
                  </div>
                  <div className="mt-1 truncate text-xs text-muted-foreground">
                    {compactStageDetail(info, isActive, progress)}
                  </div>
                </div>
                {index < STEPS.length - 1 && (
                  <div
                    className={cn(
                      "hidden h-px w-5 shrink-0 lg:block",
                      chainState[STEPS[index + 1].key].status !== "not_started"
                        ? "bg-primary/50"
                        : "bg-border"
                    )}
                  />
                )}
              </div>
            );
          })}
        </div>
      </section>
    );
  }

  return (
    <div className={cn("grid gap-4", className)}>
      <div className="flex items-center gap-2">
        {STEPS.map((step, i) => {
          const info = chainState[step.key];
          const isActive = currentStage === step.key;
          const isDone = info.status === "confirmed";
          const isBlocked = info.status === "blocked";
          const isFailed = info.status === "failed";

          return (
            <div key={step.key} className="flex items-center gap-2">
              <Card
                className={cn(
                  "flex-1 transition-colors",
                  isActive && "border-primary ring-1 ring-primary/30",
                  isDone && "border-[#34C759]",
                  isBlocked && "border-destructive",
                  isFailed && "border-[#FF9500]"
                )}
              >
                <CardContent className="p-4">
                  <div className="flex items-center gap-3">
                    {isDone && <CheckCircle2 size={22} className="text-[#34C759] shrink-0" />}
                    {isActive && !isGenerating && (
                      <div className="w-[22px] h-[22px] rounded-full bg-primary flex items-center justify-center shrink-0">
                        <span className="text-primary-foreground text-xs font-bold">
                          {i + 1}
                        </span>
                      </div>
                    )}
                    {isActive && isGenerating && (
                      <Loader2 size={22} className="text-primary animate-spin shrink-0" />
                    )}
                    {isBlocked && <AlertTriangle size={22} className="text-destructive shrink-0" />}
                    {isFailed && <AlertTriangle size={22} className="text-[#FF9500] shrink-0" />}
                    {!isDone && !isActive && !isBlocked && !isFailed && (
                      <Lock size={18} className="text-muted-foreground shrink-0" />
                    )}

                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <strong
                          className={cn(
                            "text-sm",
                            isDone && "text-[#34C759]",
                            isActive && "text-primary"
                          )}
                        >
                          {step.label}
                        </strong>
                        <Badge
                          variant="outline"
                          className={cn(
                            "text-[10px] px-1.5 py-0 h-4",
                            info.status === "generated" && "border-primary text-primary",
                            info.status === "confirmed" && "border-[#34C759] text-[#34C759]"
                          )}
                        >
                          {stageStatusLabel(info.status)}
                        </Badge>
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {isDone && info.confirmed_by
                          ? `已由 ${info.confirmed_by} 确认 · ${info.row_count} 行`
                          : isActive
                            ? `${info.row_count} 行 · ${info.pending_count} 项待确认`
                            : step.description}
                      </p>
                    </div>
                  </div>

                  {isActive && !isGenerating && canOperate && (
                    <div className="flex items-center gap-2 mt-3 pt-3 border-t border-border">
                      <Button
                        size="sm"
                        disabled={confirming !== null || info.row_count === 0}
                        onClick={() => handleConfirm(step.key)}
                      >
                        {confirming === step.key && (
                          <Loader2 size={14} className="mr-1.5 animate-spin" />
                        )}
                        确认并进入下一步
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={regenerating !== null}
                        onClick={() => handleRegenerate(step.key)}
                      >
                        {regenerating === step.key && (
                          <Loader2 size={14} className="mr-1.5 animate-spin" />
                        )}
                        <RefreshCw size={14} className="mr-1.5" />
                        重新生成
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>

              {i < STEPS.length - 1 && (
                <ChevronRight
                  size={20}
                  className={cn(
                    "shrink-0",
                    chainState[STEPS[i + 1].key].status !== "not_started"
                      ? "text-primary"
                      : "text-muted-foreground/30"
                  )}
                />
              )}
            </div>
          );
        })}
      </div>

      {message && (
        <div
          className={cn(
            "text-sm p-3 rounded-lg",
            message.includes("失败")
              ? "bg-destructive/10 text-destructive"
              : "bg-primary/10 text-primary"
          )}
        >
          {message}
        </div>
      )}

      {currentStage === "complete" && (
        <Card className="border-[#34C759]">
          <CardContent className="p-4 flex items-center gap-3">
            <CheckCircle2 size={22} className="text-[#34C759]" />
            <div>
              <strong className="text-sm">链式确认流程已完成</strong>
              <p className="text-xs text-muted-foreground">
                过程流程图、失效模式分析、控制计划三个阶段均已确认。现在可以进入三表工作台查看和导出。
              </p>
            </div>
            {onViewTable && (
              <Button size="sm" className="ml-auto" onClick={onViewTable}>
                进入三表工作台
              </Button>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function stageIcon(status: StageStatus, isActive: boolean, isGenerating: boolean) {
  if (status === "confirmed") return <CheckCircle2 size={17} className="shrink-0 text-[#34C759]" />;
  if (status === "failed") return <AlertTriangle size={17} className="shrink-0 text-destructive" />;
  if (status === "blocked") return <AlertTriangle size={17} className="shrink-0 text-[#d29b14]" />;
  if (status === "running" || (isActive && isGenerating)) {
    return <Loader2 size={17} className="shrink-0 animate-spin text-primary" />;
  }
  if (status === "generated" || isActive) return <CircleDot size={17} className="shrink-0 text-primary" />;
  return <Lock size={15} className="shrink-0 text-muted-foreground" />;
}

function compactStageDetail(
  info: ChainState[ChainStageKey],
  isActive: boolean,
  progress?: GenerationProgress,
): string {
  if (info.status === "failed") return "生成失败，可进入工作台查看并重试。";
  if (info.status === "blocked") return "等待补齐上游确认。";
  if (info.status === "running") {
    if (progress?.failedStepId) {
      return `${progress.failedStepId} 生成失败，继续生成中；已生成 ${progress.rowsSoFar ?? info.row_count} 行。`;
    }
    if (progress?.totalSteps) {
      const currentStep = Math.min((progress.stepIndex ?? 0) + 1, progress.totalSteps);
      return `后台生成中，${currentStep}/${progress.totalSteps} 步，已生成 ${progress.rowsSoFar ?? info.row_count} 行。`;
    }
    return `后台生成中，等待首个工序返回，当前 ${info.row_count} 行。`;
  }
  if (info.status === "generated") return `${info.row_count} 行已生成，${info.pending_count} 项待确认。`;
  if (info.status === "confirmed") {
    return info.confirmed_by ? `${info.row_count} 行，已由 ${info.confirmed_by} 确认。` : `${info.row_count} 行已确认。`;
  }
  return isActive ? "准备生成。" : "等待上游阶段。";
}

function stageStatusLabel(status: StageStatus): string {
  const map: Record<StageStatus, string> = {
    not_started: "未开始",
    running: "生成中",
    generated: "已生成",
    confirmed: "已确认",
    blocked: "已阻断",
    failed: "失败",
  };
  return map[status] || status;
}

function stageLabel(key: ChainStageKey | "complete"): string {
  if (key === "complete") return "已完成";
  return STEPS.find((step) => step.key === key)?.label ?? key.toUpperCase();
}
