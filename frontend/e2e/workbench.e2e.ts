import { expect, test, type Page } from "@playwright/test";

const strategy = {
  path: "examples/ma_cross.py",
  name: "Moving Average Cross",
  group: "示例策略",
  readonly: true,
  revision: "a".repeat(64),
  size: 2048,
  updated_at: "2026-07-19T10:00:00Z",
  parameters: [],
  compatibility: {
    supported: true,
    issues: [],
    unsupported_names: [],
    bar_types: ["K_DAY"],
    driver_bar_type: "K_DAY",
    session_types: ["ALL"],
    required_session: "ALL",
  },
};

const request = {
  strategy: strategy.path,
  symbol: "US.AAPL",
  start: "2025-01-01",
  end: "2025-12-31",
  ktype: "K_DAY",
  autype: "QFQ",
  session: "ALL",
  initial_cash: 100000,
  commission_bps: 3,
  min_commission: 1,
  slippage_bps: 5,
  warmup_bars: 0,
  allow_short: false,
  liquidate_on_end: false,
};

const job = {
  id: "e2e-run",
  status: "succeeded",
  created_at: "2026-07-19T10:00:00Z",
  started_at: "2026-07-19T10:00:01Z",
  finished_at: "2026-07-19T10:00:02Z",
  request,
  strategy_path: strategy.path,
  run_dir: "runs/e2e-run",
  stdout: "",
  stderr: "",
  error: null,
};

const result = {
  job,
  summary: {
    strategy: "ma_cross",
    symbol: "US.AAPL",
    period: { start: request.start, end: request.end, bars: 252 },
    settings: {
      engine_contract: {
        version: 3,
        strict_single_period: false,
        day_order_scope: "trading-day",
        end_position_policy: "mark-to-market",
      },
      opend: { ktype: "K_DAY", autype: "QFQ", session: "ALL", cache_path: "data/opend/cache/e2e.csv" },
      market_metadata: { name: "Apple Inc." },
    },
    metrics: {
      total_return_pct: 12.5,
      benchmark_return_pct: 9.2,
      max_drawdown_pct: -4.8,
      sharpe_ratio: 1.36,
      total_trades: 8,
      total_fees: 42.5,
      exposure_pct: 61,
    },
  },
  price_series: [],
  price_series_offset: 0,
  price_series_count: 0,
  price_overview: [],
  trades: [],
  equity_curve: [],
  equity_curve_count: 0,
  report_url: "/api/jobs/e2e-run/report.svg",
};

async function mockApi(page: Page) {
  await page.addInitScript(() => window.localStorage.setItem("strategy-lab.locale", "en-US"));
  await page.route("**/api/**", async (route) => {
    const requestUrl = new URL(route.request().url());
    const path = requestUrl.pathname;
    if (!path.startsWith("/api/")) {
      await route.continue();
      return;
    }
    let payload: unknown;
    if (path === "/api/health") {
      payload = { status: "ok", opend: { connected: true, host: "127.0.0.1", port: 11111 } };
    } else if (path === "/api/diagnostics") {
      payload = {
        ready: true,
        host: "127.0.0.1",
        port: 11111,
        checks: [
          { id: "python", status: "pass", detail: "Python 3.12.13", hint: null },
          { id: "futu_api", status: "pass", detail: "futu-api 10.6.6608", hint: null },
          { id: "workspace", status: "pass", detail: "workspace ready", hint: null },
          { id: "opend", status: "pass", detail: "OpenD TCP reachable", hint: null },
          { id: "quote_directory", status: "pass", detail: "OpenD stock directory readable", hint: null },
        ],
      };
    } else if (path === "/api/config") {
      payload = { strategies: [strategy], kline_types: ["K_DAY"], adjustment_types: ["QFQ", "HFQ", "NONE"], session_types: ["ALL", "RTH", "ETH"] };
    } else if (path === "/api/strategies") {
      payload = { strategies: [strategy] };
    } else if (path === "/api/strategies/examples/ma_cross.py") {
      payload = { ...strategy, content: "def initialize(context):\n    pass\n" };
    } else if (path === "/api/jobs") {
      payload = { jobs: [job] };
    } else if (path === "/api/jobs/e2e-run") {
      payload = job;
    } else if (path === "/api/jobs/e2e-run/result") {
      payload = result;
    } else if (path === "/api/jobs/e2e-run/prices") {
      payload = { offset: 0, total: 0, points: [] };
    } else if (path === "/api/symbols/resolve") {
      payload = { symbols: [{ code: "US.AAPL", name: "Apple Inc.", market: "US" }] };
    } else if (path === "/api/experiments") {
      payload = { experiments: [] };
    } else if (path === "/api/cache") {
      payload = { entries: [], total_bytes: 0 };
    } else {
      await route.fulfill({ status: 404, json: { detail: `Unmocked E2E endpoint: ${path}` } });
      return;
    }
    await route.fulfill({ status: 200, json: payload });
  });
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test("renders versioned backtest evidence on the stable backtests route", async ({ page }) => {
  await page.goto("/");

  await expect(page).toHaveURL(/\/backtests$/);
  await expect(page.getByText("OPEND CONTRACT V3")).toBeVisible();
  await expect(page.getByText("+12.50%")).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Symbols" })).toHaveValue("US.AAPL");
  await expect(page.locator(".result-symbol-name")).toHaveText("· Apple Inc.");
});

test("navigates workspaces and explains the real OpenD readiness state", async ({ page }) => {
  await page.goto("/backtests");
  await page.getByRole("button", { name: /OpenD connected/ }).click();

  const diagnostics = page.getByRole("region", { name: "System diagnostics" });
  await expect(diagnostics.getByText("Ready for OpenD stock backtests")).toBeVisible();
  await expect(diagnostics.getByText("OpenD stock directory readable")).toBeVisible();

  await page.getByRole("link", { name: /Experiments/ }).click();
  await expect(page).toHaveURL(/\/experiments$/);
  await expect(page.getByRole("heading", { name: "Parameter matrix" })).toBeVisible();

  await page.getByRole("link", { name: /Strategies/ }).click();
  await expect(page).toHaveURL(/\/strategies$/);
  await expect(page.getByRole("heading", { name: "Strategy repository" })).toBeVisible();
  await expect(page.getByText("Moving Average Cross")).toBeVisible();
});
