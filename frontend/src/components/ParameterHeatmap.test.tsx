import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Experiment } from "../api/types";
import { buildParameterSurface } from "../lib/parameterSurface";
import { ParameterHeatmap } from "./ParameterHeatmap";

const experiment = {
  objective: "sharpe_ratio",
  parameter_grid: {
    fast: [5, 10],
    slow: [20, 30],
    risk: [0.5, 1],
  },
  status: "succeeded",
  runs: [
    { index: 1, parameters: { fast: 5, slow: 20, risk: 0.5 }, job_id: "1", status: "succeeded", metrics: null, score: 1, rank: 3, error: null },
    { index: 2, parameters: { fast: 5, slow: 20, risk: 1 }, job_id: "2", status: "succeeded", metrics: null, score: 2, rank: 2, error: null },
    { index: 3, parameters: { fast: 10, slow: 30, risk: 1 }, job_id: "3", status: "succeeded", metrics: null, score: 3, rank: 1, error: null },
  ],
} as unknown as Experiment;

describe("ParameterHeatmap", () => {
  it("aggregates hidden dimensions and preserves the winning cell", () => {
    const surface = buildParameterSurface(experiment, "fast", "slow");
    expect(surface?.cells.find((cell) => cell.x === 5 && cell.y === 20)).toMatchObject({
      score: 1.5,
      runs: 2,
      bestRank: 2,
    });
    expect(surface?.cells.find((cell) => cell.x === 10 && cell.y === 30)?.bestRank).toBe(1);
  });

  it("renders a labelled parameter surface and its best candidate", () => {
    render(<ParameterHeatmap experiment={experiment} />);
    expect(screen.getByRole("region", { name: "参数稳定性热力图" })).toBeInTheDocument();
    expect(screen.getByText(/未展示的 1 个参数维度已取平均/)).toBeInTheDocument();
    expect(screen.getByText("#1")).toBeInTheDocument();
  });
});
