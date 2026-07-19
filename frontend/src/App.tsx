import { lazy, Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api } from "./api/client";
import { queryKeys } from "./api/queryKeys";
import { useI18n } from "./i18n/I18nContext";
import { useTransientNotice } from "./hooks/useTransientNotice";
import type { BacktestRail } from "./lib/backtestWorkspace";
import { workspacePaths } from "./lib/workspaceRoutes";
import { BacktestWorkspace } from "./components/BacktestWorkspace";
import { Header } from "./components/Header";

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
  const navigate = useNavigate();
  const [backtestRail, setBacktestRail] = useState<BacktestRail>("archive");
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [selectedStrategy, setSelectedStrategy] = useState("");
  const [toast, setToast] = useTransientNotice();

  const healthQuery = useQuery({
    queryKey: queryKeys.health,
    queryFn: api.health,
    refetchInterval: 5_000,
  });
  const configQuery = useQuery({ queryKey: queryKeys.config, queryFn: api.config });
  const strategiesQuery = useQuery({
    queryKey: queryKeys.strategies,
    queryFn: api.strategies,
  });
  const strategies = strategiesQuery.data?.strategies ?? configQuery.data?.strategies ?? [];
  const resolvedStrategy = selectedStrategy || strategies[0]?.path || "";
  const opendConnected = healthQuery.data?.opend.connected === true;

  function useStrategyForBacktest(path: string) {
    setSelectedStrategy(path);
    setBacktestRail("create");
    setToast(t("app.strategySelected", { path }));
    navigate(workspacePaths.backtest);
  }

  function openExperimentRun(jobId: string) {
    setActiveJobId(jobId);
    setBacktestRail("archive");
    setToast(t("app.experimentRunOpened", { id: jobId }));
    navigate(workspacePaths.backtest);
  }

  return (
    <div className="page-shell">
      <Header health={healthQuery.data} />

      <Routes>
        <Route path="/" element={<Navigate to={workspacePaths.backtest} replace />} />
        <Route
          path={workspacePaths.backtest}
          element={(
            <BacktestWorkspace
              config={configQuery.data}
              strategies={strategies}
              selectedStrategy={resolvedStrategy}
              onSelectedStrategyChange={setSelectedStrategy}
              rail={backtestRail}
              onRailChange={setBacktestRail}
              activeJobId={activeJobId}
              onActiveJobChange={setActiveJobId}
              opendConnected={opendConnected}
              onNotice={setToast}
            />
          )}
        />
        <Route
          path={workspacePaths.iterate}
          element={(
            <Suspense fallback={<div className="workspace-loading">{t("app.loadingExperiments")}</div>}>
              <IterationWorkspace
                config={configQuery.data}
                selectedStrategy={resolvedStrategy}
                onSelectedStrategyChange={setSelectedStrategy}
                opendConnected={opendConnected}
                onOpenRun={openExperimentRun}
              />
            </Suspense>
          )}
        />
        <Route
          path={workspacePaths.strategies}
          element={(
            <Suspense fallback={<div className="workspace-loading">{t("app.loadingEditor")}</div>}>
              <StrategyWorkspace
                strategies={strategies}
                selectedPath={resolvedStrategy}
                onSelectedPathChange={setSelectedStrategy}
                onUseForBacktest={useStrategyForBacktest}
              />
            </Suspense>
          )}
        />
        <Route path="*" element={<Navigate to={workspacePaths.backtest} replace />} />
      </Routes>

      {toast ? <div className="toast" role="status">{toast}</div> : null}
    </div>
  );
}
