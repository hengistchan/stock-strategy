import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { BacktestJob } from "../api/types";
import { RunHistory } from "./RunHistory";

function job(id: string, symbol: string, strategy: string, start: string): BacktestJob {
  return {
    id,
    status: "succeeded",
    created_at: "2026-07-18T14:00:00+08:00",
    started_at: "2026-07-18T14:00:00+08:00",
    finished_at: "2026-07-18T14:00:01+08:00",
    request: {
      strategy,
      symbol,
      start,
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
    },
    strategy_path: strategy,
    run_dir: null,
    stdout: "",
    stderr: "",
    error: null,
  };
}

describe("RunHistory", () => {
  it("navigates the archive by symbol and strategy before showing runs", () => {
    const onSelect = vi.fn();
    const jobs = [
      job("aapl-ma", "US.AAPL", "examples/ma_cross.py", "2024-01-01"),
      job("aapl-breakout", "US.AAPL", "strategies/breakout.py", "2023-01-01"),
      job("futu-ma", "US.FUTU", "examples/ma_cross.py", "2022-01-01"),
    ];
    render(
      <RunHistory
        jobs={jobs}
        activeJobId="aapl-ma"
        onSelect={onSelect}
        onRefresh={() => undefined}
        onCreate={() => undefined}
        symbolNames={{ "US.AAPL": "苹果", "US.FUTU": "富途控股" }}
      />,
    );

    expect(screen.getByRole("combobox", { name: "标的" })).toHaveValue("US.AAPL");
    expect(screen.getByRole("option", { name: "US.AAPL · 苹果" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "策略" })).toHaveValue("examples/ma_cross.py");
    expect(screen.getByText("回测 2 · 策略 2")).toBeInTheDocument();
    expect(screen.getByText("2024-01-01 → 2025-12-31")).toBeInTheDocument();
    expect(screen.queryByText("2023-01-01 → 2025-12-31")).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole("combobox", { name: "策略" }), {
      target: { value: "strategies/breakout.py" },
    });
    expect(onSelect).toHaveBeenCalledWith("aapl-breakout");

    fireEvent.change(screen.getByRole("combobox", { name: "标的" }), {
      target: { value: "US.FUTU" },
    });
    expect(onSelect).toHaveBeenCalledWith("futu-ma");
  });

  it("directs an empty archive to create a backtest", () => {
    const onCreate = vi.fn();
    render(
      <RunHistory
        jobs={[]}
        activeJobId={null}
        onSelect={() => undefined}
        onRefresh={() => undefined}
        onCreate={onCreate}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /创建第一次回测/ }));
    expect(onCreate).toHaveBeenCalledOnce();
  });

  it("paginates long symbol and strategy histories", () => {
    const jobs = Array.from({ length: 7 }, (_, index) =>
      job(`run-${index}`, "US.AAPL", "examples/ma_cross.py", `202${index}-01-01`),
    );
    render(
      <RunHistory
        jobs={jobs}
        activeJobId="run-0"
        onSelect={() => undefined}
        onRefresh={() => undefined}
        onCreate={() => undefined}
      />,
    );

    expect(screen.queryByText("2026-01-01 → 2025-12-31")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /下一页/ }));
    expect(screen.getByText("2026-01-01 → 2025-12-31")).toBeInTheDocument();
    expect(screen.getByText("第 2 / 2 页")).toBeInTheDocument();
  });
});
