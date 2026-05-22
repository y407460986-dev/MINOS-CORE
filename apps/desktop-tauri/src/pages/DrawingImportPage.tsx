import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  FileText,
  FolderOpen,
  GitBranch,
  Layers3,
  Loader2,
  Play,
  RefreshCw,
  Upload
} from "lucide-react";
import { ChainStepper } from "../components/ChainStepper";
import type { ChainState } from "../api/types";
import {
  LocalServiceConnectionError,
  applyLinkageSync,
  startChainRun,
  getRun,
  createProject,
  getDrawingAnalysis,
  getPartFamily,
  selectDrawingFile,
  selectOutputDir
} from "../api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Notice, StatusPill, Surface } from "@/components/ui/experience";
import type {
  DesktopRun,
  DrawingAnalysisMode,
  DrawingAnalysisResponse,
  LinkageApplySyncResponse,
  PartFamilyResponse
} from "../api/types";

type DrawingImportPageProps = {
  activeRun: DesktopRun | null;
  onRunCreated: (run: DesktopRun) => void;
  onRunUpdated: (run: DesktopRun) => void;
  onOpenWorkbench: () => void;
};

type ImportInsights = {
  identity: {
    partName: string;
    drawingNumber: string;
    revision: string;
  };
  partFamily: string;
  evidenceCount: number;
  drawingItemCount: number;
  drawingReviewCount: number;
  pfdStepCount: number;
  pfdReviewCount: number;
  linkageIssueCount: number;
  syncSuggestionCount: number;
  generationTitle: string;
  generationMessage: string;
  failureDetail: string;
  blockedStage: string;
  recognition: {
    ocrStatus: string;
    visionStatus: string;
    source: string;
    pendingFieldCount: number;
  };
};

const analysisMode: DrawingAnalysisMode = "ocr_only";

const analysisBlockKeys = [
  "materials",
  "surface_treatments",
  "dimensions",
  "tolerances",
  "special_characteristics",
  "technical_requirements",
  "inspection_requirements",
  "manufacturing_clues",
  "uncertainties"
];

const chainStageKeys = ["pfd", "pfmea", "cp"] as const;

type StoryTone = "idle" | "running" | "active" | "success" | "failed";

type StatusStory = {
  tone: StoryTone;
  badge: string;
  title: string;
  detail: string;
};

export default function DrawingImportPage({ activeRun, onRunCreated, onRunUpdated, onOpenWorkbench }: DrawingImportPageProps) {
  const [drawingPath, setDrawingPath] = useState("");
  const [outputDir, setOutputDir] = useState("");
  const [runState, setRunState] = useState<"idle" | "running" | "failed" | "blocked" | "chain_active">("idle");
  const [completedRun, setCompletedRun] = useState<DesktopRun | null>(null);
  const [chainState, setChainState] = useState<ChainState | null>(null);
  const [analysisOverride, setAnalysisOverride] = useState<DrawingAnalysisResponse | null>(null);
  const [partFamilyOverride, setPartFamilyOverride] = useState<PartFamilyResponse | null>(null);
  const [statusStory, setStatusStory] = useState<StatusStory | null>(null);

  const visibleRun = completedRun && completedRun.id !== activeRun?.id ? completedRun : activeRun ?? completedRun;
  const visibleChainState = useMemo(() => extractChainState(visibleRun) ?? chainState, [chainState, visibleRun]);
  const insights = useMemo(
    () => buildImportInsights(visibleRun, analysisOverride, partFamilyOverride),
    [analysisOverride, partFamilyOverride, visibleRun]
  );
  const hasExistingTask = Boolean(visibleRun);
  const primaryStory = useMemo(
    () => statusStory ?? buildPrimaryStory(visibleRun, visibleChainState, runState, insights),
    [insights, runState, statusStory, visibleChainState, visibleRun]
  );
  const hasFailure = primaryStory.tone === "failed";
  const isStageGenerating = hasRunningStage(visibleChainState);
  const isBusy = runState === "running" || statusStory?.tone === "running";
  const canStart = Boolean(drawingPath.trim() && !isBusy);
  const startButtonLabel = runState === "running" ? "启动中..." : hasExistingTask ? "启动新任务" : "开始导入";

  useEffect(() => {
    const nextChainState = extractChainState(activeRun);
    if (nextChainState) setChainState(nextChainState);
  }, [activeRun]);

  async function chooseDrawing() {
    const path = await selectDrawingFile();
    if (path) setDrawingPath(path);
  }

  async function chooseOutput() {
    const path = await selectOutputDir();
    if (path) setOutputDir(path);
  }

  function updateStory(tone: StoryTone, title: string, detail: string, badge = storyBadge(tone)) {
    setStatusStory({ tone, badge, title, detail });
  }

  // ---- 链式流程 ----

  async function startChainFlow() {
    setStatusStory(null);
    setAnalysisOverride(null); setPartFamilyOverride(null);
    setCompletedRun(null);
    if (!drawingPath.trim()) {
      setRunState("blocked");
      updateStory("failed", "请先选择图纸", "需要指定图纸文件后才能启动新的链式生成。", "缺少输入");
      return;
    }
    setRunState("running");
    updateStory("running", "正在建立项目记录", "本地服务正在创建项目并准备链式流程。", "启动中");
    try {
      const autoProjectName = drawingPath.split(/[/\\]/).pop()?.replace(/\.[^.]+$/, "") || "MINOS-Project";
      const project = await createProject({
        project_name: autoProjectName, drawing_path: drawingPath,
        output_dir: outputDir,
        context: { source: "tauri-react-desktop", analysis_mode: analysisMode, ocr_engine: "auto" },
      });
      updateStory("running", "正在分析图纸", "第一阶段会生成过程流程图，完成后进入工作台确认。", "生成中");
      const run = await startChainRun(project.id);
      setCompletedRun(run); onRunCreated(run);
      setRunState("chain_active");
      const cs = extractChainState(run);
      setChainState(cs);
      const feedback = chainStartFeedback(run, cs);
      updateStory(feedback.error ? "failed" : "active", feedback.status, feedback.error || resumeContextMessage(run, cs, buildImportInsights(run, null, null)), feedback.error ? "失败" : "已启动");
    } catch (caught) {
      setRunState("failed");
      updateStory("failed", isLocalServiceProblem(caught) ? "本地服务未连接" : "链式启动失败", errorMessage(caught), "失败");
    }
  }

  function extractChainState(run: DesktopRun | null): ChainState | null {
    if (!run) return null;
    if (run.chain_stages) return run.chain_stages;
    const current = record(run.current_result).chain_stages;
    if (current && typeof current === "object") return current as ChainState;
    const raw = record(run.raw_result).chain_stages;
    if (raw && typeof raw === "object") return raw as ChainState;
    return null;
  }

  async function refreshVisibleRun() {
    if (!visibleRun) return;
    updateStory("running", "正在刷新任务上下文", `运行 #${visibleRun.id} 正在重新读取。`, "刷新中");
    try {
      const latest = await getRun(visibleRun.id);
      setCompletedRun(latest);
      onRunUpdated(latest);
      setChainState(extractChainState(latest));
      setRunState(latest.failure_message ? "failed" : "chain_active");
      updateStory(latest.failure_message ? "failed" : "success", "任务上下文已刷新", latest.failure_message || "当前运行、阶段状态和输出路径已同步。", latest.failure_message ? "失败" : "已刷新");
    } catch (caught) {
      updateStory("failed", "任务上下文刷新失败", errorMessage(caught), "失败");
    }
  }

  async function refreshDrawingAnalysis() {
    if (!visibleRun) return;
    updateStory("running", "正在刷新图纸识别", `运行 #${visibleRun.id} 的识别摘要正在重新读取。`, "刷新中");
    try {
      setAnalysisOverride(await getDrawingAnalysis(visibleRun.id));
      updateStory("success", "图纸识别状态已刷新", "OCR、AI 视觉和待确认字段摘要已更新。", "已刷新");
    } catch (caught) {
      updateStory("failed", "图纸识别刷新失败", errorMessage(caught), "失败");
    }
  }

  async function refreshPartFamily() {
    if (!visibleRun) return;
    updateStory("running", "正在读取零件族", `运行 #${visibleRun.id} 的零件族判断正在刷新。`, "刷新中");
    try {
      const response = await getPartFamily(visibleRun.id);
      setPartFamilyOverride(response);
      updateStory("success", "零件族已刷新", response.part_family ? `当前判断：${response.part_family}` : "零件族判断已更新。", "已刷新");
    } catch (caught) {
      updateStory("failed", "零件族刷新失败", errorMessage(caught), "失败");
    }
  }

  async function applySync() {
    if (!visibleRun) return;
    updateStory("running", "正在应用联动同步", "过程流程图、失效模式分析和控制计划的关联差异正在同步。", "同步中");
    try {
      const response = await applyLinkageSync(visibleRun.id, {
        apply_all: true,
        reason: "桌面端应用联动同步"
      });
      const updatedRun = runFromLinkageResponse(visibleRun, response);
      if (updatedRun) {
        setCompletedRun(updatedRun);
        onRunUpdated(updatedRun);
      }
      updateStory("success", "联动同步已完成", syncResultMessage(response), "已同步");
    } catch (caught) {
      updateStory("failed", "联动同步失败", errorMessage(caught), "失败");
    }
  }

  return (
    <section className="grid gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <span className="text-primary text-xs font-bold">Drawing Import</span>
          <h2 className="mt-1 mb-0 text-[22px]">图纸导入与任务恢复</h2>
        </div>
        {visibleRun && (
          <StatusPill tone={hasFailure ? "danger" : "success"} icon={hasFailure ? AlertTriangle : CheckCircle2}>
            当前运行 #{visibleRun.id}
          </StatusPill>
        )}
      </div>

      <StatusRail story={primaryStory} />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px] xl:items-start">
        <Surface className="grid content-start gap-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-[7px] text-primary text-xs font-bold">
                <FileText size={16} />
                <span>导入命令</span>
              </div>
              <Button
                disabled={!canStart}
                onClick={startChainFlow}
                className="justify-center min-w-[150px]"
              >
                {isBusy ? <Loader2 size={16} className="mr-[7px] animate-spin" /> : <Play size={16} className="mr-[7px]" />}
                {startButtonLabel}
              </Button>
            </div>

            <div className="grid gap-3 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
              <label className="grid gap-[7px]">
                <span className="text-[13px] text-muted-foreground">图纸文件</span>
                <div className="flex gap-2 items-center">
                  <Input value={drawingPath} onChange={(event) => setDrawingPath(event.target.value)} placeholder="选择 PDF、PNG、JPG 或 JPEG" className="flex-1" />
                  <Button variant="outline" size="sm" onClick={chooseDrawing}>
                    <Upload size={16} className="mr-[7px]" />
                    选择图纸
                  </Button>
                </div>
              </label>
              <label className="grid gap-[7px]">
                <span className="text-[13px] text-muted-foreground">输出目录</span>
                <div className="flex gap-2 items-center">
                  <Input value={outputDir} onChange={(event) => setOutputDir(event.target.value)} placeholder="选择工作包输出目录" className="flex-1" />
                  <Button variant="outline" size="sm" onClick={chooseOutput}>
                    <FolderOpen size={16} className="mr-[7px]" />
                    选择目录
                  </Button>
                </div>
              </label>
            </div>

            <div className="text-xs leading-[1.45] text-muted-foreground">
              导入页只负责启动和恢复任务。过程流程图、PFMEA、控制计划的确认仍在工作台完成。
            </div>

            <ChainStepper
              chainState={visibleChainState}
              run={visibleRun}
              isGenerating={isStageGenerating}
              onViewTable={visibleRun ? onOpenWorkbench : undefined}
              compact
              readOnly
              title="阶段轨"
            />
        </Surface>

        <Surface className="grid content-start gap-4">
            <div className="flex items-center gap-[7px] text-primary text-xs font-bold">
              {hasFailure ? <AlertTriangle size={16} /> : <ArrowRight size={16} />}
              <span>右侧检查器</span>
            </div>

            <div className="grid gap-2">
              <h3 className="m-0 text-base leading-[1.35]">
                {visibleRun ? `运行 #${visibleRun.id}` : "暂无活动任务"}
              </h3>
              <p className="m-0 text-[13px] leading-[1.45] text-muted-foreground">
                {visibleRun
                  ? resumeContextMessage(visibleRun, visibleChainState, insights)
                  : "启动后会在这里保留当前运行，切回导入页时可以继续查看上下文。"}
              </p>
              <dl className="grid gap-[7px] m-0">
                {[
                  ["状态", visibleRun ? visibleRun.status_display || visibleRun.status : "未启动"],
                  ["输出", visibleRun?.output_dir || outputDir || "未指定"],
                  ["阻断环节", insights.blockedStage || "无"]
                ].map(([dt, dd]) => (
                  <div key={dt} className="flex justify-between gap-2.5 min-w-0">
                    <dt className="text-muted-foreground text-xs">{dt}</dt>
                    <dd className="m-0 min-w-0 text-foreground text-[13px] text-right break-words">{dd}</dd>
                  </div>
                ))}
              </dl>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" size="sm" disabled={!visibleRun} onClick={onOpenWorkbench}>
                  打开三表工作台
                </Button>
                <Button variant="outline" size="sm" disabled={!visibleRun} onClick={() => void refreshVisibleRun()}>
                  <RefreshCw size={15} className="mr-[7px]" />刷新上下文
                </Button>
              </div>
            </div>

            <div className="grid gap-3 border-0 border-t border-solid border-[hsl(var(--surface-border))] pt-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-[7px] text-primary text-xs font-bold">
                  <ClipboardCheck size={16} />
                  <span>图纸识别</span>
                </div>
                <Button variant="outline" size="sm" disabled={!visibleRun} onClick={() => void refreshDrawingAnalysis()}>
                  <RefreshCw size={15} className="mr-[7px]" />刷新识别
                </Button>
              </div>
              <h3 className="m-0 text-base leading-[1.35]">{insights.identity.partName}</h3>
              <dl className="grid gap-[7px] m-0">
                {[["图号", insights.identity.drawingNumber], ["版本", insights.identity.revision]].map(([dt, dd]) => (
                  <div key={dt} className="flex justify-between gap-2.5 min-w-0">
                    <dt className="text-muted-foreground text-xs">{dt}</dt>
                    <dd className="m-0 min-w-0 text-foreground text-[13px] text-right break-words">{dd}</dd>
                  </div>
                ))}
              </dl>
              <div className="flex flex-wrap gap-2">
                <StatusPill tone="neutral">OCR {insights.recognition.ocrStatus}</StatusPill>
                <StatusPill tone="neutral">视觉 {insights.recognition.visionStatus}</StatusPill>
                <StatusPill tone="neutral">待确认 {insights.recognition.pendingFieldCount}</StatusPill>
              </div>
            </div>

            <div className="grid gap-3 border-0 border-t border-solid border-[hsl(var(--surface-border))] pt-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-[7px] text-primary text-xs font-bold">
                  <Layers3 size={16} />
                  <span>零件族</span>
                </div>
                <Button variant="outline" size="sm" disabled={!visibleRun} onClick={() => void refreshPartFamily()}>
                  <RefreshCw size={15} className="mr-[7px]" />重新识别
                </Button>
              </div>
              <h3 className="m-0 text-base leading-[1.35]">{insights.partFamily}</h3>
            </div>

            <div className="grid gap-3 border-0 border-t border-solid border-[hsl(var(--surface-border))] pt-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-[7px] text-primary text-xs font-bold">
                  <GitBranch size={16} />
                  <span>过程流程图</span>
                </div>
                <Button
                  variant="outline" size="sm"
                  disabled={!visibleRun || (insights.syncSuggestionCount === 0 && insights.linkageIssueCount === 0)}
                  onClick={() => void applySync()}
                >
                  应用联动同步
                </Button>
              </div>
              <dl className="grid gap-[7px] m-0">
                {[["工序", String(insights.pfdStepCount)], ["待确认", String(insights.pfdReviewCount)], ["联动差异", String(insights.linkageIssueCount)]].map(([dt, dd]) => (
                  <div key={dt} className="flex justify-between gap-2.5 min-w-0">
                    <dt className="text-muted-foreground text-xs">{dt}</dt>
                    <dd className="m-0 min-w-0 text-foreground text-[13px] text-right break-words">{dd}</dd>
                  </div>
                ))}
              </dl>
            </div>
        </Surface>
      </div>
    </section>
  );
}

function resumeContextMessage(run: DesktopRun, chainState: ChainState | null, insights: ImportInsights): string {
  if (run.failure_message || hasFailedStage(chainState)) {
    return "上次任务没有完整结束，可以继续打开工作台处理，也可以刷新状态后按阶段恢复。";
  }
  if (hasRunningStage(chainState)) {
    return "任务仍在后台生成，下方阶段轨会显示当前进度；需要编辑和确认时进入工作台。";
  }
  if (chainState?.current_stage === "complete") {
    return "链式阶段已完成，可以进入工作台复核并导出。";
  }
  if (chainState) {
    return `已生成 ${insights.pfdStepCount} 道工序，当前停在 ${stageName(chainState.current_stage)}。`;
  }
  return `运行状态：${run.status_display || run.status}。可继续进入工作台查看三表。`;
}

function StatusRail({ story }: { story: StatusStory }) {
  const tone = statusTone(story.tone);
  const icon = story.tone === "running" ? undefined : story.tone === "failed" ? AlertTriangle : CheckCircle2;
  const activity = story.tone === "running" ? "spin" : "none";

  return (
    <Notice tone={tone} title={story.title} icon={icon}>
      <div className="flex flex-wrap items-center gap-2">
        <span>{story.detail}</span>
        <StatusPill tone={tone} activity={activity}>{story.badge}</StatusPill>
      </div>
    </Notice>
  );
}

function buildPrimaryStory(
  run: DesktopRun | null,
  chainState: ChainState | null,
  runState: "idle" | "running" | "failed" | "blocked" | "chain_active",
  insights: ImportInsights
): StatusStory {
  if (runState === "blocked") {
    return { tone: "failed", badge: "缺少输入", title: "请先选择图纸", detail: "需要指定图纸文件后才能启动新的链式生成。" };
  }
  if (runState === "running" || hasRunningStage(chainState)) {
    return { tone: "running", badge: "生成中", title: "链式流程正在运行", detail: "图纸识别、过程流程图和下游表会按阶段推进。" };
  }
  if (run?.failure_message || hasFailedStage(chainState) || insights.failureDetail) {
    return { tone: "failed", badge: "需要处理", title: insights.generationTitle || "任务未完成", detail: run?.failure_message || failedStageMessage(chainState) || insights.failureDetail };
  }
  if (chainState?.current_stage === "complete") {
    return { tone: "success", badge: "已完成", title: "链式阶段已完成", detail: "可以进入工作台复核并导出提交包。" };
  }
  if (run || runState === "chain_active") {
    return { tone: "active", badge: "可继续", title: insights.generationTitle, detail: insights.generationMessage };
  }
  return { tone: "idle", badge: "待启动", title: "选择图纸后启动新任务", detail: "也可以继续已有运行，并从工作台完成三表确认。" };
}

function storyBadge(tone: StoryTone): string {
  const labels: Record<StoryTone, string> = {
    idle: "待启动",
    running: "处理中",
    active: "可继续",
    success: "已完成",
    failed: "需要处理"
  };
  return labels[tone];
}

function statusTone(tone: StoryTone): "neutral" | "info" | "success" | "warning" | "danger" {
  if (tone === "failed") return "danger";
  if (tone === "success") return "success";
  if (tone === "running" || tone === "active") return "info";
  return "neutral";
}

function hasFailedStage(chainState: ChainState | null): boolean {
  return Boolean(chainState && chainStageKeys.some((stage) => chainState[stage].status === "failed"));
}

function hasRunningStage(chainState: ChainState | null): boolean {
  return Boolean(chainState && chainStageKeys.some((stage) => chainState[stage].status === "running"));
}

function failedStageMessage(chainState: ChainState | null): string {
  if (!chainState) return "任务启动或阶段生成失败。";
  for (const stage of chainStageKeys) {
    if (chainState[stage].status === "failed") return `${stageName(stage)}生成失败。`;
  }
  return "任务启动或阶段生成失败。";
}

function stageName(stage: ChainState["current_stage"]): string {
  const map: Record<ChainState["current_stage"], string> = {
    pfd: "过程流程图",
    pfmea: "失效模式分析",
    cp: "控制计划",
    complete: "已完成"
  };
  return map[stage] ?? String(stage);
}

function buildImportInsights(
  run: DesktopRun | null,
  analysisOverride: DrawingAnalysisResponse | null,
  partFamilyOverride: PartFamilyResponse | null
): ImportInsights {
  const result = record(run?.current_result);
  const analysis = analysisOverride ?? (record(result.drawing_analysis) as DrawingAnalysisResponse);
  const identity = record(analysis.drawing_identity);
  const analysisMetadata = record(analysis.metadata);
  const adapterMetadata = record(analysisMetadata.adapter_metadata);
  const inputs = record(result.inputs);
  const context = record(inputs.context);
  const metadata = record(result.metadata);
  const resultRecognition = record(result.recognition);
  const metadataRecognition = record(metadata.recognition);
  const analysisRecognition = record(analysisMetadata.recognition);
  const processFlow = record(result.process_flow);
  const qualityGates = record(result.quality_gates);
  const drawingGate = record(qualityGates.drawing_recognition);
  const pfdGate = record(qualityGates.process_flow);
  const linkageReport = record(result.linkage_report);
  const linkageMap = record(result.linkage_map);
  const statusDisplay = text(result.status_display ?? run?.status_display ?? result.status ?? run?.status, "已生成");
  const blockedStage = text(result.blocked_stage ?? run?.blocked_stage);
  const drawingItemCount = analysisBlockKeys.reduce((count, key) => count + array(analysis[key]).length, 0);
  const drawingReviewCount = drawingPendingFieldCount(analysis, drawingGate);
  const pfdSteps = array(processFlow.steps);
  const pfdReviewCount =
    pfdSteps.filter((item) => {
      const row = record(item);
      const rowStatus = text(row.review_status ?? row.row_status ?? row.status);
      return Boolean(row.needs_confirmation) || rowStatus.includes("确认") || rowStatus.includes("复核");
    }).length + array(pfdGate.needs_confirmation_items).length;
  const syncSuggestions = firstNonEmptyArray(linkageReport.sync_suggestions, linkageMap.sync_suggestions, result.sync_suggestions);
  const linkageIssues = firstNonEmptyArray(linkageReport.sync_issues, result.linkage_gaps, linkageMap.gaps);
  const failureMessage = text(run?.failure_message);
  const visionStreamError = isVisionStreamReadError(failureMessage);
  const analysisMode = text(context.analysis_mode ?? metadata.analysis_mode ?? analysisMetadata.analysis_mode, "hybrid");
  const ocrStatus = recognitionStatusLabel(
    firstStatusText(
      analysisMetadata.ocr_status,
      metadata.ocr_status,
      result.ocr_status,
      adapterMetadata.ocr_status,
      resultRecognition.ocr,
      metadataRecognition.ocr,
      analysisRecognition.ocr,
      analysisMetadata.ocr,
      metadata.ocr,
      result.ocr
    ),
    analysisMode === "vision_only" ? "未启用" : visionStreamError ? "已保留" : array(analysis.evidence).length > 0 ? "已完成" : "等待识别"
  );
  const visionStatus = recognitionStatusLabel(
    firstStatusText(
      analysisMetadata.vision_status,
      metadata.vision_status,
      result.vision_status,
      adapterMetadata.vision_status,
      resultRecognition.vision,
      metadataRecognition.vision,
      analysisRecognition.vision,
      analysisMetadata.vision,
      metadata.vision,
      result.vision
    ),
    analysisMode === "ocr_only" ? "未启用" : visionStreamError ? "中断" : drawingItemCount > 0 ? "已完成" : "等待识别"
  );
  const recognitionSource = recognitionSourceLabel(
    firstStatusText(
      analysisMetadata.recognition_source,
      metadata.recognition_source,
      result.recognition_source,
      adapterMetadata.recognition_source,
      adapterMetadata.source,
      resultRecognition.source,
      metadataRecognition.source,
      analysisRecognition.source,
      context.analysis_mode
    ) || analysisMode
  );

  return {
    identity: {
      partName: text(identity.part_name, "未识别零件名"),
      drawingNumber: text(identity.drawing_number, "未识别图号"),
      revision: text(identity.revision, "未识别")
    },
    partFamily: text(partFamilyOverride?.part_family ?? context.part_family ?? metadata.part_family ?? record(result.part_family).part_family, "未设置"),
    evidenceCount: array(analysis.evidence).length,
    drawingItemCount,
    drawingReviewCount,
    pfdStepCount: pfdSteps.length,
    pfdReviewCount,
    linkageIssueCount: linkageIssues.length,
    syncSuggestionCount: syncSuggestions.length,
    generationTitle: failureMessage ? "生成未完成" : blockedStage ? "生成已停在需处理环节" : "三表草案已就绪",
    generationMessage: visionStreamError
      ? "AI 视觉识别中断，已保留 OCR 识别结果。"
      : userFacingMessage(failureMessage) || `运行状态：${statusDisplay}。图纸识别、零件族和过程流程图已汇总到下方确认区。`,
    failureDetail: visionStreamError ? `详情：\n${failureMessage}` : "",
    blockedStage,
    recognition: {
      ocrStatus,
      visionStatus,
      source: recognitionSource,
      pendingFieldCount: drawingReviewCount
    }
  };
}

function drawingPendingFieldCount(analysis: DrawingAnalysisResponse, drawingGate: Record<string, unknown>): number {
  const pending = new Set<string>();
  for (const value of [...array(drawingGate.pending_fields), ...array(drawingGate.needs_confirmation_items)]) {
    const key = text(value);
    if (key) pending.add(key);
  }
  for (const value of array(drawingGate.manual_review_items)) {
    const item = record(value);
    const key = text(item.value ?? item.target ?? item.field ?? item.id);
    if (key) pending.add(key);
  }
  for (const blockKey of analysisBlockKeys) {
    array(analysis[blockKey]).forEach((value, index) => {
      const item = record(value);
      if (!item.needs_confirmation) return;
      pending.add(`${blockKey}:${text(item.item_id ?? item.id ?? item.name ?? item.label, String(index))}`);
    });
  }
  return pending.size;
}

function recognitionSourceLabel(value: unknown): string {
  const raw = text(value, "hybrid");
  const lowered = raw.toLowerCase();
  if (lowered.includes("hybrid") || lowered.includes("mixed") || (lowered.includes("ocr") && lowered.includes("vision"))) return "混合识别";
  if (lowered.includes("ocr_only") || lowered.includes("ocr")) return "仅 OCR";
  if (lowered.includes("vision_only") || lowered.includes("vision")) return "仅 AI 视觉";
  return normalizeLocalServiceWording(raw);
}

function recognitionStatusLabel(value: unknown, fallback: string): string {
  const raw = text(value, fallback);
  const lowered = raw.toLowerCase();
  if (["ok", "success", "succeeded", "complete", "completed", "done", "ready", "used", "available"].includes(lowered)) return "已完成";
  if (["pending", "queued", "waiting"].includes(lowered)) return "等待识别";
  if (["running", "processing", "started", "in_progress"].includes(lowered)) return "识别中";
  if (["partial", "partially_completed"].includes(lowered)) return "部分完成";
  if (["skipped", "disabled", "not_enabled", "not enabled", "off"].includes(lowered)) return "未启用";
  if (lowered.includes("stream_read_error") || lowered.includes("interrupted") || lowered.includes("aborted") || lowered.includes("timeout")) return "中断";
  if (lowered.includes("failed") || lowered.includes("failure") || lowered.includes("error")) return "识别失败";
  return normalizeLocalServiceWording(raw);
}

function firstStatusText(...values: unknown[]): string {
  for (const value of values) {
    if (value === null || value === undefined || value === "") continue;
    const row = record(value);
    if (Object.keys(row).length > 0) {
      const nested = firstStatusText(row.status, row.state, row.result, row.message, row.code);
      if (nested) return nested;
      continue;
    }
    const raw = text(value);
    if (raw) return raw;
  }
  return "";
}

function runFromLinkageResponse(baseRun: DesktopRun, response: LinkageApplySyncResponse): DesktopRun | null {
  if (response.run) return response.run;
  if (response.current_result) {
    return { ...baseRun, current_result: response.current_result };
  }
  return null;
}

function syncResultMessage(response: LinkageApplySyncResponse): string {
  if (response.message) return response.message;
  if (typeof response.applied_count === "number") {
    return `联动同步已应用 ${response.applied_count} 项。`;
  }
  return "联动同步已提交。";
}

function isLocalServiceProblem(caught: unknown): boolean {
  const message = rawErrorMessage(caught).toLowerCase();
  return caught instanceof LocalServiceConnectionError || message.includes("failed to fetch") || message.includes("networkerror") || message.includes("本地服务未连接");
}

function isProblemMessage(message: string): boolean {
  const value = message.toLowerCase();
  return value.includes("未连接") || value.includes("returned") || value.includes("失败") || value.includes("error") || value.includes("中断");
}

function errorMessage(caught: unknown): string {
  return userFacingMessage(rawErrorMessage(caught));
}

function rawErrorMessage(caught: unknown): string {
  return caught instanceof Error ? caught.message : String(caught);
}

function userFacingMessage(message: string): string {
  const normalized = normalizeLocalServiceWording(message);
  if (!isVisionStreamReadError(normalized)) return normalized;
  return ["AI 视觉识别中断，已保留 OCR 识别结果。", "", "详情：", message].join("\n");
}

function chainStartFeedback(run: DesktopRun, chainState: ChainState | null): { status: string; error: string } {
  const failure = text(run.failure_message);
  const pfdStatus = chainState?.pfd?.status;
  if (pfdStatus === "failed" || failure) {
    return {
      status: "过程流程图生成失败，请查看原始错误。",
      error: failure
    };
  }
  if (pfdStatus === "generated") {
    return { status: "过程流程图已生成，请确认。", error: "" };
  }
  if (pfdStatus === "running") {
    return { status: "过程流程图正在生成...", error: "" };
  }
  return { status: "链式流程已启动，请刷新阶段状态。", error: "" };
}

function isVisionStreamReadError(message: string): boolean {
  const value = message.toLowerCase();
  return (
    value.includes("stream_read_error") ||
    (value.includes("stream") && value.includes("read") && value.includes("error"))
  );
}

function normalizeLocalServiceWording(message: string): string {
  return message.replace(/api\s*离线/gi, "本地服务未连接").replace(/api\s*offline/gi, "本地服务未连接");
}

function record(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function array(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function firstNonEmptyArray(...values: unknown[]): unknown[] {
  for (const value of values) {
    const items = array(value);
    if (items.length > 0) return items;
  }
  return [];
}

function text(value: unknown, fallback = ""): string {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}
