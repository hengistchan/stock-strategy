import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";
import { api } from "../api/client";
import type { PortfolioResult } from "../api/types";
import { PortfolioWorkspace } from "./PortfolioWorkspace";

vi.mock("./PerformanceChart", () => ({
  PerformanceChart: () => <div>performance chart</div>,
}));

afterEach(() => vi.restoreAllMocks());

describe("PortfolioWorkspace", () => {
  it("submits normalized stock weights to the shared-cash portfolio API", async () => {
    const run = vi.spyOn(api, "runPortfolio").mockImplementation(
      () => new Promise(() => undefined),
    );
    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false } },
    });
    renderWorkspace(queryClient);

    fireEvent.change(screen.getByLabelText("标的代码"), {
      target: { value: "US.AAPL, US.MSFT" },
    });
    fireEvent.change(screen.getByLabelText("目标权重"), {
      target: { value: "70, 30" },
    });
    fireEvent.click(screen.getByRole("button", { name: "运行组合回测" }));

    await waitFor(() => expect(run).toHaveBeenCalled());
    expect(run.mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({
        weights: { "US.AAPL": 70, "US.MSFT": 30 },
        rebalance: "monthly",
        ktype: "K_DAY",
      }),
    );
  });

  it("adds, re-enables, and reuses portfolio symbols before opening monitoring", async () => {
    vi.spyOn(api, "runPortfolio").mockResolvedValue(portfolioResult());
    vi.spyOn(api, "watchlist").mockResolvedValue({
      instruments: [
        monitoredInstrument("US.AAPL", true),
        monitoredInstrument("US.MSFT", false),
      ],
    });
    const add = vi.spyOn(api, "addWatchlistItem").mockImplementation(
      async (payload) => monitoredInstrument(payload.code, true),
    );
    const update = vi.spyOn(api, "updateWatchlistItem").mockImplementation(
      async (code) => monitoredInstrument(code, true),
    );
    const onNotice = vi.fn();
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    renderWorkspace(queryClient, onNotice);

    fireEvent.click(screen.getByRole("button", { name: "运行组合回测" }));
    fireEvent.click(
      await screen.findByRole("button", {
        name: /将 3 个标的加入监控|Monitor 3 symbols/,
      }),
    );

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith("US.MSFT", { enabled: true }),
    );
    expect(add).toHaveBeenCalledWith({
      code: "US.NVDA",
      name: "US.NVDA",
      instrument_type: "stock",
      enabled: true,
    });
    expect(add).toHaveBeenCalledTimes(1);
    expect(update).toHaveBeenCalledTimes(1);
    expect(onNotice).toHaveBeenCalledWith(
      expect.stringMatching(
        /已同步 3 个标的：新增 1、重新启用 1、已有 1。|Synced 3 symbols: 1 added, 1 re-enabled, 1 already present\./,
      ),
    );
    expect(screen.getByLabelText("current-path")).toHaveTextContent(
      "/monitors/US.AAPL",
    );
  });
});

function renderWorkspace(queryClient: QueryClient, onNotice = vi.fn()) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/portfolios"]}>
        <PortfolioWorkspace
          opendConnected
          onNotice={onNotice}
        />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function LocationProbe() {
  return <output aria-label="current-path">{useLocation().pathname}</output>;
}

function monitoredInstrument(code: string, enabled: boolean) {
  return {
    code,
    name: code,
    market: code.split(".", 1)[0],
    instrument_type: "stock" as const,
    underlying_code: null,
    enabled,
    created_at: "2026-07-29T00:00:00Z",
    updated_at: "2026-07-29T00:00:00Z",
    snapshot: null,
    freshness: "unavailable" as const,
  };
}

function portfolioResult(): PortfolioResult {
  const request = {
    weights: { "US.AAPL": 40, "US.MSFT": 35, "US.NVDA": 25 },
    start: "2024-01-01",
    end: "2025-12-31",
    initial_cash: 100_000,
    commission_bps: 3,
    min_commission: 1,
    slippage_bps: 5,
    rebalance: "monthly" as const,
    ktype: "K_DAY" as const,
    autype: "QFQ" as const,
    session: "ALL" as const,
  };
  return {
    id: "portfolio-1",
    created_at: "2026-07-29T00:00:00Z",
    source: "opend",
    request,
    market_data_sha256: {},
    metrics: {
      total_return_pct: 1,
      benchmark_return_pct: 0,
      max_drawdown_pct: -2,
      sharpe_ratio: 0.5,
      total_trades: 3,
      total_fees: 3,
      exposure_pct: 100,
    },
    period: { start: request.start, end: request.end, bars: 10 },
    weights: {
      "US.AAPL": 0.4,
      "US.MSFT": 0.35,
      "US.NVDA": 0.25,
    },
    positions: [
      {
        symbol: "US.AAPL",
        quantity: 10,
        mark_price: 100,
        market_value: 1_000,
      },
    ],
    cash: 0,
    transactions: [],
    equity_curve: [],
    engine_contract: {
      shared_cash: true,
      unified_clock: "K_DAY",
      integer_shares: true,
      execution: "next-bar",
      currency: "USD",
    },
  };
}
