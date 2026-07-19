import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { queryKeys } from "../api/queryKeys";
import type {
  AppConfig,
  BacktestRequest,
  StrategyMetadata,
} from "../api/types";
import { useSymbolNames } from "../hooks/useSymbolNames";
import { useI18n } from "../i18n/I18nContext";
import { resolveVisibleJobId, type BacktestRail } from "../lib/backtestWorkspace";
import { formatSymbolLabel } from "../lib/symbols";
import { BacktestForm } from "./BacktestForm";
import { ResultView } from "./ResultView";
import { RunHistory } from "./RunHistory";

interface BacktestWorkspaceProps {
  config?: AppConfig;
  strategies: StrategyMetadata[];
  selectedStrategy: string;
  onSelectedStrategyChange: (path: string) => void;
  rail: BacktestRail;
  onRailChange: (rail: BacktestRail) => void;
  activeJobId: string | null;
  onActiveJobChange: (jobId: string | null) => void;
  opendConnected: boolean;
  onNotice: (message: string) => void;
}

export function BacktestWorkspace({
  config,
  strategies,
  selectedStrategy,
  onSelectedStrategyChange,
  rail,
  onRailChange,
  activeJobId,
  onActiveJobChange,
  opendConnected,
  onNotice,
}: BacktestWorkspaceProps) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const jobsQuery = useQuery({ queryKey: queryKeys.jobs, queryFn: api.jobs });
  const resolvedJobId = resolveVisibleJobId(
    rail,
    activeJobId,
    jobsQuery.data?.jobs ?? [],
  );
  const jobQuery = useQuery({
    queryKey: queryKeys.job(resolvedJobId),
    queryFn: () => api.job(resolvedJobId!),
    enabled: Boolean(resolvedJobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 900 : false;
    },
  });
  const resultQuery = useQuery({
    queryKey: queryKeys.result(resolvedJobId),
    queryFn: () => api.result(resolvedJobId!),
    enabled: Boolean(resolvedJobId && jobQuery.data?.status === "succeeded"),
  });
  const runMutation = useMutation({
    mutationFn: (request: BacktestRequest) => api.runBacktest(request),
    onSuccess: (createdJob) => {
      onActiveJobChange(createdJob.id);
      queryClient.setQueryData(queryKeys.job(createdJob.id), createdJob);
      void queryClient.invalidateQueries({ queryKey: queryKeys.jobs });
      onRailChange("archive");
      onNotice(t("app.backtestQueued", { id: createdJob.id }));
    },
    onError: (error) => onNotice(error.message),
  });

  useEffect(() => {
    if (jobQuery.data?.status === "succeeded" || jobQuery.data?.status === "failed") {
      void queryClient.invalidateQueries({ queryKey: queryKeys.jobs });
    }
  }, [jobQuery.data?.status, queryClient]);

  const job = rail === "archive"
    ? jobQuery.data ?? jobsQuery.data?.jobs.find((item) => item.id === resolvedJobId)
    : undefined;
  const result = rail === "archive" ? resultQuery.data : undefined;
  const symbolNames = useSymbolNames(
    [
      ...(jobsQuery.data?.jobs ?? []).map((item) => item.request.symbol),
      ...(job ? [job.request.symbol] : []),
    ],
    opendConnected,
  );
  const selectedStrategyMetadata = strategies.find(
    (strategy) => strategy.path === selectedStrategy,
  );

  return (
    <main className="backtest-workspace">
      <aside className="control-rail" aria-label={t("app.backtestConfig")}>
        <div className="rail-heading">
          <div>
            <span className="section-code">{rail === "create" ? "INPUT" : "ARCHIVE"}</span>
            <h2>{rail === "create" ? t("app.experimentConditions") : t("history.title")}</h2>
          </div>
          <button
            className="source-seal"
            type="button"
            onClick={() => onRailChange(rail === "create" ? "archive" : "create")}
          >
            {rail === "create" ? t("history.viewArchive") : t("history.newBacktest")}
          </button>
        </div>
        {rail === "create" ? (
          <BacktestForm
            config={config}
            selectedStrategy={selectedStrategy}
            onStrategyChange={onSelectedStrategyChange}
            onSubmit={(request) => runMutation.mutate(request)}
            running={runMutation.isPending || job?.status === "queued" || job?.status === "running"}
            opendConnected={opendConnected}
            parameterDefinitions={selectedStrategyMetadata?.parameters ?? []}
            compatibility={selectedStrategyMetadata?.compatibility}
          />
        ) : (
          <RunHistory
            jobs={jobsQuery.data?.jobs ?? []}
            symbolNames={symbolNames}
            activeJobId={resolvedJobId}
            onSelect={onActiveJobChange}
            onRefresh={() => void jobsQuery.refetch()}
            onCreate={() => onRailChange("create")}
          />
        )}
      </aside>
      <section className="result-desk" aria-live="polite">
        <div className="desk-intro">
          <div>
            <span className="section-code">OUTPUT</span>
            <p>
              {job
                ? `${formatSymbolLabel(job.request.symbol, symbolNames)} · ${t(`status.${job.status}`)}`
                : t(rail === "create" ? "app.waitingNewBacktest" : "app.waitingConditions")}
            </p>
          </div>
          <p className="desk-note">{t("app.executionNote")}</p>
        </div>
        <ResultView
          job={job}
          result={result}
          symbolName={job ? symbolNames[job.request.symbol] : undefined}
          loading={rail === "archive" && resultQuery.isLoading}
          emptyContext={rail === "create" ? "create" : "archive"}
        />
      </section>
    </main>
  );
}
