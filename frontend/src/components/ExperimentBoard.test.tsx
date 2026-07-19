import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Experiment } from "../api/types";
import { ExperimentBoard } from "./ExperimentBoard";

const experiment: Experiment = {
  id: "exp-1",
  name: "MA 参数矩阵",
  status: "succeeded",
  created_at: "2026-07-18T12:00:00+08:00",
  started_at: "2026-07-18T12:00:00+08:00",
  finished_at: "2026-07-18T12:01:00+08:00",
  objective: "sharpe_ratio",
  base_request: {
    strategy: "examples/ma_cross.py", symbol: "US.AAPL", start: "2024-01-01", end: "2025-12-31", ktype: "K_DAY", autype: "QFQ", session: "ALL", initial_cash: 100000, commission_bps: 3, min_commission: 1, slippage_bps: 5, warmup_bars: 0, allow_short: false,
  },
  parameter_grid: { fast_period: [10, 20] },
  strategy_path: "examples/ma_cross.py",
  progress: { completed: 2, total: 2 },
  runs: [
    { index: 1, parameters: { fast_period: 10 }, job_id: "job-1", status: "succeeded", score: 1.2, rank: 2, error: null, metrics: { total_return_pct: 20, benchmark_return_pct: 10, max_drawdown_pct: -12, sharpe_ratio: 1.2, total_trades: 3, total_fees: 20, exposure_pct: 60 } },
    { index: 2, parameters: { fast_period: 20 }, job_id: "job-2", status: "succeeded", score: 1.8, rank: 1, error: null, metrics: { total_return_pct: 30, benchmark_return_pct: 10, max_drawdown_pct: -10, sharpe_ratio: 1.8, total_trades: 4, total_fees: 25, exposure_pct: 65 } },
  ],
};

describe("ExperimentBoard", () => {
  it("ranks candidates and opens a selected comparison result", () => {
    const onOpenRun = vi.fn();
    render(
      <ExperimentBoard
        experiments={[experiment]}
        experiment={experiment}
        activeExperimentId="exp-1"
        onSelectExperiment={() => undefined}
        onOpenRun={onOpenRun}
        symbolNames={{ "US.AAPL": "苹果" }}
      />,
    );

    expect(screen.getAllByText(/US\.AAPL · 苹果/).length).toBeGreaterThan(0);
    expect(screen.getByText("#1")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("比较第 2 组"));
    fireEvent.click(screen.getByRole("button", { name: /查看回测证据/ }));
    expect(onOpenRun).toHaveBeenCalledWith("job-2");
  });
});
