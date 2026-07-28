import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { OptionChainResponse, OptionExpiration } from "../../api/types";
import { I18nProvider } from "../../i18n/I18nProvider";
import { OptionChainPanel } from "./OptionChainPanel";

const expirations: OptionExpiration[] = [
  { expiration: "2026-07-31", days_to_expiry: 3, cycle: "WEEKLY" },
  { expiration: "2026-08-21", days_to_expiry: 24, cycle: "MONTHLY" },
];

const chain: OptionChainResponse = {
  underlying: "US.AAPL",
  expiration: "2026-07-31",
  fetched_at: "2026-07-28T02:00:00Z",
  source: "opend",
  underlying_snapshot: {
    code: "US.AAPL",
    name: "Apple",
    instrument_type: "stock",
    source: "opend",
    source_time: "2026-07-28 10:00:00",
    fetched_at: "2026-07-28T02:00:00Z",
    last_price: 200,
  },
  contracts: [
    {
      code: "US.AAPL260731C200000",
      name: "AAPL C200",
      underlying_code: "US.AAPL",
      option_type: "CALL",
      expiration: "2026-07-31",
      strike_price: 200,
      last_price: 3.2,
      bid_price: 3.1,
      ask_price: 3.3,
      option_implied_volatility: 21.5,
      volume: 100,
      option_open_interest: 500,
    },
    {
      code: "US.AAPL260731P200000",
      name: "AAPL P200",
      underlying_code: "US.AAPL",
      option_type: "PUT",
      expiration: "2026-07-31",
      strike_price: 200,
      last_price: null,
      bid_price: null,
      ask_price: null,
      option_implied_volatility: null,
      volume: null,
      option_open_interest: null,
    },
  ],
  summary: {},
};

describe("OptionChainPanel", () => {
  it("renders CALL｜STRIKE｜PUT rows, daily OI semantics, missing values, and contract actions", () => {
    const onOpenContract = vi.fn();
    const onExpirationChange = vi.fn();
    render(
      <I18nProvider>
        <OptionChainPanel
          symbol="US.AAPL"
          expirations={expirations}
          expiration="2026-07-31"
          data={chain}
          expirationsLoading={false}
          chainLoading={false}
          error={null}
          onExpirationChange={onExpirationChange}
          onOpenContract={onOpenContract}
          onRetry={vi.fn()}
        />
      </I18nProvider>,
    );

    expect(screen.getAllByText(/OI · 日更|OI · DAILY/).length).toBeGreaterThan(0);
    expect(screen.getByText(/daily\/as-of/)).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.getAllByText("ATM").length).toBeGreaterThan(0);

    fireEvent.click(
      screen.getByRole("button", {
        name: /US\.AAPL260731C200000/,
      }),
    );
    expect(onOpenContract).toHaveBeenCalledWith("US.AAPL260731C200000");

    fireEvent.change(
      screen.getByRole("combobox", { name: /到期日|Expiration/ }),
      { target: { value: "2026-08-21" } },
    );
    expect(onExpirationChange).toHaveBeenCalledWith("2026-08-21");
  });

  it("shows a permission-specific state instead of a generic empty chain", () => {
    render(
      <I18nProvider>
        <OptionChainPanel
          symbol="US.AAPL"
          expirations={[]}
          expiration={null}
          expirationsLoading={false}
          chainLoading={false}
          error={
            new ApiError(
              "permission denied",
              503,
              "market_data_permission_denied",
            )
          }
          onExpirationChange={vi.fn()}
          onOpenContract={vi.fn()}
          onRetry={vi.fn()}
        />
      </I18nProvider>,
    );

    expect(
      screen.getByRole("heading", {
        name: /缺少相应行情权限|Quote permission is missing/,
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/没有合约|No contracts/)).not.toBeInTheDocument();
  });
});
