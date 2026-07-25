import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { StrategyMigrationReport } from "../api/types";
import { StrategyMigrationPanel } from "./StrategyMigrationPanel";

const source = [
  "from stock_strategy.futu import *",
  "class Strategy(StrategyBase):",
  "    def handle_data(self):",
  "        pass",
].join("\n");

const staticReport: StrategyMigrationReport = {
  source_sha256: "a".repeat(64),
  syntax_valid: true,
  compatibility: {
    supported: true,
    issues: [],
    unsupported_names: [],
    bar_types: [],
    findings: [],
    semantic_differences: [
      { code: "next_bar", message: "Orders execute on the next bar." },
    ],
  },
  fixture: { status: "not_run" },
  next_step: "run_deterministic_fixture",
};

const fixtureReport: StrategyMigrationReport = {
  ...staticReport,
  fixture: { status: "passed", bars: 400, symbol: "US.AAPL" },
  next_step: "save_and_run_opend_backtest",
};

function renderPanel(onImported = vi.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <StrategyMigrationPanel onImported={onImported} />
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByText("迁移 Futu 策略"));
  fireEvent.change(screen.getByLabelText("Futu 策略源码"), {
    target: { value: source },
  });
  fireEvent.change(screen.getByLabelText("导入后的策略名"), {
    target: { value: "migrated_strategy" },
  });
  return onImported;
}

describe("StrategyMigrationPanel", () => {
  it("requires scan and fixture validation before importing", async () => {
    vi.spyOn(api, "scanMigration").mockResolvedValue(staticReport);
    vi.spyOn(api, "validateMigrationFixture").mockResolvedValue(fixtureReport);
    const importMigration = vi.spyOn(api, "importMigration").mockResolvedValue({
      strategy: {
        path: "strategies/migrated_strategy.py",
        name: "migrated_strategy",
        group: "我的策略",
        readonly: false,
        revision: "b".repeat(64),
        size: source.length,
        updated_at: "2026-07-25T12:00:00+08:00",
        content: source,
      },
      report: fixtureReport,
    });
    const onImported = renderPanel();
    const fixtureButton = screen.getByRole("button", {
      name: "2 · Fixture 验证",
    });
    const importButton = screen.getByRole("button", {
      name: "3 · 导入策略",
    });

    expect(fixtureButton).toBeDisabled();
    expect(importButton).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "1 · 静态扫描" }));
    await waitFor(() => expect(fixtureButton).toBeEnabled());
    fireEvent.click(fixtureButton);
    await waitFor(() => expect(importButton).toBeEnabled());
    fireEvent.click(importButton);

    await waitFor(() =>
      expect(importMigration).toHaveBeenCalledWith(
        "migrated_strategy",
        source,
      ),
    );
    expect(onImported).toHaveBeenCalledWith(
      "strategies/migrated_strategy.py",
    );
  });
});
