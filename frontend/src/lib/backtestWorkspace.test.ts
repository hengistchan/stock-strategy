import { describe, expect, it } from "vitest";
import type { BacktestJob } from "../api/types";
import { resolveVisibleJobId } from "./backtestWorkspace";

function makeJob(id: string, status: BacktestJob["status"]): BacktestJob {
  return {
    id,
    status,
    created_at: "2026-07-18T10:00:00Z",
    started_at: null,
    finished_at: null,
    request: {
      strategy: "examples/ma_cross.py",
      symbol: "US.AAPL",
      start: "2025-01-01",
      end: "2025-12-31",
      ktype: "K_DAY",
      autype: "QFQ",
      initial_cash: 100_000,
      commission_bps: 3,
      min_commission: 1,
      slippage_bps: 5,
      warmup_bars: 0,
      allow_short: false,
    },
    strategy_path: "examples/ma_cross.py",
    run_dir: null,
    stdout: "",
    stderr: "",
    error: null,
  };
}

describe("resolveVisibleJobId", () => {
  const jobs = [makeJob("running-job", "running"), makeJob("completed-job", "succeeded")];

  it("clears the visible job while creating a backtest", () => {
    expect(resolveVisibleJobId("create", "completed-job", jobs)).toBeNull();
  });

  it("restores the active job in the archive", () => {
    expect(resolveVisibleJobId("archive", "completed-job", jobs)).toBe("completed-job");
  });

  it("defaults to the latest successful job when no job is active", () => {
    expect(resolveVisibleJobId("archive", null, jobs)).toBe("completed-job");
  });
});
