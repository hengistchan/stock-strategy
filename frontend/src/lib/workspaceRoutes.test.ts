import { describe, expect, it } from "vitest";
import { workspacePaths } from "./workspaceRoutes";

describe("workspace routes", () => {
  it("maps stable paths to each workspace", () => {
    expect(workspacePaths.backtest).toBe("/backtests");
    expect(workspacePaths.backtestNew).toBe("/backtests/new");
    expect(workspacePaths.backtestNewForSymbol("hk.00700")).toBe(
      "/backtests/new?symbol=HK.00700",
    );
    expect(workspacePaths.backtestDetail("job 1")).toBe("/backtests/job%201");
    expect(workspacePaths.iterate).toBe("/experiments");
    expect(workspacePaths.experimentNew).toBe("/experiments/new");
    expect(workspacePaths.experimentDetail("exp 1")).toBe(
      "/experiments/exp%201",
    );
    expect(workspacePaths.strategies).toBe("/strategies");
    expect(workspacePaths.monitors).toBe("/monitors");
    expect(workspacePaths.monitorSymbol("US.AAPL")).toBe("/monitors/US.AAPL");
    expect(workspacePaths.monitorOptions("US.AAPL")).toBe(
      "/monitors/US.AAPL/options",
    );
    expect(workspacePaths.monitorContract("US.AAPL", "US.AAPL 260731 C100")).toBe(
      "/monitors/US.AAPL/options/US.AAPL%20260731%20C100",
    );
    expect(workspacePaths.monitorAlerts("US.AAPL")).toBe(
      "/monitors/US.AAPL/alerts",
    );
    expect(workspacePaths.strategyDetail("strategies/my strategy.py")).toBe(
      "/strategies/strategies/my%20strategy.py",
    );
  });
});
