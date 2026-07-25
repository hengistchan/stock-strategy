import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { StrategyDocument } from "../api/types";
import { StrategyVersionPanel } from "./StrategyVersionPanel";

const currentRevision = "b".repeat(64);
const previousRevision = "a".repeat(64);
const document: StrategyDocument = {
  path: "strategies/demo.py",
  name: "demo",
  group: "我的策略",
  readonly: false,
  revision: currentRevision,
  size: 42,
  updated_at: "2026-07-25T12:00:00+08:00",
  content: "class Strategy:\n    value = 2\n",
};

describe("StrategyVersionPanel", () => {
  it("shows immutable lineage usage and restores with optimistic locking", async () => {
    vi.spyOn(api, "strategyVersions").mockResolvedValue({
      strategy_path: document.path,
      versions: [
        {
          id: "current",
          revision: currentRevision,
          created_at: "2026-07-25T12:00:00+08:00",
          reason: "saved",
          source_path: "runs/current.py",
          current: true,
          backtest_count: 2,
          experiment_count: 1,
        },
        {
          id: "previous",
          revision: previousRevision,
          created_at: "2026-07-24T12:00:00+08:00",
          reason: "created",
          source_path: "runs/previous.py",
          current: false,
          backtest_count: 1,
          experiment_count: 0,
        },
      ],
    });
    const restore = vi.spyOn(api, "restoreStrategyVersion").mockResolvedValue({
      ...document,
      revision: previousRevision,
      content: "class Strategy:\n    pass\n",
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <StrategyVersionPanel document={document} />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("2 次回测 · 1 次实验")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "恢复此版本" }));
    await waitFor(() => expect(restore).toHaveBeenCalledWith(
      document.path,
      previousRevision,
      currentRevision,
    ));
  });
});
