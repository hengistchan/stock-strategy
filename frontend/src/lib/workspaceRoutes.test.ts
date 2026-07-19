import { describe, expect, it } from "vitest";
import { workspacePaths } from "./workspaceRoutes";

describe("workspace routes", () => {
  it("maps stable paths to each workspace", () => {
    expect(workspacePaths).toEqual({
      backtest: "/backtests",
      iterate: "/experiments",
      strategies: "/strategies",
    });
  });
});
