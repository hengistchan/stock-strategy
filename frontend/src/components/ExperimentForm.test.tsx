import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AppConfig, StrategyParameterDefinition } from "../api/types";
import { ExperimentForm } from "./ExperimentForm";

const definitions: StrategyParameterDefinition[] = [
  {
    name: "fast_period",
    label: "短均线周期",
    description: "快速趋势周期",
    type: "int",
    default: 20,
    min: 2,
    max: 120,
    candidates: [10, 20],
  },
  {
    name: "capital_fraction",
    label: "资金使用比例",
    description: "仓位比例",
    type: "float",
    default: 0.9,
    min: 0.1,
    max: 1,
    candidates: [0.8, 0.9],
  },
];

const config: AppConfig = {
  strategies: [{ path: "examples/ma_cross.py", name: "ma cross", group: "示例策略", readonly: true, revision: "a".repeat(64), size: 100, updated_at: "2026-07-18", parameters: definitions }],
  kline_types: ["K_DAY"],
  adjustment_types: ["QFQ"],
  session_types: ["ALL"],
};

describe("ExperimentForm", () => {
  it("expands typed candidate values into an experiment request", () => {
    const onSubmit = vi.fn();
    render(
      <ExperimentForm
        config={config}
        selectedStrategy="examples/ma_cross.py"
        parameterDefinitions={definitions}
        onStrategyChange={() => undefined}
        onSubmit={onSubmit}
        running={false}
        opendConnected
      />,
    );

    fireEvent.change(screen.getByLabelText("短均线周期候选值"), { target: { value: "5, 10, 20" } });
    fireEvent.click(screen.getByRole("button", { name: /运行 6 组参数/ }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        objective: "sharpe_ratio",
        parameter_grid: {
          fast_period: [5, 10, 20],
          capital_fraction: [0.8, 0.9],
        },
        base: expect.objectContaining({
          strategy: "examples/ma_cross.py",
          parameters: { fast_period: 20, capital_fraction: 0.9 },
        }),
      }),
    );
  });
});
