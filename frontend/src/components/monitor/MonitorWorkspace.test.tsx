import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { api } from "../../api/client";
import type {
  MonitorAlert,
  MonitorBarsResponse,
  MonitorRule,
  MonitoredInstrument,
  MonitoringStatusResponse,
  OptionChainResponse,
  OptionContractResponse,
  SnapshotResponse,
} from "../../api/types";
import { I18nProvider } from "../../i18n/I18nProvider";
import { MonitorWorkspace } from "./MonitorWorkspace";

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="location">{`${location.pathname}${location.search}`}</output>;
}

const disabledInstrument: MonitoredInstrument = {
  code: "US.AAPL",
  name: "Apple",
  market: "US",
  instrument_type: "stock",
  underlying_code: null,
  enabled: false,
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
  snapshot: null,
  freshness: "stale",
};

const status: MonitoringStatusResponse = {
  phase: "ready",
  rules_paused: false,
  last_success_at: "2026-07-28T02:00:00Z",
  last_error: null,
  market_states: { us: "OPEN" },
  generic_subscription_budget: {
    generic_total_used: 1,
    generic_remaining: 199,
  },
  freshness: { "US.AAPL": "stale" },
};

const snapshot: SnapshotResponse = {
  freshness: "stale",
  market_state: "OPEN",
  age_seconds: 42,
  snapshot: {
    code: "US.AAPL",
    name: "Apple",
    instrument_type: "stock",
    source: "opend",
    source_time: "2026-07-28 10:00:00",
    fetched_at: "2026-07-28T02:00:42Z",
    last_price: 200,
    previous_close: 198,
    change_rate: 1.01,
    open_price: 199,
    high_price: 201,
    low_price: 197,
    bid_price: 199.9,
    ask_price: 200.1,
    volume: 1_000_000,
    turnover: 200_000_000,
  },
};

const bars: MonitorBarsResponse = {
  code: "US.AAPL",
  ktype: "K_5M",
  bars: [
    {
      code: "US.AAPL",
      source_time: "2026-07-28 09:55:00",
      ktype: "K_5M",
      open: 199,
      high: 200,
      low: 198,
      close: 199.5,
      volume: 1000,
      is_closed: true,
    },
    {
      code: "US.AAPL",
      source_time: "2026-07-28 10:00:00",
      ktype: "K_5M",
      open: 199.5,
      high: 201,
      low: 199,
      close: 200,
      volume: 1200,
      is_closed: false,
    },
  ],
};

const chain: OptionChainResponse = {
  underlying: "US.AAPL",
  expiration: "2026-07-31",
  underlying_snapshot: snapshot.snapshot,
  contracts: [
    {
      code: "US.AAPL260731C200000",
      name: "AAPL C200",
      underlying_code: "US.AAPL",
      option_type: "CALL",
      expiration: "2026-07-31",
      strike_price: 200,
      last_price: 3,
      bid_price: 2.9,
      ask_price: 3.1,
      option_implied_volatility: 20,
      volume: 100,
      option_open_interest: 200,
    },
  ],
  summary: {},
  fetched_at: "2026-07-28T02:00:00Z",
  source: "opend",
};

const contract: OptionContractResponse = {
  contract: chain.contracts[0],
  analytics: {},
  freshness: "live",
};

const rule: MonitorRule = {
  id: "rule-1",
  name: "Price crosses 201",
  code: "US.AAPL",
  underlying_code: "US.AAPL",
  instrument_type: "stock",
  metric: "last_price",
  operator: "crosses_above",
  threshold: 201,
  severity: "warning",
  cooldown_seconds: 300,
  daily_trigger_limit: 10,
  session: "regular",
  enabled: true,
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
};

const alert: MonitorAlert = {
  id: "alert-1",
  dedupe_key: "rule-1:2026-07-28T02:00:00Z",
  rule_id: rule.id,
  rule_name: rule.name,
  code: rule.code,
  underlying_code: "US.AAPL",
  triggered_at: "2026-07-28T02:00:00Z",
  acknowledged_at: null,
  severity: rule.severity,
  metric: rule.metric,
  operator: rule.operator,
  threshold: rule.threshold,
  value: 202,
  source: "opend",
  provider_time: "2026-07-28 10:00:00",
  received_at: "2026-07-28T02:00:01Z",
  snapshot: {},
};

function mockApis(
  options: {
    watchlist?: MonitoredInstrument[];
    status?: MonitoringStatusResponse;
    pendingSnapshot?: boolean;
  } = {},
) {
  vi.spyOn(api, "monitoringStatus").mockResolvedValue(options.status ?? status);
  vi.spyOn(api, "monitoringDiagnostics").mockResolvedValue({
    ready: true,
    checks: [],
  });
  vi.spyOn(api, "watchlist").mockResolvedValue({
    instruments: options.watchlist ?? [disabledInstrument],
  });
  vi.spyOn(api, "underlyingSnapshot").mockImplementation(
    options.pendingSnapshot
      ? () => new Promise(() => undefined)
      : async () => snapshot,
  );
  vi.spyOn(api, "underlyingBars").mockResolvedValue(bars);
  vi.spyOn(api, "optionExpirations").mockResolvedValue({
    underlying: "US.AAPL",
    expirations: [
      { expiration: "2026-07-31", days_to_expiry: 3, cycle: "WEEKLY" },
    ],
    fetched_at: "2026-07-28T02:00:00Z",
  });
  vi.spyOn(api, "optionChain").mockResolvedValue(chain);
  vi.spyOn(api, "optionContract").mockResolvedValue(contract);
  vi.spyOn(api, "monitorRules").mockResolvedValue({ rules: [] });
  vi.spyOn(api, "monitorAlerts").mockResolvedValue({
    alerts: [],
    next_cursor: null,
  });
  vi.spyOn(api, "addWatchlistItem").mockResolvedValue({
    ...disabledInstrument,
    enabled: true,
  });
  vi.spyOn(api, "updateWatchlistItem").mockResolvedValue({
    ...disabledInstrument,
    enabled: true,
  });
  vi.spyOn(api, "deleteWatchlistItem").mockResolvedValue(undefined);
  vi.spyOn(api, "createMonitorRule");
  vi.spyOn(api, "updateMonitorRule");
  vi.spyOn(api, "deleteMonitorRule");
  vi.spyOn(api, "acknowledgeMonitorAlert");
}

function renderWorkspace(path: string, opendConnected: boolean | null = true) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
  const onNotice = vi.fn();
  const workspace = (
    <MonitorWorkspace
      opendConnected={opendConnected}
      onNotice={onNotice}
    />
  );
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <I18nProvider>
          <Routes>
            <Route path="/monitors" element={workspace} />
            <Route path="/monitors/:symbol" element={workspace} />
            <Route path="/monitors/:symbol/options" element={workspace} />
            <Route
              path="/monitors/:symbol/options/:contractCode"
              element={workspace}
            />
            <Route path="/monitors/:symbol/alerts" element={workspace} />
          </Routes>
          <LocationProbe />
        </I18nProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { onNotice, queryClient };
}

describe("MonitorWorkspace", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("keeps stale data visible with explicit freshness, absolute time, age, and generic quota semantics", async () => {
    mockApis();
    renderWorkspace("/monitors/US.AAPL");

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: /Apple.*US\.AAPL/s,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/当前行情已经过期|The current quote is stale/)).toBeInTheDocument();
    expect(screen.getByText(/2026-07-28 10:00:00.*(?:数据年龄 42 秒|data age 42s)/)).toBeInTheDocument();
    expect(screen.getByText(/通用全证券行情订阅余量|Generic all-security quote subs left/)).toBeInTheDocument();
    expect(screen.getByText("199")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /标的概览|Overview/ })).toHaveClass("active");
    expect(screen.getByRole("img")).toBeInTheDocument();
    expect(api.monitoringDiagnostics).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByText(/监控数据诊断|Monitoring data diagnostics/),
    );
    await waitFor(() => expect(api.monitoringDiagnostics).toHaveBeenCalledTimes(1));
    expect(
      (await screen.findAllByText(/全部检查通过|All checks passed/)).length,
    ).toBeGreaterThan(0);
  });

  it("deduplicates a disabled watchlist item by enabling it and navigating instead of posting", async () => {
    mockApis();
    renderWorkspace("/monitors");

    const input = await screen.findByRole("combobox");
    fireEvent.change(input, { target: { value: "US.AAPL" } });
    fireEvent.click(screen.getByRole("button", { name: /添加监控标的|Add a monitored symbol/ }));

    await waitFor(() =>
      expect(api.updateWatchlistItem).toHaveBeenCalledWith("US.AAPL", {
        enabled: true,
      }),
    );
    expect(api.addWatchlistItem).not.toHaveBeenCalled();
    expect(screen.getByLabelText("location")).toHaveTextContent(
      "/monitors/US.AAPL",
    );
  });

  it("preserves option deep links, fetches the contract, and returns to the chain on close", async () => {
    mockApis();
    renderWorkspace(
      "/monitors/US.AAPL/options/US.AAPL260731C200000?expiration=2026-07-31",
    );

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    await waitFor(() =>
      expect(api.optionChain).toHaveBeenCalledWith("US.AAPL", "2026-07-31"),
    );
    expect(api.optionContract).toHaveBeenCalledWith(
      "US.AAPL260731C200000",
    );

    fireEvent.click(
      screen.getByRole("button", { name: /关闭合约详情|Close contract details/ }),
    );
    await waitFor(() =>
      expect(screen.getByLabelText("location")).toHaveTextContent(
        "/monitors/US.AAPL/options?expiration=2026-07-31",
      ),
    );
  });

  it("distinguishes offline and reconnecting states", async () => {
    mockApis();
    const { unmount } = render(
      <QueryClientProvider
        client={new QueryClient({
          defaultOptions: { queries: { retry: false } },
        })}
      >
        <MemoryRouter initialEntries={["/monitors"]}>
          <I18nProvider>
            <MonitorWorkspace opendConnected={false} onNotice={vi.fn()} />
          </I18nProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(
      await screen.findByRole("heading", { name: /OpenD 当前未连接|OpenD is currently offline/ }),
    ).toBeInTheDocument();
    unmount();

    vi.restoreAllMocks();
    mockApis({
      pendingSnapshot: true,
      status: { ...status, phase: "reconnecting", last_error: "socket lost" },
    });
    renderWorkspace("/monitors/US.AAPL");
    expect(
      await screen.findByRole("heading", { name: /行情服务正在重新连接|Market data is reconnecting/ }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("socket lost").length).toBeGreaterThan(0);
  });

  it("retries only valid requests for the active option view", async () => {
    mockApis();
    vi.mocked(api.optionChain).mockRejectedValue(new Error("chain unavailable"));
    renderWorkspace("/monitors/US.AAPL/options?expiration=2026-07-31");

    expect(
      await screen.findByRole("heading", {
        name: /监控请求未完成|The monitoring request did not complete/,
      }),
    ).toBeInTheDocument();
    expect(api.underlyingBars).not.toHaveBeenCalled();
    expect(api.optionContract).not.toHaveBeenCalled();
    expect(api.monitorRules).not.toHaveBeenCalled();
    expect(api.monitorAlerts).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole("button", { name: /重新检查|Check again/ }),
    );

    await waitFor(() => expect(api.optionChain).toHaveBeenCalledTimes(2));
    expect(api.optionExpirations).toHaveBeenCalledTimes(2);
    expect(api.underlyingSnapshot).toHaveBeenCalledTimes(2);
    expect(api.underlyingBars).not.toHaveBeenCalled();
    expect(api.optionContract).not.toHaveBeenCalled();
    expect(api.monitorRules).not.toHaveBeenCalled();
    expect(api.monitorAlerts).not.toHaveBeenCalled();
  });

  it("never retries symbol endpoints with blank parameters while OpenD is offline", async () => {
    mockApis();
    renderWorkspace("/monitors", false);

    expect(
      await screen.findByRole("heading", {
        name: /OpenD 当前未连接|OpenD is currently offline/,
      }),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: /重新检查|Check again/ }),
    );

    await waitFor(() => expect(api.monitoringDiagnostics).toHaveBeenCalledTimes(1));
    expect(api.underlyingSnapshot).not.toHaveBeenCalled();
    expect(api.underlyingBars).not.toHaveBeenCalled();
    expect(api.optionExpirations).not.toHaveBeenCalled();
    expect(api.optionChain).not.toHaveBeenCalled();
    expect(api.optionContract).not.toHaveBeenCalled();
  });

  it("re-enables watchlist, rule, and alert actions after mutations settle", async () => {
    mockApis();
    vi.mocked(api.monitorRules).mockResolvedValue({ rules: [rule] });
    vi.mocked(api.monitorAlerts).mockResolvedValue({
      alerts: [alert],
      next_cursor: null,
    });
    vi.mocked(api.updateWatchlistItem).mockResolvedValue({
      ...disabledInstrument,
      enabled: true,
    });
    vi.mocked(api.updateMonitorRule).mockResolvedValue({
      ...rule,
      enabled: false,
    });
    vi.mocked(api.acknowledgeMonitorAlert).mockResolvedValue({
      ...alert,
      acknowledged_at: "2026-07-28T02:01:00Z",
    });
    renderWorkspace("/monitors/US.AAPL/alerts");

    const watchlistButton = await screen.findByRole("button", {
      name: /启用 US\.AAPL 监控|Enable monitoring for US\.AAPL/,
    });
    fireEvent.click(watchlistButton);
    await waitFor(() => expect(api.updateWatchlistItem).toHaveBeenCalled());
    await waitFor(() => expect(watchlistButton).not.toBeDisabled());

    const ruleButton = await screen.findByRole("button", {
      name: /已启用|Enabled/,
    });
    fireEvent.click(ruleButton);
    await waitFor(() => expect(api.updateMonitorRule).toHaveBeenCalled());
    await waitFor(() => expect(ruleButton).not.toBeDisabled());

    const alertButton = await screen.findByRole("button", {
      name: /确认告警|Acknowledge/,
    });
    fireEvent.click(alertButton);
    await waitFor(() => expect(api.acknowledgeMonitorAlert).toHaveBeenCalled());
    await waitFor(() => expect(alertButton).not.toBeDisabled());
  });
});
