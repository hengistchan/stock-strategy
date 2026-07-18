import type {
  AppConfig,
  BacktestJob,
  BacktestRequest,
  BacktestResult,
  CacheResponse,
  Experiment,
  ExperimentRequest,
  ExperimentsResponse,
  HealthResponse,
  JobsResponse,
  PriceWindow,
  StrategiesResponse,
  StrategyDocument,
} from "./types";
import { translations } from "../i18n/translations";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  const contentType = response.headers.get("content-type") ?? "";
  const payload: unknown = contentType.includes("application/json")
    ? await response.json()
    : null;
  if (!response.ok) {
    const locale = document.documentElement.lang === "en-US" ? "en-US" : "zh-CN";
    let message = translations[locale]["common.requestFailed"].replace("{{status}}", String(response.status));
    if (payload && typeof payload === "object" && "detail" in payload) {
      const detail = (payload as { detail: unknown }).detail;
      message = Array.isArray(detail)
        ? detail.map((item) => String((item as { msg?: string }).msg ?? item)).join("；")
        : String(detail);
    }
    throw new ApiError(message, response.status);
  }
  return payload as T;
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  config: () => request<AppConfig>("/api/config"),
  jobs: () => request<JobsResponse>("/api/jobs"),
  job: (jobId: string) => request<BacktestJob>(`/api/jobs/${jobId}`),
  result: (jobId: string) => request<BacktestResult>(`/api/jobs/${jobId}/result`),
  prices: (jobId: string, offset: number, limit: number) =>
    request<PriceWindow>(`/api/jobs/${jobId}/prices?offset=${offset}&limit=${limit}`),
  runBacktest: (payload: BacktestRequest) =>
    request<BacktestJob>("/api/jobs", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  strategies: () => request<StrategiesResponse>("/api/strategies"),
  strategy: (path: string) =>
    request<StrategyDocument>(`/api/strategies/${encodeURI(path)}`),
  createStrategy: (payload: {
    name: string;
    content?: string;
    template_path?: string;
  }) =>
    request<StrategyDocument>("/api/strategies", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  saveStrategy: (path: string, content: string, expectedRevision: string) =>
    request<StrategyDocument>(`/api/strategies/${encodeURI(path)}`, {
      method: "PUT",
      body: JSON.stringify({
        content,
        expected_revision: expectedRevision,
      }),
    }),
  experiments: () => request<ExperimentsResponse>("/api/experiments"),
  experiment: (experimentId: string) =>
    request<Experiment>(`/api/experiments/${experimentId}`),
  runExperiment: (payload: ExperimentRequest) =>
    request<Experiment>("/api/experiments", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  cache: () => request<CacheResponse>("/api/cache"),
  deleteCache: (cacheId: string) =>
    request<{ deleted: string }>(`/api/cache/${cacheId}`, { method: "DELETE" }),
};
