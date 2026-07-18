import { lazy, Suspense, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api/client";
import type { BacktestRequest } from "./api/types";
import { useI18n } from "./i18n/I18nContext";
import { BacktestForm } from "./components/BacktestForm";
import { Header, type WorkspaceMode } from "./components/Header";
import { ResultView } from "./components/ResultView";
import { RunHistory } from "./components/RunHistory";

const StrategyWorkspace = lazy(() =>
  import("./components/StrategyWorkspace").then((module) => ({
    default: module.StrategyWorkspace,
  })),
);

const IterationWorkspace = lazy(() =>
  import("./components/IterationWorkspace").then((module) => ({
    default: module.IterationWorkspace,
  })),
);

export function App() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<WorkspaceMode>("backtest");
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [selectedStrategy, setSelectedStrategy] = useState("");
  const [toast, setToast] = useState<string | null>(null);

  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 5_000,
  });
  const configQuery = useQuery({ queryKey: ["config"], queryFn: api.config });
  const strategiesQuery = useQuery({ queryKey: ["strategies"], queryFn: api.strategies });
  const jobsQuery = useQuery({ queryKey: ["jobs"], queryFn: api.jobs });
  const resolvedStrategy = selectedStrategy || configQuery.data?.strategies[0]?.path || "";
  const resolvedJobId = activeJobId
    ?? jobsQuery.data?.jobs.find((job) => job.status === "succeeded")?.id
    ?? jobsQuery.data?.jobs[0]?.id
    ?? null;
  const jobQuery = useQuery({
    queryKey: ["job", resolvedJobId],
    queryFn: () => api.job(resolvedJobId!),
    enabled: Boolean(resolvedJobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 900 : false;
    },
  });
  const resultQuery = useQuery({
    queryKey: ["result", resolvedJobId],
    queryFn: () => api.result(resolvedJobId!),
    enabled: Boolean(resolvedJobId && jobQuery.data?.status === "succeeded"),
  });

  const runMutation = useMutation({
    mutationFn: (request: BacktestRequest) => api.runBacktest(request),
    onSuccess: (job) => {
      setActiveJobId(job.id);
      queryClient.setQueryData(["job", job.id], job);
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      setToast(t("app.backtestQueued", { id: job.id }));
    },
    onError: (error) => setToast(error.message),
  });

  useEffect(() => {
    if (jobQuery.data?.status === "succeeded" || jobQuery.data?.status === "failed") {
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    }
  }, [jobQuery.data?.status, queryClient]);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(null), 5_000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const job = jobQuery.data ?? jobsQuery.data?.jobs.find((item) => item.id === resolvedJobId);
  const strategies = strategiesQuery.data?.strategies ?? configQuery.data?.strategies ?? [];
  const selectedStrategyMetadata = strategies.find((strategy) => strategy.path === resolvedStrategy);

  function useStrategyForBacktest(path: string) {
    setSelectedStrategy(path);
    setMode("backtest");
    setToast(t("app.strategySelected", { path }));
  }

  function openExperimentRun(jobId: string) {
    setActiveJobId(jobId);
    setMode("backtest");
    setToast(t("app.experimentRunOpened", { id: jobId }));
  }

  return (
    <div className="page-shell">
      <Header health={healthQuery.data} mode={mode} onModeChange={setMode} />

      {mode === "backtest" ? (
        <main className="backtest-workspace">
          <aside className="control-rail" aria-label={t("app.backtestConfig")}>
            <div className="rail-heading">
              <div><span className="section-code">INPUT</span><h2>{t("app.experimentConditions")}</h2></div>
              <button className="source-seal" type="button" onClick={() => setMode("strategies")}>{t("app.editStrategy")}</button>
            </div>
            <BacktestForm
              config={configQuery.data}
              selectedStrategy={resolvedStrategy}
              onStrategyChange={setSelectedStrategy}
              onSubmit={(request) => runMutation.mutate(request)}
              running={runMutation.isPending || job?.status === "queued" || job?.status === "running"}
              opendConnected={healthQuery.data?.opend.connected === true}
              parameterDefinitions={selectedStrategyMetadata?.parameters ?? []}
            />
            <RunHistory
              jobs={jobsQuery.data?.jobs ?? []}
              activeJobId={resolvedJobId}
              onSelect={setActiveJobId}
              onRefresh={() => void jobsQuery.refetch()}
            />
          </aside>
          <section className="result-desk" aria-live="polite">
            <div className="desk-intro">
              <div><span className="section-code">OUTPUT</span><p>{job ? `${job.request.symbol} · ${t(`status.${job.status}`)}` : t("app.waitingConditions")}</p></div>
              <p className="desk-note">{t("app.executionNote")}</p>
            </div>
            <ResultView job={job} result={resultQuery.data} loading={resultQuery.isLoading} />
          </section>
        </main>
      ) : mode === "iterate" ? (
        <Suspense fallback={<div className="workspace-loading">{t("app.loadingExperiments")}</div>}>
          <IterationWorkspace
            config={configQuery.data}
            selectedStrategy={resolvedStrategy}
            onSelectedStrategyChange={setSelectedStrategy}
            opendConnected={healthQuery.data?.opend.connected === true}
            onOpenRun={openExperimentRun}
          />
        </Suspense>
      ) : (
        <Suspense fallback={<div className="workspace-loading">{t("app.loadingEditor")}</div>}>
          <StrategyWorkspace
            strategies={strategies}
            selectedPath={resolvedStrategy}
            onSelectedPathChange={setSelectedStrategy}
            onUseForBacktest={useStrategyForBacktest}
          />
        </Suspense>
      )}

      {toast ? <div className="toast" role="status">{toast}</div> : null}
    </div>
  );
}
