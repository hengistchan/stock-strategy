import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Trade } from "../api/types";
import { TradeTable } from "./TradeTable";

function makeTrade(index: number): Trade {
  return {
    trade_id: index,
    symbol: "US.AAPL",
    side: "LONG",
    entry_date: "2025-01-02 09:30:00",
    exit_date: "2025-01-02 09:35:00",
    entry_price: 100,
    exit_price: 101,
    quantity: 10,
    gross_pnl: 10,
    fees: 1,
    net_pnl: 9,
    return_pct: 1,
    bars_held: 5,
    exit_reason: `signal-${index}`,
  };
}

describe("TradeTable pagination", () => {
  it("renders 25 rows at a time and navigates to the next page", () => {
    const trades = Array.from({ length: 31 }, (_, index) => makeTrade(index + 1));
    const { container } = render(<TradeTable trades={trades} ktype="K_1M" exposure={42} />);

    expect(container.querySelectorAll("tbody tr")).toHaveLength(25);
    expect(screen.getByText("signal-1")).toBeInTheDocument();
    expect(screen.queryByText("signal-26")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "下一页" }));

    expect(container.querySelectorAll("tbody tr")).toHaveLength(6);
    expect(screen.queryByText("signal-1")).not.toBeInTheDocument();
    expect(screen.getByText("signal-26")).toBeInTheDocument();
  });
});
