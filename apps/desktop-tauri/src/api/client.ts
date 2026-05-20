import { invoke } from "@tauri-apps/api/core";
import type {
  BootstrapPayload,
  ChainConfirmRequest,
  ChainState,
  ClosureTasksResponse,
  CreateProjectRequest,
  DesktopProject,
  DesktopRun,
  DesktopSettings,
  DrawingAnalysisResponse,
  ExportResponse,
  HealthResponse,
  KnowledgeFamiliesResponse,
  KnowledgeImportSeedsRequest,
  KnowledgeImportSeedsResponse,
  LinkageApplySyncRequest,
  LinkageApplySyncResponse,
  PartFamilyResponse
} from "./types";

const API_BASE_URL = import.meta.env.VITE_MINOS_API_BASE_URL ?? "http://127.0.0.1:8000";
let runtimeApiBaseUrl = API_BASE_URL;
let runtimeApiToken = import.meta.env.VITE_MINOS_API_TOKEN ?? "";

export class LocalServiceConnectionError extends Error {
  readonly cause?: unknown;

  constructor(baseUrl: string, cause: unknown) {
    super(`本地服务未连接：无法连接 ${baseUrl}。请确认 MINOS 本地服务或 sidecar 已启动。`);
    this.name = "LocalServiceConnectionError";
    this.cause = cause;
  }
}

export function configureApi(bootstrap: BootstrapPayload | null): void {
  runtimeApiBaseUrl = bootstrap?.apiBaseUrl || API_BASE_URL;
  runtimeApiToken = bootstrap?.apiToken || runtimeApiToken;
}

export async function getHealth(): Promise<HealthResponse> {
  let response: Response;
  try {
    response = await fetch(`${runtimeApiBaseUrl}/api/health`, {
      headers: apiHeaders(false)
    });
  } catch (caught) {
    throw new LocalServiceConnectionError(runtimeApiBaseUrl, caught);
  }

  if (!response.ok) {
    throw new Error(`/api/health returned ${response.status}`);
  }

  return response.json() as Promise<HealthResponse>;
}

function apiHeaders(withJson = true): Record<string, string> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (withJson) headers["Content-Type"] = "application/json";
  if (runtimeApiToken) headers.Authorization = `Bearer ${runtimeApiToken}`;
  return headers;
}

async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${runtimeApiBaseUrl}${path}`, {
      ...init,
      headers: {
        ...apiHeaders(true),
        ...(init?.headers ?? {})
      }
    });
  } catch (caught) {
    throw new LocalServiceConnectionError(runtimeApiBaseUrl, caught);
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message = body?.failure_message ?? body?.detail ?? body?.message ?? `${path} returned ${response.status}`;
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export function createProject(payload: CreateProjectRequest): Promise<DesktopProject> {
  return apiJson<DesktopProject>("/api/projects", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getRecentRuns(limit = 1): Promise<DesktopRun[]> {
  return apiJson<DesktopRun[]>(`/api/runs/recent?limit=${limit}`);
}

export function getRun(runId: number): Promise<DesktopRun> {
  return apiJson<DesktopRun>(`/api/runs/${runId}`);
}

export function getDrawingAnalysis(runId: number): Promise<DrawingAnalysisResponse> {
  return apiJson<DrawingAnalysisResponse>(`/api/runs/${runId}/drawing-analysis`);
}

export function getPartFamily(runId: number): Promise<PartFamilyResponse> {
  return apiJson<PartFamilyResponse>(`/api/runs/${runId}/part-family`);
}

export function updatePartFamily(runId: number, partFamily: string): Promise<PartFamilyResponse> {
  return apiJson<PartFamilyResponse>(`/api/runs/${runId}/part-family`, {
    method: "PATCH",
    body: JSON.stringify({ part_family: partFamily })
  });
}

export function getKnowledgeFamilies(): Promise<KnowledgeFamiliesResponse> {
  return apiJson<KnowledgeFamiliesResponse>("/api/knowledge/families");
}

export function importKnowledgeSeeds(
  payload: KnowledgeImportSeedsRequest = { write_files: true }
): Promise<KnowledgeImportSeedsResponse> {
  return apiJson<KnowledgeImportSeedsResponse>("/api/knowledge/import-seeds", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getClosureTasks(runId: number): Promise<ClosureTasksResponse> {
  return apiJson<ClosureTasksResponse>(`/api/runs/${runId}/closure-tasks`);
}

export function applyEditPatch(runId: number, patch: Record<string, unknown>): Promise<DesktopRun> {
  return apiJson<DesktopRun>(`/api/runs/${runId}/edit-patch`, {
    method: "PATCH",
    body: JSON.stringify({ patch })
  });
}

export function acceptRecommendation(runId: number, recommendationId: string): Promise<DesktopRun> {
  return apiJson<DesktopRun>(`/api/runs/${runId}/recommendations/${encodeURIComponent(recommendationId)}/accept`, {
    method: "POST"
  });
}

export function ignoreRecommendation(runId: number, recommendationId: string, reason: string): Promise<DesktopRun> {
  return apiJson<DesktopRun>(`/api/runs/${runId}/recommendations/${encodeURIComponent(recommendationId)}/ignore`, {
    method: "POST",
    body: JSON.stringify({ reason })
  });
}

export function resolveChangeImpact(runId: number, itemId: string, status = "已处理"): Promise<DesktopRun> {
  return apiJson<DesktopRun>(`/api/runs/${runId}/change-impacts/${encodeURIComponent(itemId)}/resolve`, {
    method: "POST",
    body: JSON.stringify({ status })
  });
}

export function resolveAction(runId: number, actionId: string): Promise<DesktopRun> {
  return apiJson<DesktopRun>(`/api/runs/${runId}/actions/${encodeURIComponent(actionId)}/resolve`, {
    method: "POST",
    body: JSON.stringify({ changes: { status: "已关闭" }, reason: "桌面端闭环处理" })
  });
}

export function batchConfirmAutomation(runId: number): Promise<DesktopRun> {
  return apiJson<DesktopRun>(`/api/runs/${runId}/automation-review/batch-confirm`, {
    method: "POST"
  });
}

export function applyLinkageSync(
  runId: number,
  payload: LinkageApplySyncRequest = { apply_all: true }
): Promise<LinkageApplySyncResponse> {
  return apiJson<LinkageApplySyncResponse>(`/api/runs/${runId}/linkage/apply-sync`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function exportRun(runId: number, exportMode: "draft" | "final", outputDir = ""): Promise<ExportResponse> {
  return apiJson<ExportResponse>(`/api/runs/${runId}/exports`, {
    method: "POST",
    body: JSON.stringify({ export_mode: exportMode, output_dir: outputDir })
  });
}

export function getSettings(): Promise<DesktopSettings> {
  return apiJson<DesktopSettings>("/api/settings");
}

export function setDefaultOutputDir(outputDir: string): Promise<DesktopSettings> {
  return apiJson<DesktopSettings>("/api/settings/default-output-dir", {
    method: "PATCH",
    body: JSON.stringify({ output_dir: outputDir })
  });
}

export function getBootstrap(): Promise<BootstrapPayload> {
  return invoke<BootstrapPayload>("get_bootstrap");
}

export function selectDrawingFile(): Promise<string | null> {
  return invoke<string | null>("select_drawing_file");
}

export function selectOutputDir(): Promise<string | null> {
  return invoke<string | null>("select_output_dir");
}

export function openOutputDir(path: string): Promise<void> {
  return invoke("open_output_dir", { path });
}

export function revealFile(path: string): Promise<void> {
  return invoke("reveal_file", { path });
}

export function shutdownSidecar(): Promise<void> {
  return invoke("shutdown_sidecar");
}

/** Expose the runtime API base URL for SSE connections. */
export function getApiBaseUrl(): string {
  return runtimeApiBaseUrl;
}

// ---- 链式确认流程 API ----

export function startChainRun(projectId: number): Promise<DesktopRun> {
  return apiJson<DesktopRun>(`/api/projects/${projectId}/chain-runs`, {
    method: "POST",
  });
}

export function getChainState(runId: number): Promise<ChainState> {
  return apiJson<ChainState>(`/api/runs/${runId}/chain/state`);
}

export function confirmPfdStage(
  runId: number,
  payload: ChainConfirmRequest
): Promise<DesktopRun> {
  return apiJson<DesktopRun>(`/api/runs/${runId}/chain/pfd-confirm`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function regeneratePfmeaStage(runId: number): Promise<DesktopRun> {
  return apiJson<DesktopRun>(`/api/runs/${runId}/chain/pfmea-regenerate`, {
    method: "POST",
  });
}

export function confirmPfmeaStage(
  runId: number,
  payload: ChainConfirmRequest
): Promise<DesktopRun> {
  return apiJson<DesktopRun>(`/api/runs/${runId}/chain/pfmea-confirm`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function regenerateCpStage(runId: number): Promise<DesktopRun> {
  return apiJson<DesktopRun>(`/api/runs/${runId}/chain/cp-regenerate`, {
    method: "POST",
  });
}

export function confirmCpStage(
  runId: number,
  payload: ChainConfirmRequest
): Promise<DesktopRun> {
  return apiJson<DesktopRun>(`/api/runs/${runId}/chain/cp-confirm`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
