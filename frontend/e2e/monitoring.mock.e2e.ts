import { expect, test, type Locator, type Page } from "@playwright/test";
import {
  emitApiEvent,
  eventSourceUrls,
  waitForEventSource,
} from "./fixtures/fakeEventSource";
import {
  monitoringContracts,
  setupMonitoringMock,
  type MonitoringDataMode,
} from "./fixtures/monitoringApi";

const monitorTitle = /Stock and option monitoring|股票与期权监控/;

test("adds US and HK symbols with the keyboard, deduplicates, re-enables, and preserves a cancelled removal", async ({
  page,
}) => {
  const mock = await setupMonitoringMock(page);
  await openMonitor(page);

  const search = page.getByRole("combobox", { name: "Add a monitored symbol" });
  await search.fill("AAPL");
  const results = page.getByRole("listbox", {
    name: "OpenD symbol search results",
  });
  await expect(results).toBeVisible();
  await expect(results.getByRole("option", { name: /US\.AAPL/ })).toBeVisible();
  await search.press("ArrowDown");
  await expect(search).toHaveAttribute("aria-activedescendant", /results-0$/);
  await search.press("ArrowUp");
  await search.press("Enter");
  await expect(search).toHaveValue(/US\.AAPL/);
  await search.press("Enter");

  await expect(page).toHaveURL(/\/monitors\/US\.AAPL$/);
  await expect(watchlistLink(page, "US.AAPL")).toBeVisible();
  await expect(
    page.getByRole("status").filter({
      hasText: "US.AAPL was added to monitoring.",
    }),
  ).toBeVisible();

  await search.fill("Tencent");
  await expect(results).toBeVisible();
  await search.press("Escape");
  await expect(results).toBeHidden();
  await search.fill("HK.00700");
  await search.press("Enter");
  await expect(page).toHaveURL(/\/monitors\/HK\.00700$/);
  await expect(watchlistLink(page, "HK.00700")).toBeVisible();

  const deletesBeforeCancel = mock.requestCount(
    "DELETE",
    "/api/monitoring/watchlist/US.AAPL",
  );
  page.once("dialog", async (dialog) => {
    expect(dialog.type()).toBe("confirm");
    expect(dialog.message()).toContain("Remove US.AAPL");
    await dialog.dismiss();
  });
  await page.getByRole("button", { name: "Remove US.AAPL" }).click();
  await expect(watchlistLink(page, "US.AAPL")).toBeVisible();
  expect(
    mock.requestCount("DELETE", "/api/monitoring/watchlist/US.AAPL"),
  ).toBe(deletesBeforeCancel);

  await watchlistLink(page, "US.AAPL").click();
  await page.getByRole("button", {
    name: "Disable monitoring for US.AAPL",
  }).click();
  await expect(page.getByRole("button", {
    name: "Enable monitoring for US.AAPL",
  })).toBeVisible();

  const patchesBeforeReactivation = mock.requestCount(
    "PATCH",
    "/api/monitoring/watchlist/US.AAPL",
  );
  await search.fill("AAPL");
  await expect(results.getByRole("option", { name: /US\.AAPL/ })).toBeVisible();
  await search.press("Enter");
  await search.press("Enter");
  await expect.poll(() =>
    mock.requestCount("PATCH", "/api/monitoring/watchlist/US.AAPL")
  ).toBe(patchesBeforeReactivation + 1);
  await expect(page.getByRole("button", {
    name: "Disable monitoring for US.AAPL",
  })).toBeVisible();
  await expect(
    page.getByRole("status").filter({
      hasText: "US.AAPL is already in the watchlist and has been opened.",
    }),
  ).toBeVisible();

  const writesBeforeDuplicate =
    mock.requestCount("POST", "/api/monitoring/watchlist")
    + mock.requestCount("PATCH", "/api/monitoring/watchlist/US.AAPL");
  await search.fill("US.AAPL");
  await search.press("Enter");
  await expect.poll(() =>
    mock.requestCount("POST", "/api/monitoring/watchlist")
    + mock.requestCount("PATCH", "/api/monitoring/watchlist/US.AAPL")
  ).toBe(writesBeforeDuplicate);

  const deletesBeforeConfirm = mock.requestCount(
    "DELETE",
    "/api/monitoring/watchlist/HK.00700",
  );
  page.once("dialog", async (dialog) => {
    expect(dialog.type()).toBe("confirm");
    expect(dialog.message()).toContain("Remove HK.00700");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Remove HK.00700" }).click();
  await expect(watchlistLink(page, "HK.00700")).toBeHidden();
  expect(
    mock.requestCount("DELETE", "/api/monitoring/watchlist/HK.00700"),
  ).toBe(deletesBeforeConfirm + 1);

  mock.assertNoUnhandledRequests();
});

test("renders snapshots and bars, supports chart keyboard navigation, and refreshes immediately after quote SSE", async ({
  page,
}) => {
  const mock = await setupMonitoringMock(page, {
    initialInstruments: [{ code: "US.AAPL" }],
  });
  await openMonitor(page, "/monitors/US.AAPL");

  await expect(page.getByRole("heading", {
    name: /Apple Inc\. \/ 苹果/,
  }).first()).toBeVisible();
  await expect(page.locator(".monitor-last-price")).toContainText("201.25");
  await expect(page.getByRole("region", {
    name: "Underlying quote metrics",
  })).toContainText("36,420,000");

  const chart = page.getByRole("img", {
    name: /US\.AAPL's latest 12 OpenD five-minute OHLCV bars/,
  });
  await expect(chart).toBeVisible();
  const readout = page.locator(".monitor-tape-readout");
  await chart.focus();
  await chart.press("Home");
  await expect(readout).toContainText("198.70");
  await chart.press("End");
  await expect(readout).toContainText("201.60");
  await chart.press("ArrowLeft");
  await expect(readout).toContainText("202.20");

  await waitForEventSource(page);
  expect(await eventSourceUrls(page)).toContain("/api/events");
  const snapshotPath = "/api/monitoring/underlyings/US.AAPL/snapshot";
  const watchlistPath = "/api/monitoring/watchlist";
  const snapshotRequestsBefore = mock.requestCount("GET", snapshotPath);
  const watchlistRequestsBefore = mock.requestCount("GET", watchlistPath);
  const snapshot = mock.updateQuote("US.AAPL", {
    last_price: 225,
    previous_close: 200,
    change_rate: 12.5,
    source_time: "2026-07-28T18:31:00Z",
  });
  await emitApiEvent(page, "monitor.quote.updated", {
    code: "US.AAPL",
    snapshot,
  });

  await expect.poll(
    () => mock.requestCount("GET", snapshotPath),
    {
      timeout: 2_000,
      message: "quote SSE should invalidate the snapshot before its 3s poll",
    },
  ).toBeGreaterThan(snapshotRequestsBefore);
  await expect.poll(
    () => mock.requestCount("GET", watchlistPath),
    {
      timeout: 2_000,
      message: "quote SSE should invalidate the watchlist quote immediately",
    },
  ).toBeGreaterThan(watchlistRequestsBefore);
  await expect(page.locator(".monitor-last-price")).toContainText("225.00");

  mock.assertNoUnhandledRequests();
});

test("keeps option routes refreshable and navigable while exposing Greeks and missing values", async ({
  page,
}) => {
  const mock = await setupMonitoringMock(page, {
    initialInstruments: [{ code: "US.AAPL" }],
  });
  await openMonitor(page, "/monitors/US.AAPL");

  const optionsLink = page.getByRole("link", { name: "Option chain" }).last();
  await optionsLink.focus();
  await optionsLink.press("Enter");
  await expect(page).toHaveURL(/\/monitors\/US\.AAPL\/options$/);
  await expect(page.getByRole("heading", { name: "Option chain desk" })).toBeVisible();

  await page.getByRole("combobox", { name: "Expiration" }).selectOption(
    "2026-08-14",
  );
  await expect(page).toHaveURL(
    /\/monitors\/US\.AAPL\/options\?expiration=2026-08-14$/,
  );
  const table = page.getByRole("table", {
    name: /US\.AAPL 2026-08-14 Call｜Strike｜Put option chain/,
  });
  await expect(table).toBeVisible();
  await page.getByRole("combobox", { name: "Moneyness filter" }).selectOption(
    "otm",
  );
  await expect(table.locator("tbody tr")).toHaveCount(2);
  await page.getByRole("combobox", { name: "Moneyness filter" }).selectOption(
    "all",
  );

  const missingQuoteRow = table.getByRole("button", {
    name: new RegExp(monitoringContracts.call205),
  }).locator("xpath=ancestor::tr");
  const missingQuoteCells = missingQuoteRow.getByRole("cell");
  await expect(missingQuoteCells.nth(2)).toContainText("—");
  await expect(missingQuoteCells.nth(3)).toHaveText("—");
  await expect(missingQuoteCells.nth(6)).toHaveText("—");

  const contractButton = table.getByRole("button", {
    name: new RegExp(monitoringContracts.call200),
  });
  await contractButton.click();
  await expect(page).toHaveURL(
    new RegExp(
      `/monitors/US\\.AAPL/options/${monitoringContracts.call200}\\?expiration=2026-08-14$`,
    ),
  );
  let dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("heading", {
    name: "Complete Greeks",
  })).toBeVisible();
  await expect(definitionValue(dialog, "DELTA")).toContainText("0.5400");
  await expect(definitionValue(dialog, "RHO")).toHaveText("—");
  await expect(page.getByRole("button", {
    name: "Close contract details",
  })).toBeFocused();

  await page.keyboard.press("Escape");
  await expect(page).toHaveURL(
    /\/monitors\/US\.AAPL\/options\?expiration=2026-08-14$/,
  );
  await expect(contractButton).toBeFocused();

  await contractButton.click();
  await page.reload();
  dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(page).toHaveURL(
    new RegExp(
      `/monitors/US\\.AAPL/options/${monitoringContracts.call200}\\?expiration=2026-08-14$`,
    ),
  );
  await page.goBack();
  await expect(dialog).toBeHidden();
  await expect(page).toHaveURL(
    /\/monitors\/US\.AAPL\/options\?expiration=2026-08-14$/,
  );
  await page.goForward();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page).toHaveURL(
    new RegExp(
      `/monitors/US\\.AAPL/options/${monitoringContracts.call200}\\?expiration=2026-08-14$`,
    ),
  );

  mock.assertNoUnhandledRequests();
});

test("creates stock and option rules, toggles them, receives an alert by SSE, and acknowledges it", async ({
  page,
}) => {
  const mock = await setupMonitoringMock(page, {
    initialInstruments: [{ code: "US.AAPL" }],
  });
  await openMonitor(page, "/monitors/US.AAPL/alerts");

  await page.getByRole("textbox", { name: "Rule name" }).fill("AAPL breakout");
  await page.getByRole("spinbutton", { name: "Threshold" }).fill("220");
  const advanced = page.getByText("Cooldown, frequency & session", {
    exact: true,
  });
  await advanced.focus();
  await advanced.press("Enter");
  await page.getByRole("spinbutton", { name: "Cooldown seconds" }).fill("60");
  await page.getByRole("spinbutton", { name: "Daily trigger limit" }).fill("3");
  await page.getByRole("button", { name: "Create monitoring rule" }).click();
  const stockRule = page.locator(".monitor-rule-ledger li").filter({
    hasText: "AAPL breakout",
  });
  await expect(stockRule).toBeVisible();
  await stockRule.getByRole("button", { name: "Enabled" }).click();
  await expect(stockRule.getByRole("button", { name: "Disabled" })).toBeVisible();

  await page.getByRole("textbox", { name: "Rule name" }).fill("AAPL call IV");
  await page.getByRole("combobox", { name: "Instrument" }).selectOption("option");
  await page.getByRole("textbox", { name: "Futu code" }).fill(
    monitoringContracts.call200,
  );
  await page.getByRole("combobox", { name: "Metric" }).selectOption(
    "option_implied_volatility",
  );
  await page.getByRole("spinbutton", { name: "Threshold" }).fill("35");
  await page.getByRole("combobox", { name: "Severity" }).selectOption("critical");
  await page.getByRole("button", { name: "Create monitoring rule" }).click();
  await expect(page.getByText("AAPL call IV", { exact: true })).toBeVisible();

  await waitForEventSource(page);
  const alertsPath = "/api/monitoring/alerts";
  const alertRequestsBefore = mock.requestCount("GET", alertsPath);
  const alert = mock.addAlertForRule("AAPL call IV", 40);
  await emitApiEvent(page, "monitor.alert.triggered", { alert });

  await expect.poll(
    () => mock.requestCount("GET", alertsPath),
    {
      timeout: 2_000,
      message: "alert SSE should invalidate alerts before the 5s poll",
    },
  ).toBeGreaterThan(alertRequestsBefore);
  const alertEntry = page.locator(".monitor-alert-ledger li").filter({
    hasText: "AAPL call IV",
  });
  await expect(alertEntry).toBeVisible();
  await expect(alertEntry).toContainText("40.0000");
  await alertEntry.getByRole("button", { name: "Acknowledge" }).click();
  await expect(alertEntry).toContainText("Acknowledged");

  await page.getByRole("checkbox", { name: "Unacknowledged only" }).check();
  await expect(alertEntry).toBeHidden();
  await expect(page.getByText(
    "No alerts match the current filter.",
    { exact: true },
  )).toBeVisible();

  mock.assertNoUnhandledRequests();
});

test("shows offline, stale, closed, permission, quota, and unavailable states explicitly", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const mock = await setupMonitoringMock(page, {
    initialInstruments: [{ code: "US.AAPL" }],
  });
  const cases: Array<{
    mode: MonitoringDataMode;
    connected: boolean;
    title: string;
  }> = [
    {
      mode: "offline",
      connected: false,
      title: "OpenD is currently offline",
    },
    {
      mode: "stale",
      connected: true,
      title: "The current quote is stale",
    },
    {
      mode: "market_closed",
      connected: true,
      title: "The market is closed",
    },
    {
      mode: "permission",
      connected: true,
      title: "Quote permission is missing",
    },
    {
      mode: "quota",
      connected: true,
      title: "OpenD subscription capacity is exhausted",
    },
    {
      mode: "unavailable",
      connected: true,
      title: "No market data is available",
    },
  ];

  for (const scenario of cases) {
    mock.setConnected(scenario.connected);
    mock.setMarketDataMode(scenario.mode);
    await page.goto(`/monitors/US.AAPL?scenario=${scenario.mode}`);
    await expect(page.getByText(scenario.title, { exact: true })).toBeVisible({
      timeout: 20_000,
    });
  }

  mock.assertNoUnhandledRequests();
});

test("switches between English and Chinese without losing the monitor route or expiration", async ({
  page,
}) => {
  const mock = await setupMonitoringMock(page, {
    locale: "en-US",
    initialInstruments: [{ code: "US.AAPL" }],
  });
  const route = "/monitors/US.AAPL/options?expiration=2026-08-14";
  await openMonitor(page, route);

  await expect(page.locator("html")).toHaveAttribute("lang", "en-US");
  await expect(page.getByRole("heading", { name: "Option chain desk" })).toBeVisible();
  await page.getByRole("button", { name: "切换到中文" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
  await expect(page.getByRole("heading", { name: "期权链观察台" })).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`${escapeRegExp(route)}$`));

  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
  await expect(page.getByRole("heading", { name: "期权链观察台" })).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`${escapeRegExp(route)}$`));
  await page.getByRole("button", { name: "Switch to English" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en-US");
  await expect(page.getByRole("heading", { name: "Option chain desk" })).toBeVisible();

  mock.assertNoUnhandledRequests();
});

test("contains page overflow at 1440, 1024, 781, 780, and 390 pixels", async ({
  page,
}) => {
  const mock = await setupMonitoringMock(page, {
    initialInstruments: [
      { code: "US.AAPL" },
      { code: "HK.00700" },
    ],
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await openMonitor(page, "/monitors/US.AAPL/options");
  await expect(page.getByRole("table")).toBeVisible();

  for (const width of [1440, 1024, 781, 780, 390]) {
    await page.setViewportSize({
      width,
      height: width <= 390 ? 844 : 900,
    });
    await expect(page.getByRole("heading", { name: "Option chain desk" })).toBeVisible();
    await assertNoPageOverflow(page, width);
  }

  const tableWrap = page.locator(".option-chain-table-wrap");
  const tableOverflow = await tableWrap.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
  }));
  expect(tableOverflow.scrollWidth).toBeGreaterThan(tableOverflow.clientWidth);

  await page.getByRole("button", {
    name: new RegExp(monitoringContracts.call200),
  }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  const dialogBox = await dialog.boundingBox();
  expect(dialogBox).not.toBeNull();
  expect(dialogBox?.x ?? -1).toBeGreaterThanOrEqual(0);
  expect((dialogBox?.x ?? 0) + (dialogBox?.width ?? 0)).toBeLessThanOrEqual(391);
  await assertNoPageOverflow(page, 390);

  mock.assertNoUnhandledRequests();
});

async function openMonitor(
  page: Page,
  path = "/monitors",
): Promise<void> {
  await page.goto(path);
  await expect(page.getByRole("heading", { name: monitorTitle }).first()).toBeVisible();
  await waitForEventSource(page);
}

function watchlistLink(page: Page, code: string): Locator {
  return page.getByRole("link", { name: new RegExp(escapeRegExp(code)) }).last();
}

function definitionValue(container: Locator, term: string): Locator {
  return container.locator("dl > div").filter({ hasText: term }).locator("dd");
}

async function assertNoPageOverflow(page: Page, width: number): Promise<void> {
  const dimensions = await page.evaluate(() => {
    const viewport = document.documentElement.clientWidth;
    const offenders = [...document.querySelectorAll<HTMLElement>("body *")]
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return {
          selector: [
            element.tagName.toLowerCase(),
            element.id ? `#${element.id}` : "",
            ...[...element.classList].map((name) => `.${name}`),
          ].join(""),
          left: Math.round(rect.left * 100) / 100,
          right: Math.round(rect.right * 100) / 100,
          scrollWidth: element.scrollWidth,
          clientWidth: element.clientWidth,
        };
      })
      .filter(({ left, right }) => left < -1 || right > viewport + 1)
      .slice(0, 12);
    return {
      viewport,
      document: document.documentElement.scrollWidth,
      body: document.body.scrollWidth,
      offenders,
    };
  });
  expect(
    dimensions.document,
    `document should not overflow at ${width}px; offenders: ${
      JSON.stringify(dimensions.offenders)
    }`,
  ).toBeLessThanOrEqual(dimensions.viewport + 1);
  expect(
    dimensions.body,
    `body should not overflow at ${width}px`,
  ).toBeLessThanOrEqual(dimensions.viewport + 1);
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
