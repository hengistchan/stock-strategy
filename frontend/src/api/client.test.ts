import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, initializeApiTokenFromFragment } from "./client";

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

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/health",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: `Bearer ${token}`,
        }),
      }),
    );
  });
});
