import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "../api/queryKeys";
import type { BacktestJob } from "../api/types";

interface StateEvent {
  id: string;
  status: string;
}

export function parseStateEvent(event: MessageEvent<string>): StateEvent | null {
  try {
    const payload: unknown = JSON.parse(event.data);
    if (
      payload &&
      typeof payload === "object" &&
      "id" in payload &&
      "status" in payload &&
      typeof payload.id === "string" &&
      typeof payload.status === "string"
    ) {
      return { id: payload.id, status: payload.status };
    }
  } catch {
    return null;
  }
  return null;
}

export function useApiEvents(): void {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const source = new EventSource("/api/events", { withCredentials: true });

    const onJobUpdated = (rawEvent: Event) => {
      const event = parseStateEvent(rawEvent as MessageEvent<string>);
      if (!event) return;
      queryClient.setQueryData<BacktestJob>(
        queryKeys.job(event.id),
        (job) => (job ? { ...job, status: event.status as BacktestJob["status"] } : job),
      );
      void queryClient.invalidateQueries({ queryKey: queryKeys.job(event.id) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.jobs });
      if (event.status === "succeeded") {
        void queryClient.invalidateQueries({ queryKey: queryKeys.result(event.id) });
      }
    };

    const onExperimentUpdated = (rawEvent: Event) => {
      const event = parseStateEvent(rawEvent as MessageEvent<string>);
      if (!event) return;
      void queryClient.invalidateQueries({
        queryKey: queryKeys.experiment(event.id),
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.experiments });
      if (
        event.status === "succeeded" ||
        event.status === "failed" ||
        event.status === "partial"
      ) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.cache });
        void queryClient.invalidateQueries({ queryKey: queryKeys.jobs });
      }
    };

    source.addEventListener("job.updated", onJobUpdated);
    source.addEventListener("experiment.updated", onExperimentUpdated);
    return () => {
      source.removeEventListener("job.updated", onJobUpdated);
      source.removeEventListener("experiment.updated", onExperimentUpdated);
      source.close();
    };
  }, [queryClient]);
}
