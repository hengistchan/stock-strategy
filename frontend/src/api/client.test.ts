import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, initializeApiTokenFromFragment } from "./client";

describe("remote API token bootstrap", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.unstubAllGlobals();
    document.cookie = "strategy_lab_token=; Max-Age=0; Path=/";
    window.history.replaceState({}, "", "/backtests");
  });

  it("moves a strong fragment token into session state and clears the URL", () => {
    const token = `remote-${"x".repeat(32)}`;
    window.history.replaceState({}, "", `/backtests#access_token=${token}`);

    initializeApiTokenFromFragment();

    expect(window.sessionStorage.getItem("strategy-lab-api-token")).toBe(token);
    expect(document.cookie).toContain("strategy_lab_token=");
    expect(window.location.hash).toBe("");
  });

  it("discards a weak fragment token", () => {
    window.history.replaceState({}, "", "/backtests#access_token=short");

    initializeApiTokenFromFragment();

    expect(window.sessionStorage.getItem("strategy-lab-api-token")).toBeNull();
    expect(window.location.hash).toBe("");
  });

  it("sends the session token in API requests", async () => {
    const token = `remote-${"x".repeat(32)}`;
    window.sessionStorage.setItem("strategy-lab-api-token", token);
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok", opend: { connected: true } }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.health();

    const request = fetchMock.mock.calls[0]?.[0] as Request;
    expect(request.url).toBe(`${window.location.origin}/api/health`);
    expect(request.headers.get("Authorization")).toBe(`Bearer ${token}`);
  });

  it("preserves structured API error codes and details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: "找不到这次回测。",
            error: {
              code: "backtest_not_found",
              message: "找不到这次回测。",
              details: { job_id: "missing" },
            },
          }),
          {
            status: 404,
            headers: { "Content-Type": "application/json" },
          },
        ),
      ),
    );

    const error = await api.job("missing").catch((reason: unknown) => reason);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 404,
      code: "backtest_not_found",
      details: { job_id: "missing" },
      message: "找不到这次回测。",
    });
  });

  it("wires monitoring watchlist, option-chain, rule, and alert operations to the generated contract", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const request = input instanceof Request ? input : new Request(input);
      const url = new URL(request.url);
      if (url.pathname.endsWith("/option-chain")) {
        return Response.json({
          underlying: "US.AAPL",
          expiration: url.searchParams.get("expiration"),
          underlying_snapshot: {
            code: "US.AAPL",
            instrument_type: "stock",
            fetched_at: "2026-07-28T00:00:00Z",
          },
          contracts: [],
          summary: {},
          fetched_at: "2026-07-28T00:00:00Z",
          source: "opend",
        });
      }
      if (url.pathname === "/api/monitoring/watchlist") {
        return Response.json(
          {
            code: "US.AAPL",
            name: "Apple",
            market: "US",
            instrument_type: "stock",
            underlying_code: null,
            enabled: true,
            created_at: "2026-07-28T00:00:00Z",
            updated_at: "2026-07-28T00:00:00Z",
          },
          { status: 201 },
        );
      }
      if (url.pathname === "/api/monitoring/rules") {
        return Response.json(
          {
            id: "rule-1",
            ...(await request.clone().json()),
            created_at: "2026-07-28T00:00:00Z",
            updated_at: "2026-07-28T00:00:00Z",
          },
          { status: 201 },
        );
      }
      return Response.json({
        id: "alert-1",
        rule_name: "AAPL breakout",
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.addWatchlistItem({
      code: "US.AAPL",
      name: "Apple",
      instrument_type: "stock",
      enabled: true,
    });
    await api.optionChain("US.AAPL", "2026-07-31");
    await api.createMonitorRule({
      name: "AAPL breakout",
      code: "US.AAPL",
      instrument_type: "stock",
      metric: "last_price",
      operator: "crosses_above",
      threshold: 220,
    });
    await api.acknowledgeMonitorAlert("alert-1");

    const requests = fetchMock.mock.calls.map(([input]) =>
      input instanceof Request ? input : new Request(input),
    );
    expect(requests[0]).toMatchObject({
      method: "POST",
    });
    expect(new URL(requests[0].url).pathname).toBe("/api/monitoring/watchlist");
    await expect(requests[0].clone().json()).resolves.toEqual({
      code: "US.AAPL",
      enabled: true,
      instrument_type: "stock",
      name: "Apple",
    });
    expect(requests[1].url).toContain(
      "/api/monitoring/underlyings/US.AAPL/option-chain?expiration=2026-07-31",
    );
    expect(new URL(requests[2].url).pathname).toBe("/api/monitoring/rules");
    await expect(requests[2].clone().json()).resolves.toMatchObject({
      metric: "last_price",
      operator: "crosses_above",
      threshold: 220,
    });
    expect(new URL(requests[3].url).pathname).toBe(
      "/api/monitoring/alerts/alert-1/ack",
    );
    expect(requests[3].method).toBe("POST");
  });

  it("queries rules and alert pages by explicit underlying scope", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const request = input instanceof Request ? input : new Request(input);
      const pathname = new URL(request.url).pathname;
      return Response.json(
        pathname.endsWith("/rules")
          ? { rules: [] }
          : { alerts: [], next_cursor: null },
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.monitorRules("us.aapl", true);
    await api.monitorAlerts("us.aapl", true, "cursor-1", 25);

    const urls = fetchMock.mock.calls.map(([input]) =>
      new URL(input instanceof Request ? input.url : String(input)),
    );
    expect(urls[0].searchParams.get("underlying_code")).toBe("us.aapl");
    expect(urls[0].searchParams.get("code")).toBeNull();
    expect(urls[0].searchParams.get("enabled")).toBe("true");
    expect(urls[1].searchParams.get("underlying_code")).toBe("us.aapl");
    expect(urls[1].searchParams.get("unacknowledged_only")).toBe("true");
    expect(urls[1].searchParams.get("cursor")).toBe("cursor-1");
    expect(urls[1].searchParams.get("limit")).toBe("25");
  });
});
