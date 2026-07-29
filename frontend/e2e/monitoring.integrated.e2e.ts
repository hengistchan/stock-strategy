import { expect, test, type Locator, type Page, type Request } from "@playwright/test";

const US_STOCK = "US.AAPL";
const HK_STOCK = "HK.00700";
const US_CALL = "US.AAPL260807C100000";
const US_PUT = "US.AAPL260807P100000";
const EXPIRATION = "2026-08-07";
const EXPECTED_OWNED_CODES = [HK_STOCK, US_STOCK, US_CALL];

interface FixtureGatewayEvidence {
  owned_codes: string[];
  external_codes: string[];
  subscribe_calls: string[][];
  unsubscribe_calls: string[][];
  close_calls: number;
  closed: boolean;
}

interface FixtureState {
  scenario: string;
  state_path: string;
  restart_count: number;
  watchlist_count: number;
  rule_count: number;
  alert_count: number;
  gateway: FixtureGatewayEvidence;
  retired_gateways: FixtureGatewayEvidence[];
}

interface MonitorRuleRecord {
  id: string;
  name: string;
  code: string;
  metric: string;
  last_value: number | null;
}

interface MonitorAlertRecord {
  id: string;
  rule_name: string;
  code: string;
  metric: string;
  acknowledged_at: string | null;
}

interface BrowserFault {
  kind: "console.error" | "pageerror" | "requestfailed";
  message: string;
}

test("runs the durable stock and option monitoring journey against the production app", async ({
  page,
}) => {
  const browserFaults: BrowserFault[] = [];
  let intentionalReload = false;
  const alertResponseTimes: number[] = [];

  page.on("console", (message) => {
    if (message.type() === "error") {
      browserFaults.push({
        kind: "console.error",
        message: message.text(),
      });
    }
  });
  page.on("pageerror", (error) => {
    browserFaults.push({ kind: "pageerror", message: error.message });
  });
  page.on("requestfailed", (request) => {
    if (isExpectedEventStreamAbort(request, intentionalReload)) return;
    browserFaults.push({
      kind: "requestfailed",
      message: `${request.method()} ${request.url()} · ${
        request.failure()?.errorText ?? "unknown failure"
      }`,
    });
  });
  page.on("response", (response) => {
    const url = new URL(response.url());
    if (
      response.request().method() === "GET"
      && url.pathname === "/api/monitoring/alerts"
      && response.status() === 200
    ) {
      alertResponseTimes.push(Date.now());
    }
  });

  await page.addInitScript(() => {
    window.localStorage.setItem("strategy-lab.locale", "en-US");
  });

  await page.goto("/monitors");
  await expect(
    page.getByRole("heading", { name: "Stock and option monitoring" }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Start monitoring with one symbol" }),
  ).toBeVisible();
  await expect(page.getByText("No monitored symbols yet.")).toBeVisible();

  await addWatchlistSymbol(page, US_STOCK);
  await expect(page).toHaveURL(new RegExp(`/monitors/${escapeRegExp(US_STOCK)}$`));
  await expect(page.locator(".monitor-last-price")).toContainText("99.00");
  await expect(
    page.getByRole("img", {
      name: new RegExp(
        `${escapeRegExp(US_STOCK)}'s latest 120 OpenD five-minute OHLCV bars`,
      ),
    }),
  ).toBeVisible();

  await addWatchlistSymbol(page, HK_STOCK);
  await expect(page).toHaveURL(new RegExp(`/monitors/${escapeRegExp(HK_STOCK)}$`));
  await expect(page.locator(".monitor-last-price")).toContainText("500.00");
  await expect(
    page.getByRole("img", {
      name: new RegExp(
        `${escapeRegExp(HK_STOCK)}'s latest 120 OpenD five-minute OHLCV bars`,
      ),
    }),
  ).toBeVisible();

  await watchlistLink(page, US_STOCK).click();
  await expect(page).toHaveURL(new RegExp(`/monitors/${escapeRegExp(US_STOCK)}$`));
  await page.getByRole("link", { name: "Option chain" }).last().click();
  await expect(page).toHaveURL(
    new RegExp(`/monitors/${escapeRegExp(US_STOCK)}/options$`),
  );
  await expect(
    page.getByRole("heading", { name: "Option chain desk" }),
  ).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "Expiration" }),
  ).toHaveValue(EXPIRATION);
  const chain = page.getByRole("table", {
    name: new RegExp(
      `${escapeRegExp(US_STOCK)} ${EXPIRATION} Call｜Strike｜Put option chain`,
    ),
  });
  await expect(chain).toBeVisible();
  await expect(
    chain.getByRole("button", {
      name: new RegExp(escapeRegExp(US_CALL)),
    }),
  ).toBeVisible();
  await expect(
    chain.getByRole("button", {
      name: new RegExp(escapeRegExp(US_PUT)),
    }),
  ).toBeVisible();

  await chain
    .getByRole("button", { name: new RegExp(escapeRegExp(US_CALL)) })
    .click();
  const contractDialog = page.getByRole("dialog");
  await expect(contractDialog).toBeVisible();
  await expect(
    contractDialog.getByRole("heading", { name: "Complete Greeks" }),
  ).toBeVisible();
  await expect(definitionValue(contractDialog, "DELTA")).toHaveText("0.5000");
  await expect(definitionValue(contractDialog, "GAMMA")).toHaveText("0.0800");
  await expect(definitionValue(contractDialog, "VEGA")).toHaveText("0.1200");
  await expect(definitionValue(contractDialog, "THETA")).toHaveText("-0.1600");
  await expect(definitionValue(contractDialog, "RHO")).toHaveText("0.0300");
  await expect(
    contractDialog.getByText("Open interest (daily as-of)", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close contract details" }).click();
  await expect(contractDialog).toBeHidden();

  await page.getByRole("link", { name: "Rules & alerts" }).last().click();
  await expect(page).toHaveURL(
    new RegExp(`/monitors/${escapeRegExp(US_STOCK)}/alerts$`),
  );

  await createRule(page, {
    name: "Apple crosses 100",
    threshold: "100",
    advanced: true,
  });
  await expect(
    page.locator(".monitor-rule-ledger li").filter({
      hasText: "Apple crosses 100",
    }),
  ).toBeVisible();

  await createRule(page, {
    name: "Apple call IV crosses 30",
    threshold: "30",
    instrumentType: "option",
    code: US_CALL,
    metric: "option_implied_volatility",
    severity: "critical",
  });
  await expect(page.locator(".toast")).toContainText(
    "Rule “Apple call IV crosses 30” was created.",
  );
  await expect(
    page.locator(".monitor-rule-ledger li").filter({
      hasText: "Apple call IV crosses 30",
    }),
  ).toBeVisible();

  const createdState = await fixtureState(page);
  expect(createdState.watchlist_count).toBe(2);
  expect(createdState.rule_count).toBe(2);
  expect(createdState.alert_count).toBe(0);

  const baseline = await fixtureControl(page, "scenario/baseline");
  expect(baseline.alert_count).toBe(0);
  const baselineRules = await productionRules(page);
  expect(ruleByMetric(baselineRules, "last_price").last_value).toBe(99);
  expect(
    ruleByMetric(baselineRules, "option_implied_volatility").last_value,
  ).toBe(25);

  // Observe a scheduled five-second poll, then trigger the edge immediately.
  // The next scheduled poll is five seconds away, so a fetch inside two seconds
  // demonstrates that monitor.alert.triggered invalidated the durable REST query.
  const alertFetchesBeforePoll = alertResponseTimes.length;
  await expect
    .poll(() => alertResponseTimes.length, {
      timeout: 7_000,
      message: "the alert ledger should complete its scheduled five-second poll",
    })
    .toBeGreaterThan(alertFetchesBeforePoll);
  await expect(page.getByText("No alerts match the current filter.")).toBeVisible();

  const alertFetchesBeforeEdge = alertResponseTimes.length;
  const edgeStartedAt = Date.now();
  const firstEdge = await fixtureControl(page, "scenario/edge");
  expect(firstEdge.alert_count).toBe(2);
  await expect
    .poll(() => alertResponseTimes.length, {
      timeout: 2_000,
      message:
        "monitor.alert.triggered SSE should refresh alerts before the 5s poll",
    })
    .toBeGreaterThan(alertFetchesBeforeEdge);
  const firstSseRefreshAt = alertResponseTimes[alertFetchesBeforeEdge];
  expect(firstSseRefreshAt - edgeStartedAt).toBeLessThan(5_000);

  const stockAlert = page.locator(".monitor-alert-ledger li").filter({
    hasText: "Apple crosses 100",
  });
  const optionAlert = page.locator(".monitor-alert-ledger li").filter({
    hasText: "Apple call IV crosses 30",
  });
  await expect(stockAlert).toBeVisible();
  await expect(optionAlert).toBeVisible();
  await expect(stockAlert).toContainText("Observed 101.0000");
  await expect(optionAlert).toContainText("Observed 35.0000");
  await stockAlert.getByRole("button", { name: "Acknowledge" }).click();
  await expect(stockAlert).toContainText("Acknowledged at");

  const acknowledgedBeforeRestart = await productionAlerts(page);
  expect(acknowledgedBeforeRestart).toHaveLength(2);
  expect(
    acknowledgedBeforeRestart.filter((alert) => alert.acknowledged_at !== null),
  ).toHaveLength(1);

  const restarted = await fixtureControl(page, "restart");
  expect(restarted.restart_count).toBe(1);
  expect(restarted.watchlist_count).toBe(2);
  expect(restarted.rule_count).toBe(2);
  expect(restarted.alert_count).toBe(2);
  assertExactSubscriptionCleanup(restarted.retired_gateways[0]);

  intentionalReload = true;
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(
    page.getByRole("heading", { name: "Create a durable monitoring rule" }),
  ).toBeVisible();
  await expect(watchlistLink(page, US_STOCK)).toBeVisible();
  await expect(watchlistLink(page, HK_STOCK)).toBeVisible();
  await expect(
    page.locator(".monitor-rule-ledger li").filter({
      hasText: "Apple crosses 100",
    }),
  ).toBeVisible();
  await expect(
    page.locator(".monitor-rule-ledger li").filter({
      hasText: "Apple call IV crosses 30",
    }),
  ).toBeVisible();
  const persistedStockAlert = page.locator(".monitor-alert-ledger li").filter({
    hasText: "Apple crosses 100",
  });
  const persistedOptionAlert = page.locator(".monitor-alert-ledger li").filter({
    hasText: "Apple call IV crosses 30",
  });
  await expect(persistedStockAlert).toContainText("Acknowledged at");
  await expect(persistedOptionAlert).toBeVisible();
  await expect(persistedOptionAlert).not.toContainText("Acknowledged at");
  intentionalReload = false;

  const persistedRules = await productionRules(page);
  expect(
    persistedRules.map((rule) => [rule.code, rule.metric]).sort(),
  ).toEqual(
    [
      [US_STOCK, "last_price"],
      [US_CALL, "option_implied_volatility"],
    ].sort(),
  );
  const persistedAlerts = await productionAlerts(page);
  expect(persistedAlerts).toHaveLength(2);
  expect(
    persistedAlerts.filter((alert) => alert.acknowledged_at !== null),
  ).toHaveLength(1);
  expect((await fixtureState(page)).alert_count).toBe(2);

  const reset = await fixtureControl(page, "scenario/reset");
  expect(reset.alert_count).toBe(2);
  const alertFetchesBeforeSecondEdge = alertResponseTimes.length;
  const secondEdge = await fixtureControl(page, "scenario/edge");
  expect(secondEdge.alert_count).toBe(4);
  await expect
    .poll(() => alertResponseTimes.length, { timeout: 2_000 })
    .toBeGreaterThan(alertFetchesBeforeSecondEdge);
  await expect(
    page.locator(".monitor-alert-ledger li").filter({
      hasText: "Apple crosses 100",
    }),
  ).toHaveCount(2);
  await expect(
    page.locator(".monitor-alert-ledger li").filter({
      hasText: "Apple call IV crosses 30",
    }),
  ).toHaveCount(2);

  const finalRestart = await fixtureControl(page, "restart");
  expect(finalRestart.restart_count).toBe(2);
  expect(finalRestart.alert_count).toBe(4);
  expect(finalRestart.retired_gateways).toHaveLength(2);
  assertExactSubscriptionCleanup(finalRestart.retired_gateways[1]);

  expect(
    browserFaults,
    browserFaults.map((fault) => `${fault.kind}: ${fault.message}`).join("\n"),
  ).toEqual([]);
});

async function addWatchlistSymbol(page: Page, code: string): Promise<void> {
  const search = page.getByRole("combobox", {
    name: "Add a monitored symbol",
  });
  await search.fill(code);
  await search.press("Enter");
  await expect(watchlistLink(page, code)).toBeVisible();
}

async function createRule(
  page: Page,
  options: {
    name: string;
    threshold: string;
    instrumentType?: "stock" | "option";
    code?: string;
    metric?: string;
    severity?: "info" | "warning" | "critical";
    advanced?: boolean;
  },
): Promise<void> {
  await page.getByRole("textbox", { name: "Rule name" }).fill(options.name);
  if (options.instrumentType) {
    await page
      .getByRole("combobox", { name: "Instrument" })
      .selectOption(options.instrumentType);
  }
  if (options.code) {
    await page.getByRole("textbox", { name: "Futu code" }).fill(options.code);
  }
  if (options.metric) {
    await page
      .getByRole("combobox", { name: "Metric" })
      .selectOption(options.metric);
  }
  await page
    .getByRole("spinbutton", { name: "Threshold" })
    .fill(options.threshold);
  if (options.severity) {
    await page
      .getByRole("combobox", { name: "Severity" })
      .selectOption(options.severity);
  }
  if (options.advanced) {
    const advanced = page.getByText("Cooldown, frequency & session", {
      exact: true,
    });
    await advanced.click();
    await page
      .getByRole("spinbutton", { name: "Cooldown seconds" })
      .fill("0");
    await page
      .getByRole("spinbutton", { name: "Daily trigger limit" })
      .fill("10");
  }
  const responsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return (
      response.request().method() === "POST"
      && url.pathname === "/api/monitoring/rules"
    );
  });
  await page.getByRole("button", { name: "Create monitoring rule" }).click();
  const response = await responsePromise;
  expect(
    response.status(),
    `create rule ${options.name}: ${await response.text()}`,
  ).toBe(201);
}

function watchlistLink(page: Page, code: string): Locator {
  return page.getByRole("link", {
    name: new RegExp(escapeRegExp(code)),
  }).last();
}

function definitionValue(container: Locator, term: string): Locator {
  return container.locator("dl > div").filter({ hasText: term }).locator("dd");
}

async function fixtureControl(
  page: Page,
  path: string,
): Promise<FixtureState> {
  const response = await page.evaluate(async (controlPath) => {
    const result = await window.fetch(`/_test/monitoring/${controlPath}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    return {
      status: result.status,
      body: (await result.json()) as unknown,
    };
  }, path);
  expect(response.status, `fixture control ${path}`).toBe(200);
  return response.body as FixtureState;
}

async function fixtureState(page: Page): Promise<FixtureState> {
  return browserJson<FixtureState>(page, "/_test/monitoring/state");
}

async function productionRules(page: Page): Promise<MonitorRuleRecord[]> {
  const payload = await browserJson<{ rules: MonitorRuleRecord[] }>(
    page,
    "/api/monitoring/rules",
  );
  return payload.rules;
}

async function productionAlerts(page: Page): Promise<MonitorAlertRecord[]> {
  const payload = await browserJson<{ alerts: MonitorAlertRecord[] }>(
    page,
    "/api/monitoring/alerts?limit=100",
  );
  return payload.alerts;
}

async function browserJson<T>(page: Page, path: string): Promise<T> {
  const response = await page.evaluate(async (requestPath) => {
    const result = await window.fetch(requestPath);
    return {
      status: result.status,
      body: (await result.json()) as unknown,
    };
  }, path);
  expect(response.status, `GET ${path}`).toBe(200);
  return response.body as T;
}

function ruleByMetric(
  rules: MonitorRuleRecord[],
  metric: string,
): MonitorRuleRecord {
  const rule = rules.find((candidate) => candidate.metric === metric);
  expect(rule, `rule metric ${metric}`).toBeDefined();
  return rule as MonitorRuleRecord;
}

function assertExactSubscriptionCleanup(
  gateway: FixtureGatewayEvidence,
): void {
  expect(gateway.unsubscribe_calls).toEqual([EXPECTED_OWNED_CODES]);
  expect(gateway.owned_codes).toEqual([]);
  expect(gateway.external_codes).toEqual(["US.MSFT"]);
  expect(gateway.close_calls).toBe(1);
  expect(gateway.closed).toBe(true);
}

function isExpectedEventStreamAbort(
  request: Request,
  intentionalReload: boolean,
): boolean {
  if (!intentionalReload) return false;
  const failure = request.failure()?.errorText ?? "";
  return (
    new URL(request.url()).pathname === "/api/events"
    && /ERR_ABORTED|NS_BINDING_ABORTED|cancelled/i.test(failure)
  );
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
