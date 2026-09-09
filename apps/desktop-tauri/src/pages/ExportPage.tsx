import { useEffect, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Download, FileCheck2, FolderOpen, PackageCheck, SendHorizontal } from "lucide-react";
import { exportRun, openOutputDir, selectOutputDir } from "../api/client";
import type { DesktopRun, ExportResponse } from "../api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState, Notice, StatusPill, Surface } from "@/components/ui/experience";
import { cn } from "@/lib/utils";

type ExportPageProps = {
  run: DesktopRun | null;
};

type QualityGateSummary = {
  allowed: boolean;
  reason: string;
};

export default function ExportPage({ run }: ExportPageProps) {
  const [outputDir, setOutputDir] = useState(run?.output_dir ?? "");
  const [lastExport, setLastExport] = useState<ExportResponse | null>(null);
  const [message, setMessage] = useState("");
  const qualityGate = extractQualityGate(run, lastExport);

  useEffect(() => {
    setOutputDir(run?.output_dir ?? "");
    setLastExport(null);
    setMessage("");
  }, [run?.id, run?.output_dir]);

  async function chooseOutputDir() {
    const path = await selectOutputDir();
    if (path) setOutputDir(path);
  }

  async function doExport(mode: "draft" | "final") {
    if (!run) return;
    if (mode === "final" && qualityGate && !qualityGate.allowed) {
      setMessage(`正式导出未放行：${qualityGate.reason}`);
      return;
    }
    setMessage("正在导出...");
    try {
      const exported = await exportRun(run.id, mode, outputDir);
      setLastExport(exported);
      if (mode === "final" && exported.quality_gate && !isGateAllowed(exported.quality_gate)) {
        setMessage(`正式导出被阻断：${extractGateReason(exported.quality_gate)}`);
        return;
      }
      setMessage(`${mode === "draft" ? "草案" : "正式"}导出完成`);
    } catch (caught) {
      const text = caught instanceof Error ? caught.message : String(caught);
      setMessage(mode === "final" ? `正式导出被阻断：${text}` : text);
    }
  }

  const exportFiles = lastExport ? Object.entries(lastExport.exports ?? {}) : [];
  const gateUnavailable = !run;
  const gateAllowed = qualityGate?.allowed ?? false;
  const gateTone: "neutral" | "success" | "danger" = gateUnavailable ? "neutral" : gateAllowed ? "success" : "danger";
  const messageTone = message.includes("失败") || message.includes("原始错误") || message.includes("阻断") || message.includes("未放行")
    ? "danger"
    : "success";

  return (
    <section className="grid gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <span className="text-primary text-xs font-bold">Export</span>
          <h2 className="mt-1 mb-0 text-[22px]">质量门提交包</h2>
          <p className="m-0 mt-1 text-[13px] text-muted-foreground">
            先产出草案包用于核对，正式提交包只有在质量门放行后才可生成。
          </p>
        </div>
        <StatusPill tone={gateTone} icon={gateAllowed ? CheckCircle2 : AlertTriangle}>
          {gateUnavailable ? "等待运行" : gateAllowed ? "质量门已放行" : "质量门未放行"}
        </StatusPill>
      </div>

      <div className="grid grid-cols-[repeat(auto-fit,minmax(190px,1fr))] gap-2.5">
        <FlowStep
          icon={<FolderOpen size={16} />}
          label="1. 输出位置"
          value={outputDir ? "已指定目录" : "使用运行默认目录"}
          active={Boolean(run)}
        />
        <FlowStep
          icon={gateAllowed ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
          label="2. 质量门"
          value={gateUnavailable ? "等待运行结果" : gateAllowed ? "允许正式提交" : "先处理阻断项"}
          tone={gateTone}
          active={Boolean(run)}
        />
        <FlowStep
          icon={<PackageCheck size={16} />}
          label="3. 提交包"
          value={lastExport ? `${lastExport.export_mode === "draft" ? "草案" : "正式"}包已生成` : "尚未生成"}
          active={exportFiles.length > 0}
        />
      </div>

      <div className="grid grid-cols-[minmax(360px,1fr)_minmax(280px,0.8fr)] gap-4 max-[900px]:grid-cols-1">
        <Card>
          <CardContent className="p-[18px] grid gap-4">
            <Notice tone={gateTone === "neutral" ? "info" : gateTone} title="正式提交包质量门" icon={gateAllowed ? CheckCircle2 : AlertTriangle}>
              {gateUnavailable
                ? "没有运行结果，无法判断正式导出质量门。"
                : qualityGate
                  ? gateAllowed
                    ? "质量门已放行，可以生成正式提交包。"
                    : `未放行：${qualityGate.reason}`
                  : "暂未读取到质量门结果，正式导出前请先确认复核任务。"}
            </Notice>

            <label className="grid gap-[7px]">
              <span className="text-[#56565b] text-[13px]">输出目录</span>
              <div className="flex gap-2 items-center max-[640px]:flex-col max-[640px]:items-stretch">
                <Input
                  value={outputDir}
                  onChange={(event) => setOutputDir(event.target.value)}
                  placeholder="默认使用当前运行输出目录"
                  className="flex-1"
                />
                <Button variant="outline" size="sm" onClick={chooseOutputDir}>
                  <FolderOpen size={16} className="mr-[7px]" />
                  选择目录
                </Button>
              </div>
            </label>

            <div className="grid grid-cols-2 gap-3 max-[720px]:grid-cols-1">
              <PackageAction
                icon={<FileCheck2 size={18} />}
                title="草案包"
                description="用于内部核对，质量门未放行时也可以生成。"
                actionLabel="生成草案包"
                disabled={!run}
                onClick={() => void doExport("draft")}
              />
              <PackageAction
                icon={<SendHorizontal size={18} />}
                title="正式提交包"
                description="由质量门控制，阻断项未处理时不会放行。"
                actionLabel="生成正式包"
                disabled={!run || !gateAllowed}
                onClick={() => void doExport("final")}
                primary
              />
            </div>

            <div className="flex flex-wrap items-center gap-2.5">
              <Button variant="outline" disabled={!outputDir} onClick={() => void openOutputDir(outputDir)}>
                <FolderOpen size={16} className="mr-[7px]" />
                打开目录
              </Button>
              <span className="text-[#56565b] text-[13px]">
                {run ? `当前运行 #${run.id}：${run.status_display || run.status}` : "暂无运行结果，不能导出。"}
              </span>
            </div>

            {message && <Notice tone={messageTone}>{message}</Notice>}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-[18px] grid gap-3">
            <div>
              <h3 className="m-0 text-[17px]">最近生成的文件</h3>
              <p className="m-0 mt-1 text-[13px] text-muted-foreground">
                这里展示本次页面操作返回的提交包清单。
              </p>
            </div>
            <div className="grid gap-2">
              {exportFiles.map(([name, path]) => (
                <Surface key={name} inset="sm" className="grid gap-1">
                  <div className="flex items-center gap-2 text-[13px] font-semibold">
                    <Download size={16} />
                    <span>{name}</span>
                  </div>
                  <p className="m-0 break-words text-[12px] leading-[1.45] text-muted-foreground">{path}</p>
                </Surface>
              ))}
              {exportFiles.length === 0 && (
                <EmptyState icon={PackageCheck} title="还没有生成提交包。" className="min-h-[180px]" />
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}

function FlowStep({
  icon,
  label,
  value,
  active,
  tone = "neutral"
}: {
  icon: ReactNode;
  label: string;
  value: string;
  active?: boolean;
  tone?: "neutral" | "success" | "danger";
}) {
  return (
    <Surface inset="sm" className={cn(
      active && "border-primary/35",
      tone === "success" && "border-[#bde5c6] bg-[#f7fcf8]",
      tone === "danger" && "border-[#f0b4ae] bg-[#fff8f7]"
    )}>
      <div className={cn(
        "mb-2 flex items-center gap-2 text-xs font-semibold text-muted-foreground",
        tone === "success" && "text-[#1f8f3a]",
        tone === "danger" && "text-destructive"
      )}>
        {icon}
        {label}
      </div>
      <strong className="text-[15px]">{value}</strong>
    </Surface>
  );
}

function PackageAction({
  icon,
  title,
  description,
  actionLabel,
  disabled,
  onClick,
  primary = false
}: {
  icon: ReactNode;
  title: string;
  description: string;
  actionLabel: string;
  disabled?: boolean;
  onClick: () => void;
  primary?: boolean;
}) {
  return (
    <Surface inset="sm" className="grid gap-3">
      <div className="flex items-center gap-2">
        {icon}
        <strong className="text-[15px]">{title}</strong>
      </div>
      <p className="m-0 min-h-10 text-[13px] leading-[1.45] text-muted-foreground">{description}</p>
      <Button variant={primary ? "default" : "outline"} disabled={disabled} onClick={onClick}>
        <Download size={16} className="mr-[7px]" />
        {actionLabel}
      </Button>
    </Surface>
  );
}

function extractQualityGate(run: DesktopRun | null, exported: ExportResponse | null): QualityGateSummary | null {
  return normalizeGate(exported?.quality_gate ?? extractResultGate(run?.current_result));
}

function extractResultGate(result: Record<string, unknown> | undefined): Record<string, unknown> | null {
  if (!result) return null;
  const dashboard = result.review_dashboard;
  if (dashboard && typeof dashboard === "object" && !Array.isArray(dashboard)) {
    const finalExportAllowed = (dashboard as Record<string, unknown>).final_export_allowed;
    if (finalExportAllowed !== undefined) {
      return {
        final_export_allowed: finalExportAllowed,
        reason: text((dashboard as Record<string, unknown>).status_display, "质量门未放行")
      };
    }
  }
  const qualityGates = result.quality_gates;
  if (qualityGates && typeof qualityGates === "object" && !Array.isArray(qualityGates)) {
    const exportGate = (qualityGates as Record<string, unknown>).export_gate ?? (qualityGates as Record<string, unknown>).export;
    if (exportGate && typeof exportGate === "object" && !Array.isArray(exportGate)) return exportGate as Record<string, unknown>;
  }
  const qualityGate = result.quality_gate;
  if (qualityGate && typeof qualityGate === "object" && !Array.isArray(qualityGate)) return qualityGate as Record<string, unknown>;
  return null;
}

function normalizeGate(value: Record<string, unknown> | null | undefined): QualityGateSummary | null {
  if (!value) return null;
  const allowed =
    isTruthy(value.allow_user_export) ||
    isTruthy(value.allow_final_export) ||
    isTruthy(value.final_export_allowed) ||
    isTruthy(value.allow_export);
  const reason =
    text(value.blocked_reason) ||
    text(value.reason) ||
    text(value.message) ||
    text(value.detail) ||
    text(value.status) ||
    "质量门未放行";
  return { allowed, reason };
}

function isGateAllowed(value: unknown): boolean {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  return normalizeGate(value as Record<string, unknown>)?.allowed ?? false;
}

function extractGateReason(value: unknown): string {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "质量门未放行";
  return normalizeGate(value as Record<string, unknown>)?.reason ?? "质量门未放行";
}

function isTruthy(value: unknown): boolean {
  return value === true || value === "true" || value === 1 || value === "1" || value === "yes";
}

function text(value: unknown, fallback = ""): string {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}
