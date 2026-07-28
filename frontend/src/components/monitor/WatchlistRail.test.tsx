import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";
import { api } from "../../api/client";
import type { MonitoredInstrument } from "../../api/types";
import { I18nProvider } from "../../i18n/I18nProvider";
import { WatchlistRail } from "./WatchlistRail";

function LocationProbe() {
  return <output aria-label="path">{useLocation().pathname}</output>;
}

const instrument: MonitoredInstrument = {
  code: "US.AAPL",
  name: "Apple",
  market: "US",
  instrument_type: "stock",
  underlying_code: null,
  enabled: true,
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
  snapshot: null,
  freshness: "unavailable",
};

describe("WatchlistRail", () => {
  afterEach(() => vi.restoreAllMocks());

  it("searches with keyboard selection and submits the canonical OpenD symbol", async () => {
    vi.spyOn(api, "symbols").mockResolvedValue({
      query: "apple",
      symbols: [{ code: "US.AAPL", name: "Apple", market: "US" }],
    });
    const onAdd = vi.fn();
    render(
      <MemoryRouter>
        <I18nProvider>
          <WatchlistRail
            activeSymbol={null}
            instruments={[]}
            opendConnected
            busyCode={null}
            adding={false}
            onAdd={onAdd}
            onToggle={vi.fn()}
            onDelete={vi.fn()}
          />
        </I18nProvider>
      </MemoryRouter>,
    );

    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "apple" } });
    const option = await screen.findByRole("option", { name: /US\.AAPL.*Apple/s });
    expect(option).toBeInTheDocument();

    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.click(screen.getByRole("button", { name: /添加监控标的|Add a monitored symbol/ }));

    expect(onAdd).toHaveBeenCalledWith({
      code: "US.AAPL",
      name: "Apple",
      market: "US",
    });
  });

  it("routes watchlist rows and exposes enable/delete actions without hiding missing quotes", async () => {
    const onToggle = vi.fn();
    const onDelete = vi.fn();
    render(
      <MemoryRouter initialEntries={["/monitors"]}>
        <I18nProvider>
          <WatchlistRail
            activeSymbol={null}
            instruments={[instrument]}
            opendConnected
            busyCode={null}
            adding={false}
            onAdd={vi.fn()}
            onToggle={onToggle}
            onDelete={onDelete}
          />
          <LocationProbe />
        </I18nProvider>
      </MemoryRouter>,
    );

    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: /停用 US\.AAPL|Disable monitoring for US\.AAPL/ }));
    expect(onToggle).toHaveBeenCalledWith(instrument);

    fireEvent.click(screen.getByRole("button", { name: /移除 US\.AAPL|Remove US\.AAPL/ }));
    expect(onDelete).toHaveBeenCalledWith(instrument);

    fireEvent.click(screen.getByRole("link", { name: /US\.AAPL.*Apple/s }));
    await waitFor(() =>
      expect(screen.getByLabelText("path")).toHaveTextContent("/monitors/US.AAPL"),
    );
  });
});
