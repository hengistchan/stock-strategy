import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "../api/queryKeys";
import type { BacktestJob } from "../api/types";

interface StateEvent {
  id: string;
  status: string;
}

interface MonitorQuoteEvent {
  code: string;
  instrumentType: string | null;
  underlyingCode: string | null;
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

function parseMonitorQuoteEvent(event: MessageEvent<string>): MonitorQuoteEvent | null {
  try {
    const payload: unknown = JSON.parse(event.data);
    if (!isRecord(payload) || typeof payload.code !== "string") return null;
    const code = payload.code.trim().toUpperCase();
    if (!code) return null;
    const snapshot = isRecord(payload.snapshot) ? payload.snapshot : null;
    const instrumentType =
      snapshot && typeof snapshot.instrument_type === "string"
        ? snapshot.instrument_type
        : null;
    const underlyingCode =
      snapshot && typeof snapshot.underlying_code === "string"
        ? snapshot.underlying_code.trim().toUpperCase() || null
        : null;
    return { code, instrumentType, underlyingCode };
  } catch {
    return null;
  }
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
        event.status === "completed_with_errors"
      ) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.cache });
        void queryClient.invalidateQueries({ queryKey: queryKeys.jobs });
      }
    };

    const onStreamReady = () => {
      // A reconnect can skip events, so the durable REST state is authoritative.
      void queryClient.invalidateQueries({ queryKey: queryKeys.monitoring });
    };

    const onMonitorQuoteUpdated = (rawEvent: Event) => {
      const event = parseMonitorQuoteEvent(rawEvent as MessageEvent<string>);
      if (!event) return;
      void queryClient.invalidateQueries({
        queryKey: queryKeys.monitorSnapshot(event.code),
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.watchlist });

      if (event.instrumentType === "option" || event.underlyingCode) {
        void queryClient.invalidateQueries({
          queryKey: queryKeys.optionContract(event.code),
        });
      }
      const chainUnderlying = event.underlyingCode ?? event.code;
      void queryClient.invalidateQueries({
        queryKey: [...queryKeys.monitoring, "option-chain", chainUnderlying],
      });
    };

    const onMonitorStatusUpdated = () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.monitoringStatus,
      });
    };

    const onMonitorWatchlistUpdated = () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.watchlist });
    };

    const onMonitorRuleUpdated = () => {
      void queryClient.invalidateQueries({
        queryKey: [...queryKeys.monitoring, "rules"],
      });
    };

    const onMonitorAlertUpdated = () => {
      void queryClient.invalidateQueries({
        queryKey: [...queryKeys.monitoring, "alerts"],
      });
    };

    source.addEventListener("job.updated", onJobUpdated);
    source.addEventListener("experiment.updated", onExperimentUpdated);
    source.addEventListener("stream.ready", onStreamReady);
    source.addEventListener("monitor.quote.updated", onMonitorQuoteUpdated);
    source.addEventListener("monitor.status.updated", onMonitorStatusUpdated);
    source.addEventListener("monitor.watchlist.updated", onMonitorWatchlistUpdated);
    source.addEventListener("monitor.rule.updated", onMonitorRuleUpdated);
    source.addEventListener("monitor.rule.suppressed", onMonitorRuleUpdated);
    source.addEventListener("monitor.alert.triggered", onMonitorAlertUpdated);
    source.addEventListener("monitor.alert.acknowledged", onMonitorAlertUpdated);
    source.addEventListener(
      "monitor.subscription.updated",
      onMonitorStatusUpdated,
    );
    return () => {
      source.removeEventListener("job.updated", onJobUpdated);
      source.removeEventListener("experiment.updated", onExperimentUpdated);
      source.removeEventListener("stream.ready", onStreamReady);
      source.removeEventListener("monitor.quote.updated", onMonitorQuoteUpdated);
      source.removeEventListener("monitor.status.updated", onMonitorStatusUpdated);
      source.removeEventListener(
        "monitor.watchlist.updated",
        onMonitorWatchlistUpdated,
      );
      source.removeEventListener("monitor.rule.updated", onMonitorRuleUpdated);
      source.removeEventListener("monitor.rule.suppressed", onMonitorRuleUpdated);
      source.removeEventListener("monitor.alert.triggered", onMonitorAlertUpdated);
      source.removeEventListener(
        "monitor.alert.acknowledged",
        onMonitorAlertUpdated,
      );
      source.removeEventListener(
        "monitor.subscription.updated",
        onMonitorStatusUpdated,
      );
      source.close();
    };
  }, [queryClient]);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
