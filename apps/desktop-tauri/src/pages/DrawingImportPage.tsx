import { useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  FolderOpen,
  GitBranch,
  Layers3,
  Play,
  RefreshCw,
  Upload
} from "lucide-react";
import { ChainStepper } from "../components/ChainStepper";
import type { ChainState } from "../api/types";
import { SegmentedControl } from "../components/SegmentedControl";
import {
  LocalServiceConnectionError,
  applyLinkageSync,
  startChainRun,
  getChainState,
  getRun,
  confirmPfdStage,
  confirmPfmeaStage,
  confirmCpStage,
  regeneratePfmeaStage,
  regenerateCpStage,
  createProject,
  getDrawingAnalysis,
  getPartFamily,
  selectDrawingFile,
  selectOutputDir,
  updatePartFamily
} from "../api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
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

const analysisModeOptions: Array<{ value: DrawingAnalysisMode; label: string }> = [
  { value: "hybrid", label: "混合识别（推荐）" },
  { value: "ocr_only", label: "仅 OCR" },
  { value: "vision_only", label: "仅 AI 视觉" }
];

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

export default function DrawingImportPage({ activeRun, onRunCreated, onRunUpdated, onOpenWorkbench }: DrawingImportPageProps) {
  const [drawingPath, setDrawingPath] = useState("");
  const [outputDir, setOutputDir] = useState("");
  const [projectName, setProjectName] = useState("MINOS-APQP-Project");
  const [analysisMode, setAnalysisMode] = useState<DrawingAnalysisMode>("hybrid");
  const [status, setStatus] = useState("等待选择图纸");
  const [runState, setRunState] = useState<"idle" | "running" | "success" | "failed" | "blocked" | "chain_active">("idle");
  const [error, setError] = useState("");
  const [completedRun, setCompletedRun] = useState<DesktopRun | null>(null);
  const [chainState, setChainState] = useState<ChainState | null>(null);
  const [chainGenerating, setChainGenerating] = useState(false);
  const [analysisOverride, setAnalysisOverride] = useState<DrawingAnalysisResponse | null>(null);
  const [partFamilyOverride, setPartFamilyOverride] = useState<PartFamilyResponse | null>(null);
  const [partFamilyDraft, setPartFamilyDraft] = useState("");
  const [panelMessage, setPanelMessage] = useState("");
  const [syncMessage, setSyncMessage] = useState("");

  const visibleRun = completedRun ?? activeRun;
  const insights = useMemo(
    () => buildImportInsights(visibleRun, analysisOverride, partFamilyOverride),
    [analysisOverride, partFamilyOverride, visibleRun]
  );
  const partFamilyValue = partFamilyDraft || (insights.partFamily === "未设置" ? "" : insights.partFamily);
  const canStart = Boolean(drawingPath.trim() && projectName.trim() && runState !== "running");
  const startButtonLabel =
    runState === "running" ? "生成中..." : runState === "chain_active" ? "重新开始" : "开始生成";
  const startHint =
    runState === "running"
      ? "正在分析图纸并生成过程流程图..."
      : runState === "failed"
        ? "上次请求失败，修正后可重新开始。"
        : runState === "blocked"
          ? "请先补齐图纸和项目名。"
          : "填写图纸和项目名后即可开始。";

  async function chooseDrawing() {
    const path = await selectDrawingFile();
    if (path) setDrawingPath(path);
  }

  async function chooseOutput() {
    const path = await selectOutputDir();
    if (path) setOutputDir(path);
  }

  // ---- 链式流程 ----

  async function startChainFlow() {
    setError(""); setPanelMessage(""); setSyncMessage("");
    setAnalysisOverride(null); setPartFamilyOverride(null);
    setCompletedRun(null);
    if (!drawingPath.trim() || !projectName.trim()) {
      setRunState("blocked");
      setStatus(!drawingPath.trim() ? "请先选择图纸" : "请先填写项目名");
      return;
    }
    setRunState("running"); setStatus("正在建立项目记录并启动链式流程...");
    try {
      const project = await createProject({
        project_name: projectName, drawing_path: drawingPath,
        output_dir: outputDir,
        context: { source: "tauri-react-desktop", part_family: partFamilyDraft.trim() || undefined, analysis_mode: analysisMode, ocr_engine: "auto" },
      });
      setStatus("正在分析图纸并生成过程流程图（第一步）...");
      const run = await startChainRun(project.id);
      setCompletedRun(run); onRunCreated(run);
      setRunState("chain_active");
      const cs = extractChainState(run);
      setChainState(cs);
      const feedback = chainStartFeedback(run, cs);
      setStatus(feedback.status);
      if (feedback.error) setError(feedback.error);
    } catch (caught) {
      setRunState("failed");
      setStatus(isLocalServiceProblem(caught) ? "本地服务未连接" : "链式启动失败");
      setError(errorMessage(caught));
    }
  }

  function extractChainState(run: DesktopRun): ChainState | null {
    if (run.chain_stages) return run.chain_stages;
    const cs = (run as Record<string, unknown>).chain_stages;
    if (cs && typeof cs === "object") return cs as ChainState;
    return null;
  }

  function stageStatusFromChainState(cs: ChainState | null, stage: "pfmea" | "cp"): string {
    return cs?.[stage]?.status ?? "";
  }

  function stageFailureTitle(stage: "pfmea" | "cp"): string {
    return stage === "pfmea" ? "失效模式分析生成失败" : "控制计划生成失败";
  }

  function pollRunUntilStageSettled(runId: number, stage: "pfmea" | "cp") {
    const timer = window.setInterval(async () => {
      try {
        const latest = await getRun(runId);
        setCompletedRun(latest);
        onRunUpdated(latest);
        const cs = extractChainState(latest);
        if (cs) setChainState(cs);
        const stageStatus = stageStatusFromChainState(cs, stage);
        if (latest.status === "failed" || stageStatus === "failed") {
          window.clearInterval(timer);
          setRunState("failed");
          setStatus(stageFailureTitle(stage));
          setError(latest.failure_message || "后台生成失败，请查看本地服务日志后重试。");
          setChainGenerating(false);
          return;
        }
        if (stageStatus && stageStatus !== "running") {
          window.clearInterval(timer);
          setRunState("chain_active");
          setStatus(stageStatus === "generated" ? "下一阶段已生成，请继续确认。" : "阶段状态已更新。");
          setChainGenerating(false);
        }
      } catch (caught) {
        window.clearInterval(timer);
        setRunState("failed");
        setStatus("阶段状态刷新失败");
        setError(errorMessage(caught));
        setChainGenerating(false);
      }
    }, 2500);
  }

  async function refreshChainState() {
    if (!completedRun) return;
    try {
      const cs = await getChainState(completedRun.id);
      setChainState(cs);
    } catch { /* ignore */ }
  }

  async function handleChainConfirm(stage: "pfd" | "pfmea" | "cp") {
    if (!completedRun) return;
    setChainGenerating(true);
    try {
      let updated: DesktopRun;
      if (stage === "pfd") updated = await confirmPfdStage(completedRun.id, {});
      else if (stage === "pfmea") updated = await confirmPfmeaStage(completedRun.id, {});
      else updated = await confirmCpStage(completedRun.id, {});
      setCompletedRun(updated);
      onRunUpdated(updated);
      const cs = extractChainState(updated);
      if (cs) setChainState(cs);
      if (stage === "pfd") {
        pollRunUntilStageSettled(updated.id, "pfmea");
      } else if (stage === "pfmea") {
        pollRunUntilStageSettled(updated.id, "cp");
      } else {
        setChainGenerating(false);
      }
    } catch (caught) {
      setError(errorMessage(caught));
      setChainGenerating(false);
    }
  }

  async function handleChainRegenerate(stage: "pfd" | "pfmea" | "cp") {
    if (!completedRun || stage === "pfd") return;
    setChainGenerating(true);
    try {
      let updated: DesktopRun;
      if (stage === "pfmea") updated = await regeneratePfmeaStage(completedRun.id);
      else updated = await regenerateCpStage(completedRun.id);
      setCompletedRun(updated);
      onRunUpdated(updated);
      const cs = extractChainState(updated);
      if (cs) setChainState(cs);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setChainGenerating(false);
    }
  }

  async function refreshDrawingAnalysis() {
    if (!visibleRun) return;
    setPanelMessage("正在刷新图纸识别状态...");
    try {
      setAnalysisOverride(await getDrawingAnalysis(visibleRun.id));
      setPanelMessage("图纸识别状态已刷新。");
    } catch (caught) {
      setPanelMessage(errorMessage(caught));
    }
  }

  async function refreshPartFamily() {
    if (!visibleRun) return;
    setPanelMessage("正在读取零件族...");
    try {
      const response = await getPartFamily(visibleRun.id);
      setPartFamilyOverride(response);
      setPartFamilyDraft(response.part_family);
      setPanelMessage("零件族已刷新。");
    } catch (caught) {
      setPanelMessage(errorMessage(caught));
    }
  }

  async function savePartFamily() {
    if (!visibleRun || !partFamilyValue.trim()) return;
    setPanelMessage("正在保存零件族...");
    try {
      const response = await updatePartFamily(visibleRun.id, partFamilyValue.trim());
      setPartFamilyOverride(response);
      setPartFamilyDraft(response.part_family);
      setPanelMessage("零件族已保存。");
    } catch (caught) {
      setPanelMessage(errorMessage(caught));
    }
  }

  async function applySync() {
    if (!visibleRun) return;
    setSyncMessage("正在应用联动同步...");
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
      setSyncMessage(syncResultMessage(response));
    } catch (caught) {
      setSyncMessage(errorMessage(caught));
    }
  }

  const errorBoxClass = "m-0 p-3 border border-[#f0b4ae] rounded-lg bg-[#fff6f5] text-[#9f1c12] whitespace-pre-wrap";

  return (
    <section className="grid gap-4">
      <div>
        <span className="text-primary text-xs font-bold">Drawing Import</span>
        <h2 className="mt-1 mb-0 text-[22px]">从图纸建立三表草案</h2>
      </div>

      <Card className="max-w-[760px]">
        <CardContent className="p-[18px] grid gap-4">
          <label className="grid gap-[7px]">
            <span className="text-[#56565b] text-[13px]">图纸文件</span>
            <div className="flex gap-2 items-center">
              <Input value={drawingPath} onChange={(event) => setDrawingPath(event.target.value)} placeholder="选择 PDF、PNG、JPG 或 JPEG" className="flex-1" />
              <Button variant="outline" size="sm" onClick={chooseDrawing}>
                <Upload size={16} className="mr-[7px]" />
                选择图纸
              </Button>
            </div>
          </label>
          <label className="grid gap-[7px]">
            <span className="text-[#56565b] text-[13px]">输出目录</span>
            <div className="flex gap-2 items-center">
              <Input value={outputDir} onChange={(event) => setOutputDir(event.target.value)} placeholder="选择工作包输出目录" className="flex-1" />
              <Button variant="outline" size="sm" onClick={chooseOutput}>
                <FolderOpen size={16} className="mr-[7px]" />
                选择目录
              </Button>
            </div>
          </label>
          <label className="grid gap-[7px]">
            <span className="text-[#56565b] text-[13px]">项目名</span>
            <Input value={projectName} onChange={(event) => setProjectName(event.target.value)} />
          </label>
          <label className="grid gap-[7px]">
            <span className="text-[#56565b] text-[13px]">识别模式</span>
            <SegmentedControl options={analysisModeOptions} value={analysisMode} onChange={setAnalysisMode} />
          </label>
          <label className="grid gap-[7px]">
            <span className="text-[#56565b] text-[13px]">零件族</span>
            <Input value={partFamilyDraft} onChange={(event) => setPartFamilyDraft(event.target.value)} placeholder="例如 stamping、machining、casting" />
          </label>
          <Button
            disabled={!canStart}
            onClick={startChainFlow}
            className="justify-center w-[150px]"
          >
            <Play size={16} className="mr-[7px]" />
            {startButtonLabel}
          </Button>
          <div className="grid gap-1">
            <div className="text-[#56565b] text-[13px]">{status}</div>
            <small className="text-[#86868b] text-xs leading-[1.4]">{startHint}</small>
          </div>
          {error && <pre className={errorBoxClass}>{error}</pre>}
        </CardContent>
      </Card>

      {/* 链式流程步骤指示器 */}
      {runState === "chain_active" && chainState && completedRun && (
        <ChainStepper
          chainState={chainState}
          run={completedRun}
          isGenerating={chainGenerating}
          onConfirm={handleChainConfirm}
          onRegenerate={handleChainRegenerate}
          onViewTable={() => onOpenWorkbench()}
        />
      )}

      {/* 结果卡片 */}
      {visibleRun && runState !== "chain_active" && (
        <div className="grid grid-cols-3 gap-3">
          <Card className="col-span-3">
            <CardContent className="p-4 grid content-start gap-2.5">
              <div className="flex items-center gap-[7px] text-primary text-xs font-bold">
                {visibleRun.failure_message ? <AlertTriangle size={16} /> : <CheckCircle2 size={16} />}
                <span>生成状态</span>
              </div>
              <h3 className="m-0 text-base leading-[1.35]">{insights.generationTitle}</h3>
              <p className="m-0 text-[#56565b] text-[13px] leading-[1.45]">{insights.generationMessage}</p>
              {insights.failureDetail && <pre className={errorBoxClass}>{insights.failureDetail}</pre>}
              <dl className="grid gap-[7px] m-0">
                {[["运行", `#${visibleRun.id}`], ["输出", visibleRun.output_dir || "未指定"], ["阻断环节", insights.blockedStage || "无"]].map(([dt, dd]) => (
                  <div key={dt} className="flex justify-between gap-2.5 min-w-0">
                    <dt className="text-muted-foreground text-xs">{dt}</dt>
                    <dd className="m-0 min-w-0 text-foreground text-[13px] text-right break-words">{dd}</dd>
                  </div>
                ))}
              </dl>
              <Button variant="outline" size="sm" onClick={onOpenWorkbench} className="w-fit">打开三表工作台</Button>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4 grid content-start gap-2.5 min-h-[220px]">
              <div className="flex items-center gap-[7px] text-primary text-xs font-bold">
                <ClipboardCheck size={16} />
                <span>图纸识别</span>
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
              {[["OCR 状态", insights.recognition.ocrStatus], ["AI 视觉状态", insights.recognition.visionStatus], ["识别来源", insights.recognition.source], ["待确认字段数量", insights.recognition.pendingFieldCount]].map(([label, value]) => (
                <div key={label} className="flex justify-between gap-2.5 items-center min-h-7 border-0 border-t border-solid border-[#ececf0]">
                  <span className="text-muted-foreground text-xs">{label}</span>
                  <strong className="text-xl">{value}</strong>
                </div>
              ))}
              <Button variant="outline" size="sm" disabled={!visibleRun} onClick={() => void refreshDrawingAnalysis()} className="w-fit">
                <RefreshCw size={15} className="mr-[7px]" />刷新识别
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4 grid content-start gap-2.5 min-h-[220px]">
              <div className="flex items-center gap-[7px] text-primary text-xs font-bold">
                <Layers3 size={16} />
                <span>零件族</span>
              </div>
              <h3 className="m-0 text-base leading-[1.35]">{insights.partFamily}</h3>
              <label className="grid gap-[5px]">
                <span className="text-[#56565b] text-[13px]">当前值</span>
                <Input value={partFamilyValue} onChange={(event) => setPartFamilyDraft(event.target.value)} placeholder="输入零件族" />
              </label>
              <div className="flex gap-2 items-center">
                <Button variant="outline" size="sm" disabled={!visibleRun} onClick={() => void refreshPartFamily()}>
                  <RefreshCw size={15} className="mr-[7px]" />读取
                </Button>
                <Button variant="outline" size="sm" disabled={!visibleRun || !partFamilyValue.trim()} onClick={() => void savePartFamily()}>保存</Button>
              </div>
              {panelMessage && <small className={isProblemMessage(panelMessage) ? "text-destructive text-xs leading-[1.4]" : "text-[#56565b] text-xs leading-[1.4]"}>{panelMessage}</small>}
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4 grid content-start gap-2.5 min-h-[220px]">
              <div className="flex items-center gap-[7px] text-primary text-xs font-bold">
                <GitBranch size={16} />
                <span>过程流程图确认</span>
              </div>
              <h3 className="m-0 text-base leading-[1.35]">过程流程图</h3>
              {[["工序", insights.pfdStepCount], ["待确认", insights.pfdReviewCount], ["联动差异", insights.linkageIssueCount]].map(([label, value]) => (
                <div key={label} className="flex justify-between gap-2.5 items-center min-h-7 border-0 border-t border-solid border-[#ececf0]">
                  <span className="text-muted-foreground text-xs">{label}</span>
                  <strong className="text-xl">{value}</strong>
                </div>
              ))}
              <Button
                variant="outline" size="sm"
                disabled={!visibleRun || (insights.syncSuggestionCount === 0 && insights.linkageIssueCount === 0)}
                onClick={() => void applySync()}
                className="w-fit"
              >
                应用联动同步
              </Button>
              {syncMessage && <small className={isProblemMessage(syncMessage) ? "text-destructive text-xs leading-[1.4]" : "text-[#56565b] text-xs leading-[1.4]"}>{syncMessage}</small>}
            </CardContent>
          </Card>
        </div>
      )}
    </section>
  );
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
