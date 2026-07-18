import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { AppConfig, ExperimentRequest } from "../api/types";
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
  const queryClient = useQueryClient();
  const [activeExperimentId, setActiveExperimentId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const experimentsQuery = useQuery({ queryKey: ["experiments"], queryFn: api.experiments });
  const cacheQuery = useQuery({ queryKey: ["cache"], queryFn: api.cache });
  const resolvedExperimentId = activeExperimentId ?? experimentsQuery.data?.experiments[0]?.id ?? null;
  const experimentQuery = useQuery({
    queryKey: ["experiment", resolvedExperimentId],
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
      queryClient.setQueryData(["experiment", experiment.id], experiment);
      void queryClient.invalidateQueries({ queryKey: ["experiments"] });
      setNotice(`${experiment.name} 已开始，共 ${experiment.progress.total} 组参数。`);
    },
    onError: (error) => setNotice(error.message),
  });
  const deleteMutation = useMutation({
    mutationFn: api.deleteCache,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["cache"] });
      setNotice("OpenD 行情缓存已删除。");
    },
    onError: (error) => setNotice(error.message),
  });

  useEffect(() => {
    const status = experimentQuery.data?.status;
    if (status === "succeeded" || status === "failed") {
      void queryClient.invalidateQueries({ queryKey: ["experiments"] });
      void queryClient.invalidateQueries({ queryKey: ["cache"] });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    }
  }, [experimentQuery.data?.status, queryClient]);

  useEffect(() => {
    if (!notice) return undefined;
    const timer = window.setTimeout(() => setNotice(null), 5_000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const selectedMetadata = config?.strategies.find((strategy) => strategy.path === selectedStrategy);
  const definitions = selectedMetadata?.parameters ?? [];

  function deleteCache(cacheId: string) {
    if (window.confirm("删除后，下一次相同条件的回测将重新从 OpenD 拉取行情。继续吗？")) {
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
        />
        <CachePanel
          cache={cacheQuery.data}
          loading={cacheQuery.isLoading}
          deletingId={deleteMutation.variables ?? null}
          onDelete={deleteCache}
          onRefresh={() => void cacheQuery.refetch()}
        />
      </div>
      {notice ? <div className="toast" role="status">{notice}</div> : null}
    </main>
  );
}
