import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { BacktestJob, BacktestResult } from "../api/types";
import { ResultView } from "./ResultView";

vi.mock("./MetricsGrid", () => ({ MetricsGrid: () => <div>metrics</div> }));
vi.mock("./PriceChart", () => ({ PriceChart: () => <div>price chart</div> }));
vi.mock("./TradeTable", () => ({ TradeTable: () => <div>trade table</div> }));

const job: BacktestJob = {
  id: "run-1",
  status: "succeeded",
  created_at: "2026-07-18T10:00:00Z",
  started_at: "2026-07-18T10:00:01Z",
  finished_at: "2026-07-18T10:00:02Z",
  request: {
    strategy: "examples/ma_cross.py",
    symbol: "US.AAPL",
    start: "2025-01-01",
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
    liquidate_on_end: false,
  },
  strategy_path: "examples/ma_cross.py",
  run_dir: "/tmp/run-1",
  stdout: "",
  stderr: "",
  error: null,
};

function makeResult(settings: BacktestResult["summary"]["settings"]): BacktestResult {
  return {
    job,
    summary: {
      strategy: "ma_cross",
      symbol: "US.AAPL",
      period: { start: "2025-01-01", end: "2025-12-31", bars: 252 },
      settings,
      metrics: {
        total_return_pct: 1,
        benchmark_return_pct: 2,
        max_drawdown_pct: -3,
        sharpe_ratio: 0.5,
        total_trades: 0,
        total_fees: 1,
        exposure_pct: 50,
      },
    },
    price_series: [],
    trades: [],
    equity_curve: [],
    report_url: "/api/jobs/run-1/report.svg",
  };
}

describe("ResultView compatibility evidence", () => {
  it("marks pre-contract results as legacy", () => {
    render(<ResultView job={job} result={makeResult({})} loading={false} />);

    expect(screen.getByText("LEGACY RESULT")).toBeInTheDocument();
    expect(screen.getByText(/旧版撮合契约/)).toBeInTheDocument();
  });

  it("shows an unliquidated ending position for contract v2 results", () => {
    render(
      <ResultView
        job={job}
        loading={false}
        result={makeResult({
          engine_contract: {
            version: 2,
            strict_single_period: true,
            day_order_scope: "trading-day",
            end_position_policy: "mark-to-market",
          },
          ending_position: {
            quantity: 10,
            side: "LONG",
            average_price: 100,
            mark_price: 105,
            unrealized_pnl: 50,
          },
        })}
      />,
    );

    expect(screen.getByText("OPEND CONTRACT V2")).toBeInTheDocument();
    expect(screen.getByText("期末持仓未强平")).toBeInTheDocument();
    expect(screen.queryByText(/旧版撮合契约/)).not.toBeInTheDocument();
  });
});
