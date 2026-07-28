import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { OptionContractResponse } from "../../api/types";
import { I18nProvider } from "../../i18n/I18nProvider";
import { OptionContractDialog } from "./OptionContractDialog";

const contract: OptionContractResponse = {
  freshness: "live",
  contract: {
    code: "US.AAPL260731C200000",
    name: "AAPL C200",
    underlying_code: "US.AAPL",
    option_type: "CALL",
    expiration: "2026-07-31",
    strike_price: 200,
    days_to_expiry: 3,
    lot_size: 100,
    option_contract_size: 100,
    last_price: 3.2,
    bid_price: 3.1,
    ask_price: 3.3,
    mid_price: 3.2,
    bid_ask_spread: 0.2,
    bid_ask_spread_pct: 6.25,
    volume: 100,
    option_open_interest: 500,
    volume_open_interest_ratio: 0.2,
    option_implied_volatility: 21.5,
    option_delta: 0.52,
    option_gamma: 0.04,
    option_vega: 0.16,
    option_theta: -0.08,
    option_rho: null,
    source_time: "2026-07-28 10:00:00",
  },
  analytics: {
    volatility_history: [{ time: "2026-07-27", value: 20 }],
    exercise_probability_history: [{ time: "2026-07-27", value: 0.4 }],
  },
};

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <I18nProvider>
      <button type="button" onClick={() => setOpen(true)}>
        Contract trigger
      </button>
      {open ? (
        <OptionContractDialog
          contractCode="US.AAPL260731C200000"
          data={contract}
          loading={false}
          error={null}
          onClose={() => setOpen(false)}
          onRetry={vi.fn()}
        />
      ) : null}
    </I18nProvider>
  );
}

describe("OptionContractDialog", () => {
  it("shows quote, daily OI, IV, DTE, complete Greeks, and missing values", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Contract trigger" }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/未平仓量（日更 as-of）|Open interest \(daily as-of\)/)).toBeInTheDocument();
    expect(screen.getByText("21.50%")).toBeInTheDocument();
    expect(screen.getByText("0.5200")).toBeInTheDocument();
    expect(screen.getByText("-0.0800")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.getByText(/1 条波动率历史|1 volatility rows/)).toBeInTheDocument();
  });

  it("focuses the close control and restores focus to the contract trigger", async () => {
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: "Contract trigger" });
    trigger.focus();
    fireEvent.click(trigger);

    const close = screen.getByRole("button", {
      name: /关闭合约详情|Close contract details/,
    });
    expect(close).toHaveFocus();

    fireEvent.click(close);
    await waitFor(() => expect(trigger).toHaveFocus());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
