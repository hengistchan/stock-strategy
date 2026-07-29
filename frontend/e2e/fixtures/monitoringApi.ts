import { expect, type Page, type Route } from "@playwright/test";
import type {
  MonitorAlert,
  MonitorRule,
  MonitoredInstrument,
} from "../../src/api/types";
import { installFakeEventSource } from "./fakeEventSource";

export type MonitoringDataMode =
  | "live"
  | "stale"
  | "market_closed"
  | "permission"
  | "quota"
  | "offline"
  | "unavailable";

export interface MonitoringMockOptions {
  locale?: "zh-CN" | "en-US";
  connected?: boolean;
  initialInstruments?: Array<{
    code: "US.AAPL" | "HK.00700";
    enabled?: boolean;
  }>;
}

type JsonObject = Record<string, unknown>;

const FIXED_NOW = "2026-07-28T14:30:05-04:00";
const EXPIRATIONS = [
  { expiration: "2026-08-07", days_to_expiry: 10, cycle: "WEEK" },
  { expiration: "2026-08-14", days_to_expiry: 17, cycle: "WEEK" },
];

const SYMBOLS = [
  {
    code: "US.AAPL",
    name: "Apple Inc. / 苹果",
    market: "US",
  },
  {
    code: "HK.00700",
    name: "Tencent Holdings / 腾讯控股",
    market: "HK",
  },
];

const CONTRACTS = {
  call195: "US.AAPL260807C195000",
  put195: "US.AAPL260807P195000",
  call200: "US.AAPL260807C200000",
  put200: "US.AAPL260807P200000",
  call205: "US.AAPL260807C205000",
} as const;

export const monitoringContracts = CONTRACTS;

export class MonitoringApiMock {
  private connected: boolean;
  private marketDataMode: MonitoringDataMode = "live";
  private readonly instruments = new Map<string, MonitoredInstrument>();
  private readonly rules = new Map<string, MonitorRule>();
  private readonly alerts = new Map<string, MonitorAlert>();
  private readonly requestCounts = new Map<string, number>();
  private readonly unhandled: string[] = [];
  private readonly quotes = new Map<string, JsonObject>();
  private nextRuleId = 1;
  private nextAlertId = 1;

  constructor(options: MonitoringMockOptions = {}) {
    this.connected = options.connected ?? true;
    this.quotes.set("US.AAPL", stockQuote("US.AAPL"));
    this.quotes.set("HK.00700", stockQuote("HK.00700"));
    for (const item of options.initialInstruments ?? []) {
      this.instruments.set(
        item.code,
        this.makeInstrument(item.code, item.enabled ?? true),
      );
    }
  }

  async install(
    page: Page,
    locale: "zh-CN" | "en-US" = "en-US",
  ): Promise<void> {
    await installFakeEventSource(page);
    await page.addInitScript(
      ({ storageKey, storageValue }) => {
        if (window.localStorage.getItem(storageKey) === null) {
          window.localStorage.setItem(storageKey, storageValue);
        }
      },
      {
        storageKey: "strategy-lab.locale",
        storageValue: locale,
      },
    );
    await page.route("**/api/**", (route) => this.handle(route));
  }

  setConnected(connected: boolean): void {
    this.connected = connected;
  }

  setMarketDataMode(mode: MonitoringDataMode): void {
    this.marketDataMode = mode;
  }

  updateQuote(code: string, patch: JsonObject): JsonObject {
    const normalized = normalizeCode(code);
    const next = {
      ...(this.quotes.get(normalized) ?? stockQuote(normalized)),
      ...patch,
      code: normalized,
      fetched_at: FIXED_NOW,
    };
    this.quotes.set(normalized, next);
    return structuredClone(next);
  }

  requestCount(method: string, pathname: string): number {
    return this.requestCounts.get(requestKey(method, pathname)) ?? 0;
  }

  findRule(name: string): MonitorRule | undefined {
    return [...this.rules.values()].find((rule) => rule.name === name);
  }

  addAlertForRule(name: string, value: number): MonitorAlert {
    const rule = this.findRule(name);
    if (!rule) throw new Error(`No mocked rule named ${name}`);
    const id = `alert-${this.nextAlertId++}`;
    const alert: MonitorAlert = {
      id,
      dedupe_key: `${rule.id}:2026-07-28:${id}`,
      rule_id: rule.id,
      rule_name: rule.name,
      code: rule.code,
      triggered_at: FIXED_NOW,
      acknowledged_at: null,
      severity: rule.severity,
      metric: rule.metric,
      operator: rule.operator,
      threshold: rule.threshold,
      value,
      source: "opend",
      provider_time: "2026-07-28T14:30:04-04:00",
      received_at: FIXED_NOW,
      snapshot: structuredClone(
        this.quotes.get(rule.code) ?? optionContract(rule.code),
      ),
      underlying_code: text(rule.underlying_code) || rule.code,
    };
    this.alerts.set(id, alert);
    return structuredClone(alert);
  }

  assertNoUnhandledRequests(): void {
    expect(this.unhandled, "all /api requests must be declared by the mock").toEqual([]);
  }

  private async handle(route: Route): Promise<void> {
    const request = route.request();
    const method = request.method().toUpperCase();
    const url = new URL(request.url());
    const path = url.pathname;
    if (!path.startsWith("/api/")) {
      await route.continue();
      return;
    }
    this.bump(method, path);

    if (method === "GET" && path === "/api/health") {
      await json(route, 200, {
        status: "ok",
        opend: {
          connected: this.connected,
          host: "127.0.0.1",
          port: 11111,
        },
      });
      return;
    }
    if (method === "GET" && path === "/api/config") {
      await json(route, 200, {
        strategies: [],
        kline_types: ["K_DAY", "K_5M"],
        adjustment_types: ["QFQ", "HFQ", "NONE"],
        session_types: ["ALL", "RTH", "ETH"],
      });
      return;
    }
    if (method === "GET" && path === "/api/strategies") {
      await json(route, 200, { strategies: [] });
      return;
    }
    if (method === "GET" && path === "/api/diagnostics") {
      await json(route, 200, systemDiagnostics(this.connected));
      return;
    }
    if (method === "GET" && path === "/api/symbols") {
      const query = (url.searchParams.get("q") ?? "").trim().toLowerCase();
      const limit = Number(url.searchParams.get("limit") ?? 8);
      const symbols = SYMBOLS.filter((symbol) =>
        `${symbol.code} ${symbol.name}`.toLowerCase().includes(query)
      ).slice(0, limit);
      await json(route, 200, { symbols });
      return;
    }
    if (method === "GET" && path === "/api/monitoring/status") {
      await json(route, 200, this.status());
      return;
    }
    if (method === "GET" && path === "/api/monitoring/diagnostics") {
      await json(route, 200, {
        ready: this.connected,
        checks: [
          {
            id: "opend",
            status: this.connected ? "pass" : "fail",
            detail: this.connected
              ? "OpenD monitoring RPC readable"
              : "OpenD monitoring RPC unavailable",
            hint: this.connected ? null : "Start OpenD and retry.",
          },
          {
            id: "us_options",
            status: "pass",
            detail: "US option chain readable",
            hint: null,
          },
        ],
      });
      return;
    }
    if (path === "/api/monitoring/watchlist") {
      await this.handleWatchlistCollection(route, method);
      return;
    }

    const watchlistCode = pathParameter(
      path,
      /^\/api\/monitoring\/watchlist\/([^/]+)$/,
    );
    if (watchlistCode) {
      await this.handleWatchlistItem(route, method, watchlistCode);
      return;
    }

    const snapshotCode = pathParameter(
      path,
      /^\/api\/monitoring\/underlyings\/([^/]+)\/snapshot$/,
    );
    if (method === "GET" && snapshotCode) {
      if (await this.fulfillMarketDataError(route, "monitor_snapshot_not_found")) return;
      await json(route, 200, this.snapshotResponse(snapshotCode));
      return;
    }

    const barsCode = pathParameter(
      path,
      /^\/api\/monitoring\/underlyings\/([^/]+)\/bars$/,
    );
    if (method === "GET" && barsCode) {
      if (await this.fulfillMarketDataError(route, "monitor_bars_not_found")) return;
      const count = Number(url.searchParams.get("count") ?? 120);
      const ktype = url.searchParams.get("ktype") ?? "K_5M";
      await json(route, 200, {
        code: barsCode,
        ktype,
        bars: monitorBars(barsCode, Math.min(count, 12), ktype),
      });
      return;
    }

    const expirationsCode = pathParameter(
      path,
      /^\/api\/monitoring\/underlyings\/([^/]+)\/option-expirations$/,
    );
    if (method === "GET" && expirationsCode) {
      if (await this.fulfillMarketDataError(route, "option_expirations_not_found")) return;
      await json(route, 200, {
        underlying: expirationsCode,
        expirations: EXPIRATIONS,
        fetched_at: FIXED_NOW,
      });
      return;
    }

    const chainCode = pathParameter(
      path,
      /^\/api\/monitoring\/underlyings\/([^/]+)\/option-chain$/,
    );
    if (method === "GET" && chainCode) {
      if (await this.fulfillMarketDataError(route, "option_chain_not_found")) return;
      const expiration =
        url.searchParams.get("expiration") ?? EXPIRATIONS[0].expiration;
      await json(route, 200, optionChain(chainCode, expiration));
      return;
    }

    const contractCode = pathParameter(
      path,
      /^\/api\/monitoring\/contracts\/([^/]+)$/,
    );
    if (method === "GET" && contractCode) {
      if (await this.fulfillMarketDataError(route, "option_contract_not_found")) return;
      await json(route, 200, {
        contract: optionContract(contractCode),
        analytics: {
          volatility_history: [
            { time: "2026-07-25", value: 27.1 },
            { time: "2026-07-28", value: 28.4 },
          ],
          exercise_probability_history: [
            { time: "2026-07-28", value: 0.42 },
          ],
        },
        freshness: this.freshness(),
      });
      return;
    }

    if (path === "/api/monitoring/rules") {
      await this.handleRulesCollection(route, method, url);
      return;
    }
    const ruleId = pathParameter(
      path,
      /^\/api\/monitoring\/rules\/([^/]+)$/,
    );
    if (ruleId) {
      await this.handleRule(route, method, ruleId);
      return;
    }

    if (method === "GET" && path === "/api/monitoring/alerts") {
      const code = url.searchParams.get("code");
      const underlyingCode = url.searchParams.get("underlying_code");
      const unacknowledgedOnly =
        url.searchParams.get("unacknowledged_only") === "true";
      const alerts = [...this.alerts.values()].filter(
        (alert) =>
          (!code || alert.code === normalizeCode(code))
          && (
            !underlyingCode
            || text(alert.underlying_code) === normalizeCode(underlyingCode)
          )
          && (!unacknowledgedOnly || alert.acknowledged_at === null),
      );
      await json(route, 200, {
        alerts: alerts.reverse(),
        next_cursor: null,
      });
      return;
    }
    const alertId = pathParameter(
      path,
      /^\/api\/monitoring\/alerts\/([^/]+)\/ack$/,
    );
    if (method === "POST" && alertId) {
      const alert = this.alerts.get(alertId);
      if (!alert) {
        await apiError(route, 404, "monitor_alert_not_found", alertId);
        return;
      }
      const acknowledged = {
        ...alert,
        acknowledged_at: FIXED_NOW,
      };
      this.alerts.set(alertId, acknowledged);
      await json(route, 200, acknowledged);
      return;
    }

    const requestDescription = `${method} ${url.pathname}${url.search}`;
    this.unhandled.push(requestDescription);
    await json(route, 501, {
      error: {
        code: "unmocked_e2e_endpoint",
        message: `Unmocked E2E endpoint: ${requestDescription}`,
        details: null,
      },
    });
  }

  private async handleWatchlistCollection(
    route: Route,
    method: string,
  ): Promise<void> {
    if (method === "GET") {
      await json(route, 200, {
        instruments: [...this.instruments.values()].map((instrument) =>
          this.refreshInstrument(instrument)
        ),
      });
      return;
    }
    if (method === "POST") {
      const payload = postDataObject(route);
      const code = normalizeCode(text(payload.code));
      const instrument = this.makeInstrument(
        code,
        payload.enabled !== false,
        text(payload.name) || code,
      );
      this.instruments.set(code, instrument);
      await json(route, 201, instrument);
      return;
    }
    await this.methodNotAllowed(route, method, "/api/monitoring/watchlist");
  }

  private async handleWatchlistItem(
    route: Route,
    method: string,
    code: string,
  ): Promise<void> {
    const existing = this.instruments.get(code);
    if (!existing) {
      await apiError(route, 404, "monitor_instrument_not_found", code);
      return;
    }
    if (method === "PATCH") {
      const payload = postDataObject(route);
      const updated: MonitoredInstrument = {
        ...existing,
        name: text(payload.name) || existing.name,
        enabled:
          typeof payload.enabled === "boolean"
            ? payload.enabled
            : existing.enabled,
        updated_at: FIXED_NOW,
      };
      this.instruments.set(code, updated);
      await json(route, 200, this.refreshInstrument(updated));
      return;
    }
    if (method === "DELETE") {
      this.instruments.delete(code);
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    await this.methodNotAllowed(route, method, `/api/monitoring/watchlist/${code}`);
  }

  private async handleRulesCollection(
    route: Route,
    method: string,
    url: URL,
  ): Promise<void> {
    if (method === "GET") {
      const code = url.searchParams.get("code");
      const underlyingCode = url.searchParams.get("underlying_code");
      const enabled = url.searchParams.get("enabled");
      const rules = [...this.rules.values()].filter(
        (rule) =>
          (!code || rule.code === normalizeCode(code))
          && (
            !underlyingCode
            || text(rule.underlying_code) === normalizeCode(underlyingCode)
          )
          && (
            enabled === null
            || rule.enabled === (enabled === "true")
          ),
      );
      await json(route, 200, { rules });
      return;
    }
    if (method === "POST") {
      const payload = postDataObject(route);
      const id = `rule-${this.nextRuleId++}`;
      const code = normalizeCode(text(payload.code));
      const instrumentType =
        payload.instrument_type === "option" ? "option" : "stock";
      const rule: MonitorRule = {
        id,
        name: text(payload.name),
        code,
        underlying_code:
          normalizeCode(text(payload.underlying_code))
          || (instrumentType === "option" && code.startsWith("US.AAPL")
            ? "US.AAPL"
            : code),
        instrument_type: instrumentType,
        metric: ruleMetric(payload.metric),
        operator: ruleOperator(payload.operator),
        threshold: finiteNumber(payload.threshold, 0),
        severity: ruleSeverity(payload.severity),
        cooldown_seconds: finiteNumber(payload.cooldown_seconds, 300),
        daily_trigger_limit: finiteNumber(payload.daily_trigger_limit, 10),
        session: ruleSession(payload.session),
        enabled: payload.enabled !== false,
        created_at: FIXED_NOW,
        updated_at: FIXED_NOW,
      };
      this.rules.set(id, rule);
      await json(route, 201, rule);
      return;
    }
    await this.methodNotAllowed(route, method, "/api/monitoring/rules");
  }

  private async handleRule(
    route: Route,
    method: string,
    id: string,
  ): Promise<void> {
    const existing = this.rules.get(id);
    if (!existing) {
      await apiError(route, 404, "monitor_rule_not_found", id);
      return;
    }
    if (method === "PATCH") {
      const payload = postDataObject(route);
      const updated: MonitorRule = {
        ...existing,
        enabled:
          typeof payload.enabled === "boolean"
            ? payload.enabled
            : existing.enabled,
        updated_at: FIXED_NOW,
      };
      this.rules.set(id, updated);
      await json(route, 200, updated);
      return;
    }
    if (method === "DELETE") {
      this.rules.delete(id);
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    await this.methodNotAllowed(route, method, `/api/monitoring/rules/${id}`);
  }

  private status(): JsonObject {
    return {
      phase: this.connected ? "ready" : "stopped",
      rules_paused: !this.connected,
      last_success_at: this.connected ? FIXED_NOW : null,
      last_error: this.connected ? null : "OpenD is unavailable",
      market_states: {
        us: this.marketDataMode === "market_closed" ? "CLOSED" : "MORNING",
        hk: this.marketDataMode === "market_closed" ? "CLOSED" : "AFTERNOON",
      },
      generic_subscription_budget: {
        generic_limit: 300,
        generic_used: this.instruments.size,
        generic_remaining: 300 - this.instruments.size,
      },
      freshness: Object.fromEntries(
        [...this.instruments.keys()].map((code) => [code, this.freshness()]),
      ),
    };
  }

  private snapshotResponse(code: string): JsonObject {
    const quote =
      this.quotes.get(code)
      ?? (code.startsWith("US.AAPL") ? optionContract(code) : stockQuote(code));
    return {
      snapshot: structuredClone(quote),
      freshness: this.freshness(),
      market_state:
        this.marketDataMode === "market_closed" ? "CLOSED" : "MORNING",
      age_seconds: this.marketDataMode === "stale" ? 180 : 1,
    };
  }

  private freshness(): "live" | "stale" | "market_closed" | "unavailable" {
    if (this.marketDataMode === "stale") return "stale";
    if (this.marketDataMode === "market_closed") return "market_closed";
    if (this.marketDataMode === "unavailable") return "unavailable";
    return "live";
  }

  private makeInstrument(
    code: string,
    enabled: boolean,
    name?: string,
  ): MonitoredInstrument {
    const symbol = SYMBOLS.find((candidate) => candidate.code === code);
    return {
      code,
      name: name || symbol?.name || code,
      market: code.split(".", 1)[0],
      instrument_type: "stock",
      underlying_code: null,
      enabled,
      created_at: FIXED_NOW,
      updated_at: FIXED_NOW,
      snapshot: structuredClone(this.quotes.get(code) ?? stockQuote(code)),
      freshness: this.freshness(),
    };
  }

  private refreshInstrument(
    instrument: MonitoredInstrument,
  ): MonitoredInstrument {
    return {
      ...instrument,
      snapshot: structuredClone(
        this.quotes.get(instrument.code) ?? instrument.snapshot ?? null,
      ),
      freshness: this.freshness(),
    };
  }

  private async fulfillMarketDataError(
    route: Route,
    notFoundCode: string,
  ): Promise<boolean> {
    if (this.marketDataMode === "permission") {
      await apiError(
        route,
        403,
        "market_data_permission_denied",
        "The account has no permission for this quote.",
      );
      return true;
    }
    if (this.marketDataMode === "quota") {
      await apiError(
        route,
        503,
        "market_data_quota_exhausted",
        "OpenD subscription quota is exhausted.",
      );
      return true;
    }
    if (this.marketDataMode === "offline") {
      await apiError(
        route,
        503,
        "opend_unavailable",
        "OpenD is unavailable.",
      );
      return true;
    }
    if (this.marketDataMode === "unavailable") {
      await apiError(route, 404, notFoundCode, "No market data was returned.");
      return true;
    }
    return false;
  }

  private bump(method: string, path: string): void {
    const key = requestKey(method, path);
    this.requestCounts.set(key, (this.requestCounts.get(key) ?? 0) + 1);
  }

  private async methodNotAllowed(
    route: Route,
    method: string,
    path: string,
  ): Promise<void> {
    const description = `${method} ${path}`;
    this.unhandled.push(description);
    await json(route, 405, {
      error: {
        code: "method_not_mocked",
        message: `Method not mocked: ${description}`,
        details: null,
      },
    });
  }
}

export async function setupMonitoringMock(
  page: Page,
  options: MonitoringMockOptions = {},
): Promise<MonitoringApiMock> {
  const mock = new MonitoringApiMock(options);
  await mock.install(page, options.locale ?? "en-US");
  return mock;
}

function stockQuote(code: string): JsonObject {
  const isHongKong = code.startsWith("HK.");
  const lastPrice = isHongKong ? 500.8 : 201.25;
  const previousClose = isHongKong ? 496.0 : 198.5;
  return {
    code,
    name: isHongKong ? "Tencent Holdings / 腾讯控股" : "Apple Inc. / 苹果",
    instrument_type: "stock",
    source: "opend",
    source_time: isHongKong
      ? "2026-07-29T02:30:04Z"
      : "2026-07-28T18:30:04Z",
    fetched_at: FIXED_NOW,
    last_price: lastPrice,
    previous_close: previousClose,
    change_rate: ((lastPrice - previousClose) / previousClose) * 100,
    open_price: previousClose + 0.5,
    high_price: lastPrice + 1.75,
    low_price: previousClose - 1.25,
    bid_price: lastPrice - 0.05,
    ask_price: lastPrice + 0.05,
    volume: isHongKong ? 8_230_000 : 36_420_000,
    turnover: isHongKong ? 4_121_000_000 : 7_329_000_000,
    turnover_rate: isHongKong ? 0.31 : 0.74,
    amplitude: isHongKong ? 1.8 : 2.4,
    volume_ratio: isHongKong ? 1.1 : 1.35,
    lot_size: isHongKong ? 100 : 1,
  };
}

function monitorBars(code: string, count: number, ktype: string): JsonObject[] {
  const base = code.startsWith("HK.") ? 500 : 198;
  return Array.from({ length: count }, (_, index) => {
    const open = base + index * 0.35;
    const close = open + (index % 2 === 0 ? 0.7 : -0.25);
    return {
      code,
      source_time: `2026-07-28T${String(13 + Math.floor(index / 6)).padStart(2, "0")}:${String((index % 6) * 5).padStart(2, "0")}:00-04:00`,
      ktype,
      open,
      high: Math.max(open, close) + 0.4,
      low: Math.min(open, close) - 0.35,
      close,
      volume: 10_000 + index * 750,
      is_closed: index < count - 1,
    };
  });
}

function optionChain(underlying: string, expiration: string): JsonObject {
  const contracts = [
    optionContract(CONTRACTS.call195, { strike_price: 195, option_type: "CALL" }),
    optionContract(CONTRACTS.put195, { strike_price: 195, option_type: "PUT" }),
    optionContract(CONTRACTS.call200, { strike_price: 200, option_type: "CALL" }),
    optionContract(CONTRACTS.put200, { strike_price: 200, option_type: "PUT" }),
    optionContract(CONTRACTS.call205, {
      strike_price: 205,
      option_type: "CALL",
      ask_price: null,
      option_implied_volatility: null,
    }),
  ].map((contract) => ({
    ...contract,
    underlying_code: underlying,
    expiration,
  }));
  return {
    underlying,
    expiration,
    underlying_snapshot: stockQuote(underlying),
    contracts,
    summary: {
      call_put_volume_ratio: 1.2,
      call_put_open_interest_ratio: 0.85,
    },
    fetched_at: FIXED_NOW,
    source: "opend",
  };
}

function optionContract(
  code: string,
  patch: JsonObject = {},
): JsonObject {
  const put = code.match(/\d{6}([CP])/)?.[1] === "P";
  const strikeMatch = code.match(/[CP](\d{3})000$/);
  const strike = strikeMatch ? Number(strikeMatch[1]) : 200;
  const lastPrice = Math.max(0.5, Math.abs(201.25 - strike) + 3.2);
  return {
    code,
    name: `AAPL 2026-08-07 ${put ? "Put" : "Call"} ${strike}`,
    underlying_code: "US.AAPL",
    instrument_type: "option",
    source: "opend",
    source_time: "2026-07-28T18:30:04Z",
    fetched_at: FIXED_NOW,
    option_type: put ? "PUT" : "CALL",
    expiration: "2026-08-07",
    strike_price: strike,
    lot_size: 100,
    option_contract_size: 100,
    expiration_cycle: "WEEK",
    standard_type: "STANDARD",
    settlement_mode: "PHYSICAL",
    days_to_expiry: 10,
    last_price: lastPrice,
    previous_close: lastPrice - 0.2,
    bid_price: lastPrice - 0.05,
    ask_price: lastPrice + 0.05,
    volume: put ? 830 : 1_250,
    turnover: lastPrice * (put ? 830 : 1_250),
    option_open_interest: put ? 4_300 : 5_200,
    option_net_open_interest: put ? 3_900 : 4_850,
    option_implied_volatility: put ? 31.2 : 28.4,
    option_premium: put ? 0.8 : 1.1,
    option_delta: put ? -0.46 : 0.54,
    option_gamma: 0.0312,
    option_vega: 0.118,
    option_theta: -0.084,
    option_rho: null,
    mid_price: lastPrice,
    bid_ask_spread: 0.1,
    bid_ask_spread_pct: (0.1 / lastPrice) * 100,
    volume_open_interest_ratio:
      (put ? 830 : 1_250) / (put ? 4_300 : 5_200),
    ...patch,
  };
}

function systemDiagnostics(connected: boolean): JsonObject {
  return {
    ready: connected,
    host: "127.0.0.1",
    port: 11111,
    checks: [
      { id: "python", status: "pass", detail: "Python ready", hint: null },
      { id: "futu_api", status: "pass", detail: "futu-api ready", hint: null },
      { id: "workspace", status: "pass", detail: "workspace ready", hint: null },
      {
        id: "opend",
        status: connected ? "pass" : "fail",
        detail: connected ? "OpenD TCP reachable" : "OpenD TCP unavailable",
        hint: connected ? null : "Start OpenD.",
      },
      {
        id: "quote_directory",
        status: connected ? "pass" : "blocked",
        detail: connected ? "OpenD stock directory readable" : "OpenD required",
        hint: connected ? null : "Connect OpenD.",
      },
    ],
  };
}

function pathParameter(path: string, pattern: RegExp): string | null {
  const match = path.match(pattern);
  return match ? decodeURIComponent(match[1]) : null;
}

function requestKey(method: string, pathname: string): string {
  return `${method.toUpperCase()} ${pathname}`;
}

function normalizeCode(value: string): string {
  return value.trim().toUpperCase();
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function finiteNumber(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : fallback;
}

function postDataObject(route: Route): JsonObject {
  const payload: unknown = route.request().postDataJSON();
  return payload && typeof payload === "object"
    ? payload as JsonObject
    : {};
}

function ruleMetric(value: unknown): MonitorRule["metric"] {
  return text(value) as MonitorRule["metric"];
}

function ruleOperator(value: unknown): MonitorRule["operator"] {
  const candidate = text(value);
  if (
    candidate === "above"
    || candidate === "below"
    || candidate === "crosses_below"
  ) {
    return candidate;
  }
  return "crosses_above";
}

function ruleSeverity(value: unknown): MonitorRule["severity"] {
  const candidate = text(value);
  if (candidate === "info" || candidate === "critical") return candidate;
  return "warning";
}

function ruleSession(value: unknown): MonitorRule["session"] {
  const candidate = text(value);
  if (candidate === "extended" || candidate === "all") return candidate;
  return "regular";
}

async function json(
  route: Route,
  status: number,
  payload: unknown,
): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}

async function apiError(
  route: Route,
  status: number,
  code: string,
  message: string,
): Promise<void> {
  await json(route, status, {
    error: {
      code,
      message,
      details: null,
    },
  });
}
