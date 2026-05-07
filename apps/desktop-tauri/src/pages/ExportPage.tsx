import { useState } from "react";
import { AlertTriangle, CheckCircle2, Download, FolderOpen } from "lucide-react";
import { exportRun, openOutputDir, selectOutputDir } from "../api/client";
import type { DesktopRun, ExportResponse } from "../api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";

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

  return (
    <section className="grid gap-4">
      <div>
        <span className="text-primary text-xs font-bold">导出</span>
        <h2 className="mt-1 mb-0 text-[22px]">导出与提交包</h2>
      </div>

      <Card className="max-w-[760px]">
        <CardContent className="p-[18px] grid gap-4">
          <label className="grid gap-[7px]">
            <span className="text-[#56565b] text-[13px]">输出目录</span>
            <div className="flex gap-2 items-center">
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

          <div className="flex items-center gap-2.5 min-h-12 flex-wrap">
            <Button disabled={!run} onClick={() => void doExport("draft")}>
              <Download size={16} className="mr-[7px]" />
              草案导出
            </Button>
            <Button
              variant="outline"
              disabled={!run || !gateAllowed}
              onClick={() => void doExport("final")}
            >
              <Download size={16} className="mr-[7px]" />
              正式导出
            </Button>
            <Button variant="outline" disabled={!outputDir} onClick={() => void openOutputDir(outputDir)}>
              <FolderOpen size={16} className="mr-[7px]" />
              打开目录
            </Button>
          </div>

          <div className="grid gap-2 rounded-lg border border-border bg-muted/30 p-3">
            <div className="flex items-center gap-2 text-xs font-bold text-primary">
              {gateAllowed ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
              <span>正式导出质量门</span>
            </div>
            <p className="m-0 text-[13px] leading-[1.45] text-[#56565b]">
              {gateUnavailable
                ? "没有运行结果，无法判断正式导出质量门。"
                : qualityGate
                  ? gateAllowed
                    ? "已放行，可以提交正式导出。"
                    : `未放行：${qualityGate.reason}`
                  : "暂未读取到质量门结果，正式导出前请先确认复核任务。"}
            </p>
          </div>

          <span className="text-[#56565b] text-[13px]">
            {run ? `当前运行 #${run.id}：${run.status_display || run.status}` : "暂无运行结果，不能导出。"}
          </span>

          {message && (
            <pre
              className={
                message.includes("失败") || message.includes("原始错误") || message.includes("阻断")
                  ? "m-0 p-3 border border-[#f0b4ae] rounded-lg bg-[#fff6f5] text-[#9f1c12] whitespace-pre-wrap"
                  : "text-[#56565b] text-[13px]"
              }
            >
              {message}
            </pre>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 gap-3">
        {exportFiles.map(([name, path]) => (
          <Card key={name}>
            <CardContent className="p-4 grid gap-2">
              <Download size={18} />
              <strong>{name}</strong>
              <p className="text-muted-foreground text-[13px] m-0">{path}</p>
            </CardContent>
          </Card>
        ))}
        {exportFiles.length === 0 && (
          <div className="p-6 text-muted-foreground">暂无最近导出文件。</div>
        )}
      </div>
    </section>
  );
}

function extractQualityGate(run: DesktopRun | null, exported: ExportResponse | null): QualityGateSummary | null {
  return normalizeGate(exported?.quality_gate ?? extractResultGate(run?.current_result));
}

function extractResultGate(result: Record<string, unknown> | undefined): Record<string, unknown> | null {
  if (!result) return null;
  const qualityGate = result.quality_gate;
  if (qualityGate && typeof qualityGate === "object" && !Array.isArray(qualityGate)) return qualityGate as Record<string, unknown>;
  const qualityGates = result.quality_gates;
  if (qualityGates && typeof qualityGates === "object" && !Array.isArray(qualityGates)) {
    const exportGate = (qualityGates as Record<string, unknown>).export_gate ?? (qualityGates as Record<string, unknown>).export;
    if (exportGate && typeof exportGate === "object" && !Array.isArray(exportGate)) return exportGate as Record<string, unknown>;
  }
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
