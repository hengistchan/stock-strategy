import { describe, expect, it } from "vitest";
import { workspacePaths } from "./workspaceRoutes";

describe("workspace routes", () => {
  it("maps stable paths to each workspace", () => {
    expect(workspacePaths.backtest).toBe("/backtests");
    expect(workspacePaths.backtestNew).toBe("/backtests/new");
    expect(workspacePaths.backtestDetail("job 1")).toBe("/backtests/job%201");
    expect(workspacePaths.iterate).toBe("/experiments");
    expect(workspacePaths.experimentNew).toBe("/experiments/new");
    expect(workspacePaths.experimentDetail("exp 1")).toBe(
      "/experiments/exp%201",
    );
    expect(workspacePaths.strategies).toBe("/strategies");
    expect(workspacePaths.strategyDetail("strategies/my strategy.py")).toBe(
      "/strategies/strategies/my%20strategy.py",
    );
  });
});
