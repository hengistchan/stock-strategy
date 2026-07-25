import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";
import { App } from "./App";
import { I18nProvider } from "./i18n/I18nProvider";


function LocationProbe() {
  return <output aria-label="current-path">{useLocation().pathname}</output>;
}

describe("workspace entity routes", () => {
  afterEach(() => vi.unstubAllGlobals());

  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const request = input instanceof Request ? input : new Request(input);
        const path = new URL(request.url).pathname;
        const payloads: Record<string, unknown> = {
          "/api/health": {
            status: "ok",
            opend: { connected: true, host: "127.0.0.1", port: 11111 },
          },
          "/api/config": {
            strategies: [],
            kline_types: ["K_DAY"],
            adjustment_types: ["QFQ"],
            session_types: ["ALL"],
          },
          "/api/strategies": { strategies: [] },
          "/api/jobs": { jobs: [] },
        };
        return new Response(JSON.stringify(payloads[path] ?? {}), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
  });

  it("moves the empty archive to a durable new-backtest URL", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/backtests"]}>
          <I18nProvider>
            <App />
            <LocationProbe />
          </I18nProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    fireEvent.click(
      await screen.findByRole("button", {
        name: /创建第一次回测|Create the first backtest/,
      }),
    );

    await waitFor(() =>
      expect(screen.getByLabelText("current-path")).toHaveTextContent(
        "/backtests/new",
      ),
    );
    expect(screen.getByText("INPUT")).toBeInTheDocument();
  });
});
