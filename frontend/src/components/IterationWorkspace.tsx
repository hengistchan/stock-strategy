import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { queryKeys } from "../api/queryKeys";
import type { AppConfig, ExperimentRequest } from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import { useSymbolNames } from "../hooks/useSymbolNames";
import { useTransientNotice } from "../hooks/useTransientNotice";
import { CachePanel } from "./CachePanel";
import { ExperimentBoard } from "./ExperimentBoard";
import { ExperimentForm } from "./ExperimentForm";

interface IterationWorkspaceProps {
  config?: AppConfig;
  selectedStrategy: string;
  onSelectedStrategyChange: (path: string) => void;
  opendConnected: boolean;
  onOpenRun: (jobId: string) => void;
}

export function IterationWorkspace({
  config,
  selectedStrategy,
  onSelectedStrategyChange,
  opendConnected,
  onOpenRun,
}: IterationWorkspaceProps) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [activeExperimentId, setActiveExperimentId] = useState<string | null>(null);
  const [notice, setNotice] = useTransientNotice();
  const experimentsQuery = useQuery({ queryKey: queryKeys.experiments, queryFn: api.experiments });
  const cacheQuery = useQuery({ queryKey: queryKeys.cache, queryFn: api.cache });
  const resolvedExperimentId = activeExperimentId ?? experimentsQuery.data?.experiments[0]?.id ?? null;
  const experimentQuery = useQuery({
    queryKey: queryKeys.experiment(resolvedExperimentId),
    queryFn: () => api.experiment(resolvedExperimentId!),
    enabled: Boolean(resolvedExperimentId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 700 : false;
    },
  });
  const runMutation = useMutation({
    mutationFn: (request: ExperimentRequest) => api.runExperiment(request),
    onSuccess: (experiment) => {
      setActiveExperimentId(experiment.id);
      queryClient.setQueryData(queryKeys.experiment(experiment.id), experiment);
      void queryClient.invalidateQueries({ queryKey: queryKeys.experiments });
      setNotice(t("experiment.started", { name: experiment.name, count: experiment.progress.total }));
    },
    onError: (error) => setNotice(error.message),
  });
  const deleteMutation = useMutation({
    mutationFn: api.deleteCache,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.cache });
      setNotice(t("experiment.cacheDeleted"));
    },
    onError: (error) => setNotice(error.message),
  });

  useEffect(() => {
    const status = experimentQuery.data?.status;
    if (status === "succeeded" || status === "failed") {
      void queryClient.invalidateQueries({ queryKey: queryKeys.experiments });
      void queryClient.invalidateQueries({ queryKey: queryKeys.cache });
      void queryClient.invalidateQueries({ queryKey: queryKeys.jobs });
    }
  }, [experimentQuery.data?.status, queryClient]);

  const selectedMetadata = config?.strategies.find((strategy) => strategy.path === selectedStrategy);
  const definitions = selectedMetadata?.parameters ?? [];
  const symbolNames = useSymbolNames(
    [
      ...(experimentsQuery.data?.experiments ?? []).map((item) => item.base_request.symbol),
      ...(experimentQuery.data ? [experimentQuery.data.base_request.symbol] : []),
      ...(cacheQuery.data?.entries ?? []).map((entry) => entry.symbol),
    ],
    opendConnected,
  );

  function deleteCache(cacheId: string) {
    if (window.confirm(t("experiment.confirmDeleteCache"))) {
      deleteMutation.mutate(cacheId);
    }
  }

  return (
    <main className="iteration-workspace">
      <aside className="iteration-control">
        <ExperimentForm
          key={selectedStrategy}
          config={config}
          selectedStrategy={selectedStrategy}
          parameterDefinitions={definitions}
          onStrategyChange={onSelectedStrategyChange}
          onSubmit={(request) => runMutation.mutate(request)}
          running={runMutation.isPending || experimentQuery.data?.status === "running"}
          opendConnected={opendConnected}
        />
      </aside>
      <div className="iteration-desk">
        <ExperimentBoard
          key={resolvedExperimentId ?? "empty"}
          experiments={experimentsQuery.data?.experiments ?? []}
          experiment={experimentQuery.data}
          activeExperimentId={resolvedExperimentId}
          onSelectExperiment={setActiveExperimentId}
          onOpenRun={onOpenRun}
          symbolNames={symbolNames}
        />
        <CachePanel
          cache={cacheQuery.data}
          loading={cacheQuery.isLoading}
          deletingId={deleteMutation.variables ?? null}
          onDelete={deleteCache}
          onRefresh={() => void cacheQuery.refetch()}
          symbolNames={symbolNames}
        />
      </div>
      {notice ? <div className="toast" role="status">{notice}</div> : null}
    </main>
  );
}
