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
});
