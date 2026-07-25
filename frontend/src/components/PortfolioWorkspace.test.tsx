import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { PortfolioWorkspace } from "./PortfolioWorkspace";

describe("PortfolioWorkspace", () => {
  it("submits normalized stock weights to the shared-cash portfolio API", async () => {
    const run = vi.spyOn(api, "runPortfolio").mockImplementation(
      () => new Promise(() => undefined),
    );
    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <PortfolioWorkspace opendConnected />
      </QueryClientProvider>,
    );

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
});
