import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { queryKeys } from "../api/queryKeys";
import type { BacktestJob } from "../api/types";
import { parseStateEvent, useApiEvents } from "./useApiEvents";

type EventSourceListener = EventListenerOrEventListenerObject;

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  readonly url: string;
  readonly withCredentials: boolean;
  readonly addedTypes: string[] = [];
  readonly removedTypes: string[] = [];
  closeCalls = 0;
  private readonly listeners = new Map<string, Set<EventSourceListener>>();

  constructor(url: string | URL, options?: EventSourceInit) {
    this.url = String(url);
    this.withCredentials = options?.withCredentials ?? false;
    FakeEventSource.instances.push(this);
  }

  addEventListener(
    type: string,
    listener: EventSourceListener | null,
  ): void {
    if (!listener) return;
    const listeners = this.listeners.get(type) ?? new Set();
    listeners.add(listener);
    this.listeners.set(type, listeners);
    this.addedTypes.push(type);
  }

  removeEventListener(
    type: string,
    listener: EventSourceListener | null,
  ): void {
    if (!listener) return;
    this.listeners.get(type)?.delete(listener);
    this.removedTypes.push(type);
  }

  close(): void {
    this.closeCalls += 1;
  }

  dispatch(type: string, payload: unknown): void {
    const event = new MessageEvent(type, {
      data: typeof payload === "string" ? payload : JSON.stringify(payload),
    });
    for (const listener of this.listeners.get(type) ?? []) {
      if (typeof listener === "function") {
        listener.call(this as unknown as EventSource, event);
      } else {
        listener.handleEvent(event);
      }
    }
  }

  activeListenerCount(): number {
    return [...this.listeners.values()].reduce(
      (count, listeners) => count + listeners.size,
      0,
    );
  }

  static reset(): void {
    FakeEventSource.instances = [];
  }
}

function EventsProbe(): null {
  useApiEvents();
  return null;
}

function mountEvents(queryClient: QueryClient) {
  return render(
    createElement(
      QueryClientProvider,
      { client: queryClient },
      createElement(EventsProbe),
    ),
  );
}

function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

function currentSource(): FakeEventSource {
  const source = FakeEventSource.instances.at(-1);
  if (!source) throw new Error("EventSource was not created");
  return source;
}

beforeEach(() => {
  FakeEventSource.reset();
  vi.stubGlobal(
    "EventSource",
    FakeEventSource as unknown as typeof EventSource,
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("parseStateEvent", () => {
  it("accepts state events and rejects malformed payloads", () => {
    expect(
      parseStateEvent(
        new MessageEvent("job.updated", {
          data: JSON.stringify({ id: "job-1", status: "running" }),
        }),
      ),
    ).toEqual({ id: "job-1", status: "running" });
    expect(
      parseStateEvent(new MessageEvent("job.updated", { data: "not-json" })),
    ).toBeNull();
    expect(
      parseStateEvent(
        new MessageEvent("job.updated", {
          data: JSON.stringify({ id: 1, status: "running" }),
        }),
      ),
    ).toBeNull();
  });
});

describe("useApiEvents", () => {
  it("opens the shared stream with credentials and registers every event", () => {
    const queryClient = createQueryClient();
    mountEvents(queryClient);

    const source = currentSource();
    expect(source.url).toBe("/api/events");
    expect(source.withCredentials).toBe(true);
    expect(source.addedTypes).toEqual([
      "job.updated",
      "experiment.updated",
      "stream.ready",
      "monitor.quote.updated",
      "monitor.status.updated",
      "monitor.watchlist.updated",
      "monitor.rule.updated",
      "monitor.rule.suppressed",
      "monitor.alert.triggered",
      "monitor.alert.acknowledged",
      "monitor.subscription.updated",
    ]);
  });

  it("invalidates precise durable monitoring queries for valid events", () => {
    const queryClient = createQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    mountEvents(queryClient);
    const source = currentSource();

    act(() => {
      source.dispatch("monitor.quote.updated", {
        code: "us.aapl",
        snapshot: { instrument_type: "stock" },
      });
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.monitorSnapshot("US.AAPL"),
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.watchlist,
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: [...queryKeys.monitoring, "option-chain", "US.AAPL"],
    });

    invalidate.mockClear();
    act(() => {
      source.dispatch("monitor.quote.updated", {
        code: "us.aapl260807c100000",
        snapshot: {
          instrument_type: "option",
          underlying_code: "us.aapl",
        },
      });
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.monitorSnapshot("US.AAPL260807C100000"),
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.optionContract("US.AAPL260807C100000"),
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: [...queryKeys.monitoring, "option-chain", "US.AAPL"],
    });

    invalidate.mockClear();
    act(() => {
      source.dispatch("monitor.status.updated", {});
      source.dispatch("monitor.subscription.updated", {});
      source.dispatch("monitor.watchlist.updated", {});
      source.dispatch("monitor.rule.updated", {});
      source.dispatch("monitor.rule.suppressed", {});
      source.dispatch("monitor.alert.triggered", {});
      source.dispatch("monitor.alert.acknowledged", {});
    });
    expect(invalidate).toHaveBeenCalledTimes(7);
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.monitoringStatus,
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.watchlist,
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: [...queryKeys.monitoring, "rules"],
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: [...queryKeys.monitoring, "alerts"],
    });
  });

  it("treats stream.ready as a reconnect gap and ignores malformed quotes", () => {
    const queryClient = createQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    mountEvents(queryClient);
    const source = currentSource();

    act(() => {
      source.dispatch("monitor.quote.updated", "not-json");
      source.dispatch("monitor.quote.updated", {
        snapshot: { instrument_type: "stock" },
      });
    });
    expect(invalidate).not.toHaveBeenCalled();

    act(() => {
      source.dispatch("stream.ready", {
        connected_at: "2026-07-29T10:00:00+08:00",
      });
    });
    expect(invalidate).toHaveBeenCalledOnce();
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.monitoring,
    });
  });

  it("preserves job and experiment handling", () => {
    const queryClient = createQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    queryClient.setQueryData<BacktestJob>(
      queryKeys.job("job-1"),
      backtestJob(),
    );
    mountEvents(queryClient);
    const source = currentSource();

    act(() => {
      source.dispatch("job.updated", {
        id: "job-1",
        status: "succeeded",
      });
      source.dispatch("experiment.updated", {
        id: "experiment-1",
        status: "completed_with_errors",
      });
    });

    expect(
      queryClient.getQueryData<BacktestJob>(queryKeys.job("job-1"))?.status,
    ).toBe("succeeded");
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.job("job-1"),
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.jobs,
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.result("job-1"),
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.experiment("experiment-1"),
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.experiments,
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.cache,
    });
  });

  it("removes every listener and closes the stream on unmount", () => {
    const queryClient = createQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const mounted = mountEvents(queryClient);
    const source = currentSource();
    expect(source.activeListenerCount()).toBe(11);

    mounted.unmount();

    expect(source.activeListenerCount()).toBe(0);
    expect(source.removedTypes).toEqual(source.addedTypes);
    expect(source.closeCalls).toBe(1);
    act(() => {
      source.dispatch("stream.ready", {});
      source.dispatch("monitor.status.updated", {});
    });
    expect(invalidate).not.toHaveBeenCalled();
  });
});

function backtestJob(): BacktestJob {
  return {
    id: "job-1",
    status: "running",
    created_at: "2026-07-29T10:00:00Z",
    started_at: "2026-07-29T10:00:01Z",
    finished_at: null,
    request: {
      strategy: "examples/ma_cross.py",
      symbol: "US.AAPL",
      start: "2026-01-01",
      end: "2026-07-29",
      ktype: "K_DAY",
      autype: "QFQ",
      initial_cash: 100_000,
      commission_bps: 3,
      min_commission: 1,
      slippage_bps: 5,
      warmup_bars: 0,
      allow_short: false,
    },
    strategy_path: "examples/ma_cross.py",
    run_dir: null,
    stdout: "",
    stderr: "",
    error: null,
  };
}
