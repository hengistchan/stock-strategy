import type {
  AppConfig,
  BacktestJob,
  BacktestRequest,
  BacktestResult,
  CacheResponse,
  DiagnosticsResponse,
  Experiment,
  ExperimentRequest,
  ExperimentsResponse,
  HealthResponse,
  JobsResponse,
  PriceWindow,
  PortfolioRequest,
  PortfolioResult,
  StrategiesResponse,
  StrategyDocument,
  StrategyVersionsResponse,
  SymbolResolveResponse,
  SymbolSearchResponse,
} from "./types";
import { translations } from "../i18n/translations";
import {
  cancelJobApiJobsJobIdDelete,
  configApiConfigGet,
  createExperimentApiExperimentsPost,
  createJobApiJobsPost,
  createStrategyApiStrategiesPost,
  deleteCacheApiCacheCacheIdDelete,
  diagnosticsReportApiDiagnosticsGet,
  getExperimentApiExperimentsExperimentIdGet,
  healthApiHealthGet,
  jobApiJobsJobIdGet,
  jobsApiJobsGet,
  listCacheApiCacheGet,
  listExperimentsApiExperimentsGet,
  listStrategyDocumentsApiStrategiesGet,
  listStrategyVersionsApiStrategiesVersionsGet,
  pricesApiJobsJobIdPricesGet,
  readStrategyApiStrategiesStrategyPathGet,
  resolveSymbolsApiSymbolsResolveGet,
  resultApiJobsJobIdResultGet,
  runPortfolioApiPortfoliosPost,
  importStrategyApiMigrationsImportPost,
  retryJobApiJobsJobIdRetryPost,
  restoreStrategyVersionApiStrategiesVersionsRestorePost,
  saveStrategyApiStrategiesStrategyPathPut,
  scanStrategyApiMigrationsScanPost,
  searchSymbolsApiSymbolsGet,
  validateStrategyFixtureApiMigrationsFixturePost,
} from "./generated";
import { client as generatedClient } from "./generated/client.gen";
import type {
  BacktestRequest as GeneratedBacktestRequest,
  ExperimentRequest as GeneratedExperimentRequest,
  PortfolioRequest as GeneratedPortfolioRequest,
} from "./generated/types.gen";

const ACCESS_TOKEN_KEY = "strategy-lab-api-token";
generatedClient.setConfig({ baseUrl: window.location.origin });

export function initializeApiTokenFromFragment(): void {
  const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const token = fragment.get("access_token");
  if (!token) return;
  if (token.length >= 32) {
    window.sessionStorage.setItem(ACCESS_TOKEN_KEY, token);
    const secure = window.location.protocol === "https:" ? "; Secure" : "";
    document.cookie = `strategy_lab_token=${encodeURIComponent(token)}; Path=/; SameSite=Strict${secure}`;
  }
  window.history.replaceState(
    window.history.state,
    "",
    `${window.location.pathname}${window.location.search}`,
  );
}

function accessToken(): string | null {
  return window.sessionStorage.getItem(ACCESS_TOKEN_KEY);
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(message: string, status: number, code = "http_error", details: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function requestHeaders(): Record<string, string> {
  const token = accessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

type GeneratedResult = {
  data?: unknown;
  error?: unknown;
  response?: Response;
};

async function unwrap<T>(
  operation: PromiseLike<GeneratedResult>,
): Promise<T> {
  const result = await operation;
  if (result.data !== undefined) {
    return result.data as T;
  }
  const status = result.response?.status ?? 0;
  const locale = document.documentElement.lang === "en-US" ? "en-US" : "zh-CN";
  let message = translations[locale]["common.requestFailed"].replace(
    "{{status}}",
    String(status),
  );
  let code = "http_error";
  let details: unknown = null;
  const payload = result.error;
  if (payload && typeof payload === "object" && "error" in payload) {
    const error = (payload as {
      error?: { code?: unknown; message?: unknown; details?: unknown };
    }).error;
    if (error && typeof error === "object") {
      if (typeof error.message === "string") message = error.message;
      if (typeof error.code === "string") code = error.code;
      details = error.details ?? null;
    }
  } else if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail;
    message = Array.isArray(detail)
      ? detail
          .map((item) => String((item as { msg?: string }).msg ?? item))
          .join("；")
      : String(detail);
  }
  throw new ApiError(message, status, code, details);
}

async function unwrapResponse<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => undefined);
  return unwrap<T>(
    Promise.resolve(
      response.ok
        ? { data: payload, response }
        : { error: payload, response },
    ),
  );
}

export const api = {
  health: () =>
    unwrap<HealthResponse>(healthApiHealthGet({ headers: requestHeaders() })),
  diagnostics: () =>
    unwrap<DiagnosticsResponse>(
      diagnosticsReportApiDiagnosticsGet({ headers: requestHeaders() }),
    ),
  config: () =>
    unwrap<AppConfig>(configApiConfigGet({ headers: requestHeaders() })),
  symbols: (query: string, limit = 8) =>
    unwrap<SymbolSearchResponse>(
      searchSymbolsApiSymbolsGet({
        headers: requestHeaders(),
        query: { q: query, limit },
      }),
    ),
  resolveSymbols: (codes: string[]) =>
    unwrap<SymbolResolveResponse>(
      resolveSymbolsApiSymbolsResolveGet({
        headers: requestHeaders(),
        query: { codes },
      }),
    ),
  jobs: () =>
    unwrap<JobsResponse>(jobsApiJobsGet({ headers: requestHeaders() })),
  job: (jobId: string) =>
    unwrap<BacktestJob>(
      jobApiJobsJobIdGet({
        headers: requestHeaders(),
        path: { job_id: jobId },
      }),
    ),
  cancelJob: (jobId: string) =>
    unwrap<BacktestJob>(
      cancelJobApiJobsJobIdDelete({
        headers: requestHeaders(),
        path: { job_id: jobId },
      }),
    ),
  retryJob: (jobId: string) =>
    unwrap<BacktestJob>(
      retryJobApiJobsJobIdRetryPost({
        headers: requestHeaders(),
        path: { job_id: jobId },
      }),
    ),
  result: (jobId: string) =>
    unwrap<BacktestResult>(
      resultApiJobsJobIdResultGet({
        headers: requestHeaders(),
        path: { job_id: jobId },
      }),
    ),
  prices: (jobId: string, offset: number, limit: number) =>
    unwrap<PriceWindow>(
      pricesApiJobsJobIdPricesGet({
        headers: requestHeaders(),
        path: { job_id: jobId },
        query: { offset, limit },
      }),
    ),
  runBacktest: (payload: BacktestRequest) =>
    unwrap<BacktestJob>(
      createJobApiJobsPost({
        headers: requestHeaders(),
        body: payload as GeneratedBacktestRequest,
      }),
    ),
  importEvidence: async (bundle: File) =>
    unwrapResponse<BacktestJob>(
      await fetch("/api/evidence/import", {
        method: "POST",
        headers: {
          ...requestHeaders(),
          "Content-Type": "application/zip",
        },
        body: bundle,
      }),
    ),
  scanMigration: (content: string) =>
    unwrap<import("./types").StrategyMigrationReport>(
      scanStrategyApiMigrationsScanPost({
        headers: requestHeaders(),
        body: { content },
      }),
    ),
  validateMigrationFixture: (content: string) =>
    unwrap<import("./types").StrategyMigrationReport>(
      validateStrategyFixtureApiMigrationsFixturePost({
        headers: requestHeaders(),
        body: { content },
      }),
    ),
  importMigration: (name: string, content: string) =>
    unwrap<{
      strategy: StrategyDocument;
      report: import("./types").StrategyMigrationReport;
    }>(
      importStrategyApiMigrationsImportPost({
        headers: requestHeaders(),
        body: { name, content },
      }),
    ),
  strategies: () =>
    unwrap<StrategiesResponse>(
      listStrategyDocumentsApiStrategiesGet({ headers: requestHeaders() }),
    ),
  strategy: (path: string) =>
    unwrap<StrategyDocument>(
      readStrategyApiStrategiesStrategyPathGet({
        headers: requestHeaders(),
        path: { strategy_path: path },
      }),
    ),
  createStrategy: (payload: {
    name: string;
    content?: string;
    template_path?: string;
  }) =>
    unwrap<StrategyDocument>(
      createStrategyApiStrategiesPost({
        headers: requestHeaders(),
        body: payload,
      }),
    ),
  saveStrategy: (path: string, content: string, expectedRevision: string) =>
    unwrap<StrategyDocument>(
      saveStrategyApiStrategiesStrategyPathPut({
        headers: requestHeaders(),
        path: { strategy_path: path },
        body: {
          content,
          expected_revision: expectedRevision,
        },
      }),
    ),
  strategyVersions: (path: string) =>
    unwrap<StrategyVersionsResponse>(
      listStrategyVersionsApiStrategiesVersionsGet({
        headers: requestHeaders(),
        query: { strategy_path: path },
      }),
    ),
  restoreStrategyVersion: (
    path: string,
    revision: string,
    expectedRevision: string,
  ) =>
    unwrap<StrategyDocument>(
      restoreStrategyVersionApiStrategiesVersionsRestorePost({
        headers: requestHeaders(),
        body: {
          strategy_path: path,
          revision,
          expected_revision: expectedRevision,
        },
      }),
    ),
  experiments: () =>
    unwrap<ExperimentsResponse>(
      listExperimentsApiExperimentsGet({ headers: requestHeaders() }),
    ),
  experiment: (experimentId: string) =>
    unwrap<Experiment>(
      getExperimentApiExperimentsExperimentIdGet({
        headers: requestHeaders(),
        path: { experiment_id: experimentId },
      }),
    ),
  runExperiment: (payload: ExperimentRequest) =>
    unwrap<Experiment>(
      createExperimentApiExperimentsPost({
        headers: requestHeaders(),
        body: payload as GeneratedExperimentRequest,
      }),
    ),
  runPortfolio: (payload: PortfolioRequest) =>
    unwrap<PortfolioResult>(
      runPortfolioApiPortfoliosPost({
        headers: requestHeaders(),
        body: payload as GeneratedPortfolioRequest,
      }),
    ),
  cache: () =>
    unwrap<CacheResponse>(listCacheApiCacheGet({ headers: requestHeaders() })),
  deleteCache: (cacheId: string) =>
    unwrap<{ deleted: string }>(
      deleteCacheApiCacheCacheIdDelete({
        headers: requestHeaders(),
        path: { cache_id: cacheId },
      }),
    ),
};
