import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AppConfig } from "../api/types";
import { BacktestForm } from "./BacktestForm";

const config: AppConfig = {
  strategies: [
    {
      path: "examples/ma_cross.py",
      name: "ma cross",
      group: "示例策略",
      readonly: true,
      revision: "a".repeat(64),
      size: 100,
      updated_at: "2026-07-18T00:00:00+08:00",
      parameters: [{ name: "period", label: "均线周期", description: "", type: "int", default: 20, min: 2, max: 120, candidates: [10, 20] }],
    },
  ],
  kline_types: ["K_DAY", "K_5M", "K_1M"],
  adjustment_types: ["QFQ", "HFQ", "NONE"],
  session_types: ["ALL", "RTH", "ETH"],
};

describe("BacktestForm", () => {
  it("submits a typed OpenD backtest request", () => {
    const onSubmit = vi.fn();
    render(
      <BacktestForm
        config={config}
        selectedStrategy="examples/ma_cross.py"
        onStrategyChange={() => undefined}
        onSubmit={onSubmit}
        running={false}
        opendConnected
        parameterDefinitions={config.strategies[0].parameters}
      />,
    );
    fireEvent.change(screen.getByLabelText(/^标的$/), {
      target: { value: "hk.00700" },
    });
    fireEvent.click(screen.getByRole("button", { name: /运行 OpenD 回测/ }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        strategy: "examples/ma_cross.py",
        symbol: "HK.00700",
        ktype: "K_DAY",
        session: "ALL",
        liquidate_on_end: false,
        initial_cash: 100000,
        parameters: { period: 20 },
        refresh_cache: false,
      }),
    );
  });

  it("disables execution while OpenD is offline", () => {
    render(
      <BacktestForm
        config={config}
        selectedStrategy="examples/ma_cross.py"
        onStrategyChange={() => undefined}
        onSubmit={() => undefined}
        running={false}
        opendConnected={false}
      />,
    );
    expect(screen.getByRole("button", { name: /运行 OpenD 回测/ })).toBeDisabled();
  });

  it("explains strategy compatibility blockers before execution", () => {
    render(
      <BacktestForm
        config={config}
        selectedStrategy="examples/ma_cross.py"
        onStrategyChange={() => undefined}
        onSubmit={() => undefined}
        running={false}
        opendConnected
        compatibility={{
          supported: false,
          issues: ["unsupported_names"],
          unsupported_names: ["lot_size", "order_status"],
          bar_types: ["K_1M", "K_5M"],
          driver_bar_type: "K_1M",
          session_types: ["RTH"],
          required_session: "RTH",
        }}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("lot_size · order_status");
    expect(screen.getByRole("button", { name: /运行 OpenD 回测/ })).toBeDisabled();
  });

  it("selects the smallest driver and session for a multi-period stock strategy", () => {
    render(
      <BacktestForm
        config={config}
        selectedStrategy="examples/ma_cross.py"
        onStrategyChange={() => undefined}
        onSubmit={() => undefined}
        running={false}
        opendConnected
        compatibility={{
          supported: true,
          issues: [],
          unsupported_names: [],
          bar_types: ["K_15M", "K_1M", "K_5M", "K_DAY"],
          driver_bar_type: "K_1M",
          session_types: ["RTH"],
          required_session: "RTH",
        }}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("多周期股票回测已就绪");
    expect(screen.getByLabelText(/K 线周期/)).toHaveValue("K_1M");
    expect(screen.getByLabelText(/交易时段/)).toHaveValue("RTH");
  });
});
