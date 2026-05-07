import { useState } from "react";
import {
  CheckCircle2,
  Lock,
  Loader2,
  AlertTriangle,
  RefreshCw,
  ChevronRight,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ChainState, ChainStageKey, StageStatus, DesktopRun } from "@/api/types";

// ---------------------------------------------------------------------------
// 步骤定义
// ---------------------------------------------------------------------------

type StepDef = {
  key: ChainStageKey;
  label: string;
  description: string;
};

const STEPS: StepDef[] = [
  { key: "pfd", label: "过程流程图", description: "PFD — 从图纸分析推理生成工序流程" },
  { key: "pfmea", label: "失效模式分析", description: "PFMEA — 基于已确认的 PFD 推理潜在失效" },
  { key: "cp", label: "控制计划", description: "CP — 基于已确认的 PFMEA 生成控制措施" },
];

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

type ChainStepperProps = {
  chainState: ChainState;
  run: DesktopRun | null;
  isGenerating: boolean;
  onConfirm: (stage: ChainStageKey) => Promise<void>;
  onRegenerate: (stage: ChainStageKey) => Promise<void>;
  onViewTable: () => void;
};

// ---------------------------------------------------------------------------
// 组件
// ---------------------------------------------------------------------------

export function ChainStepper({
  chainState,
  run,
  isGenerating,
  onConfirm,
  onRegenerate,
  onViewTable,
}: ChainStepperProps) {
  const [confirming, setConfirming] = useState<ChainStageKey | null>(null);
  const [regenerating, setRegenerating] = useState<ChainStageKey | null>(null);
  const [message, setMessage] = useState("");

  const currentStage = chainState.current_stage as ChainStageKey | "complete";

  async function handleConfirm(stage: ChainStageKey) {
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
      <Card>
        <CardContent className="p-6 text-center text-muted-foreground">
          此运行使用旧版"一次性生成"模式，不支持链式确认流程。
          {run && (
            <Button variant="outline" size="sm" className="ml-4" onClick={onViewTable}>
              查看三表工作台
            </Button>
          )}
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid gap-4">
      {/* 步骤指示器 */}
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
                    {/* 状态图标 */}
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

                  {/* 操作按钮（仅在活跃步骤显示） */}
                  {isActive && !isGenerating && (
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

              {/* 箭头分隔 */}
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

      {/* 消息提示 */}
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

      {/* 全部完成 */}
      {currentStage === "complete" && (
        <Card className="border-[#34C759]">
          <CardContent className="p-4 flex items-center gap-3">
            <CheckCircle2 size={22} className="text-[#34C759]" />
            <div>
              <strong className="text-sm">链式确认流程已完成</strong>
              <p className="text-xs text-muted-foreground">
                PFD、PFMEA、CP 三个阶段均已确认。现在可以进入三表工作台查看和导出。
              </p>
            </div>
            <Button size="sm" className="ml-auto" onClick={onViewTable}>
              进入三表工作台
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------

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

function stageLabel(key: ChainStageKey): string {
  return (
    STEPS.find((s) => s.key === key)?.label ?? key.toUpperCase()
  );
}
