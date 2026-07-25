import { lazy, Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Navigate,
  Route,
  Routes,
  useMatch,
  useNavigate,
} from "react-router-dom";
import { api } from "./api/client";
import { queryKeys } from "./api/queryKeys";
import { useI18n } from "./i18n/I18nContext";
import { useTransientNotice } from "./hooks/useTransientNotice";
import { useApiEvents } from "./hooks/useApiEvents";
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
  const [selectedStrategy, setSelectedStrategy] = useState("");
  const [toast, setToast] = useTransientNotice();
  useApiEvents();
  const backtestNewMatch = useMatch(workspacePaths.backtestNew);
  const backtestDetailMatch = useMatch("/backtests/:jobId");
  const experimentRootMatch = useMatch(workspacePaths.iterate);
  const experimentNewMatch = useMatch(workspacePaths.experimentNew);
  const experimentDetailMatch = useMatch("/experiments/:experimentId");
  const strategyMatch = useMatch("/strategies/*");

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
  const routeStrategy = strategyMatch?.params["*"] ?? "";
  const resolvedStrategy = routeStrategy || selectedStrategy || strategies[0]?.path || "";
  const opendConnected = healthQuery.data?.opend.connected === true;
  const activeJobId = backtestNewMatch
    ? null
    : backtestDetailMatch?.params.jobId ?? null;
  const backtestRail = backtestNewMatch ? "create" : "archive";
  const activeExperimentId = experimentNewMatch
    ? null
    : experimentDetailMatch?.params.experimentId ?? null;

  function useStrategyForBacktest(path: string) {
    setSelectedStrategy(path);
    setToast(t("app.strategySelected", { path }));
    navigate(workspacePaths.backtestNew);
  }

  function openExperimentRun(jobId: string) {
    setToast(t("app.experimentRunOpened", { id: jobId }));
    navigate(workspacePaths.backtestDetail(jobId));
  }

  const backtestWorkspace = (
    <BacktestWorkspace
      config={configQuery.data}
      strategies={strategies}
      selectedStrategy={resolvedStrategy}
      onSelectedStrategyChange={setSelectedStrategy}
      rail={backtestRail}
      onRailChange={(rail) =>
        navigate(
          rail === "create" ? workspacePaths.backtestNew : workspacePaths.backtest
        )}
      activeJobId={activeJobId}
      onActiveJobChange={(jobId) =>
        navigate(
          jobId
            ? workspacePaths.backtestDetail(jobId)
            : workspacePaths.backtest
        )}
      opendConnected={opendConnected}
      onNotice={setToast}
    />
  );
  const iterationWorkspace = (
    <Suspense
      fallback={
        <div className="workspace-loading">{t("app.loadingExperiments")}</div>
      }
    >
      <IterationWorkspace
        config={configQuery.data}
        selectedStrategy={resolvedStrategy}
        onSelectedStrategyChange={setSelectedStrategy}
        activeExperimentId={activeExperimentId}
        selectDefaultExperiment={Boolean(experimentRootMatch)}
        onActiveExperimentChange={(experimentId) =>
          navigate(workspacePaths.experimentDetail(experimentId))
        }
        opendConnected={opendConnected}
        onOpenRun={openExperimentRun}
      />
    </Suspense>
  );

  return (
    <div className="page-shell">
      <Header health={healthQuery.data} />

      <Routes>
        <Route path="/" element={<Navigate to={workspacePaths.backtest} replace />} />
        <Route
          path={workspacePaths.backtest}
          element={backtestWorkspace}
        />
        <Route path={workspacePaths.backtestNew} element={backtestWorkspace} />
        <Route path="/backtests/:jobId" element={backtestWorkspace} />
        <Route
          path={workspacePaths.iterate}
          element={iterationWorkspace}
        />
        <Route path={workspacePaths.experimentNew} element={iterationWorkspace} />
        <Route path="/experiments/:experimentId" element={iterationWorkspace} />
        <Route
          path="/strategies/*"
          element={(
            <Suspense fallback={<div className="workspace-loading">{t("app.loadingEditor")}</div>}>
              <StrategyWorkspace
                strategies={strategies}
                selectedPath={resolvedStrategy}
                onSelectedPathChange={(path) => {
                  setSelectedStrategy(path);
                  navigate(workspacePaths.strategyDetail(path));
                }}
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
