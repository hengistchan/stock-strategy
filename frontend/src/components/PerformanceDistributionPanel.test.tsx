import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { PerformanceAnalysis } from "../api/types";
import { PerformanceDistributionPanel } from "./PerformanceDistributionPanel";

const emptyDistribution = {
  count: 0,
  unit: "percent" as const,
  min: null,
  p10: null,
  p25: null,
  median: null,
  p75: null,
  p90: null,
  max: null,
  mean: null,
  std: null,
};

describe("PerformanceDistributionPanel", () => {
  it("shows quantiles, monthly returns, and regime sample sizes", () => {
    const analysis: PerformanceAnalysis = {
      return_distribution: {
        ...emptyDistribution,
        count: 20,
        p10: -2,
        median: 0.3,
        p90: 2.5,
        std: 1.2,
      },
      drawdown_distribution: { ...emptyDistribution, p10: -8 },
      trade_pnl_distribution: { ...emptyDistribution, unit: "currency" },
      monthly_returns: [
        { period: "2025-01", return_pct: 3.2, observations: 20 },
      ],
      yearly_returns: [],
      rolling: [
        {
          date: "2025-01-31",
          window_days: 20,
          sharpe_ratio: 1.4,
          max_drawdown_pct: -8,
          return_pct: 3.2,
        },
      ],
      attribution: {
        weekday: [],
        month: [],
        session: [],
        market_regime: [
          {
            bucket: "up",
            return_pct: 4,
            average_return_pct: 0.4,
            positive_rate_pct: 60,
            observations: 10,
          },
        ],
      },
    };

    render(<PerformanceDistributionPanel analysis={analysis} />);

    expect(screen.getByText("2025-01")).toBeInTheDocument();
    expect(screen.getByText("基准上涨日")).toBeInTheDocument();
    expect(screen.getByText("10 个观测")).toBeInTheDocument();
    expect(screen.getByText("1.40")).toBeInTheDocument();
  });
});
