/**
 * SSE client for chain generation progress streaming.
 * Connects to GET /api/runs/{runId}/chain/{stage}/stream
 */

import { getApiBaseUrl, getBootstrap } from "./client";

const BUILD_TIME_API_TOKEN = import.meta.env.VITE_MINOS_API_TOKEN ?? "";

export type StepCompleteEvent = {
  type: "step_complete";
  stage: "pfmea" | "cp";
  run_id: number;
  step_index: number;
  total_steps: number;
  step_id: string;
  rows_so_far: number;
  new_rows: Record<string, unknown>[];
};

export type DoneEvent = {
  type: "done";
  stage: "pfmea" | "cp";
  run_id: number;
  total_rows: number;
  status: string;
  failure_message?: string;
};

export type ErrorEvent = {
  type: "error";
  stage: "pfmea" | "cp";
  run_id: number;
  message: string;
};

export type StepFailedEvent = {
  type: "step_failed";
  stage: "pfmea" | "cp";
  run_id: number;
  step_index: number;
  total_steps: number;
  step_id: string;
  rows_so_far: number;
  message: string;
};

export type HeartbeatEvent = {
  type: "heartbeat";
  stage: "pfmea" | "cp";
  run_id: number;
  status?: string;
};

export type ConnectionState = "connected" | "reconnecting" | "closed";

export type StreamEvent = StepCompleteEvent | StepFailedEvent | HeartbeatEvent | DoneEvent | ErrorEvent;

export type StreamHandlers = {
  onProgress: (event: StepCompleteEvent) => void;
  onDone: (event: DoneEvent) => void;
  onError: (message: string) => void;
  onStepFailed?: (event: StepFailedEvent) => void;
  onHeartbeat?: (event: HeartbeatEvent) => void;
  onConnectionStateChange?: (state: ConnectionState, retryCount?: number) => void;
};

/**
 * Subscribe to a chain generation stream via SSE.
 * Returns a cleanup function that closes the connection.
 */
export function subscribeToChainStream(
  runId: number,
  stage: "pfmea" | "cp",
  handlers: StreamHandlers,
): () => void {
  const MAX_RETRIES = 5;
  let closed = false;
  let retryCount = 0;
  let retryTimer: number | undefined;
  let currentEs: EventSource | null = null;
  let runtimeBaseUrl = getApiBaseUrl();
  let runtimeToken = "";

  function resetRetryCount() {
    retryCount = 0;
  }

  function streamUrl() {
    const tokenQuery = runtimeToken ? `?token=${encodeURIComponent(runtimeToken)}` : "";
    return `${runtimeBaseUrl}/api/runs/${runId}/chain/${stage}/stream${tokenQuery}`;
  }

  function connect() {
    if (closed) return;
    const es = new EventSource(streamUrl());
    currentEs = es;

    es.onopen = () => {
      resetRetryCount();
      handlers.onConnectionStateChange?.("connected");
    };

    es.addEventListener("step_complete", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as StepCompleteEvent;
        resetRetryCount();
        handlers.onProgress(data);
      } catch { /* ignore parse errors */ }
    });

    es.addEventListener("step_failed", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as StepFailedEvent;
        resetRetryCount();
        handlers.onStepFailed?.(data);
      } catch { /* ignore parse errors */ }
    });

    es.addEventListener("heartbeat", (e: MessageEvent) => {
      resetRetryCount();
      try {
        const data = e.data ? JSON.parse(e.data) as HeartbeatEvent : {
          type: "heartbeat",
          stage,
          run_id: runId,
          status: "alive",
        } satisfies HeartbeatEvent;
        handlers.onHeartbeat?.(data);
      } catch { /* ignore heartbeat parse errors */ }
    });

    es.addEventListener("done", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as DoneEvent;
        handlers.onDone(data);
      } catch { /* ignore */ }
      closed = true;
      handlers.onConnectionStateChange?.("closed");
      es.close();
    });

    es.addEventListener("error", (e: MessageEvent) => {
      if (!e.data) return;
      closed = true;
      try {
        const data = JSON.parse(e.data) as ErrorEvent;
        handlers.onError(data.message);
      } catch {
        handlers.onError("SSE connection error");
      }
      handlers.onConnectionStateChange?.("closed");
      es.close();
    });

    es.onerror = () => {
      es.close();
      if (closed) return;
      if (retryCount < MAX_RETRIES) {
        retryCount += 1;
        handlers.onConnectionStateChange?.("reconnecting", retryCount);
        retryTimer = window.setTimeout(connect, Math.min(1000 * 2 ** (retryCount - 1), 10000));
        return;
      }
      closed = true;
      handlers.onConnectionStateChange?.("closed", retryCount);
      handlers.onError("连接中断，自动重连失败。");
    };
  }

  async function configureStreamAuth() {
    const bootstrap = await getBootstrap();
    runtimeBaseUrl = bootstrap.apiBaseUrl || runtimeBaseUrl;
    const apiToken = bootstrap.apiToken || BUILD_TIME_API_TOKEN;
    if (!apiToken) return;
    const response = await fetch(`${runtimeBaseUrl}/api/sse-token`, {
      headers: { Authorization: `Bearer ${apiToken}` },
    });
    if (!response.ok) {
      return;
    }
    const body = await response.json() as { token?: string };
    runtimeToken = body.token || "";
  }

  void configureStreamAuth()
    .catch(() => {
      /* keep build-time token or unauthenticated local mode */
    })
    .finally(connect);

  return () => {
    closed = true;
    if (retryTimer !== undefined) window.clearTimeout(retryTimer);
    currentEs?.close();
  };
}
