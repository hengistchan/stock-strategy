import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { MonitorBar } from "../../api/types";
import { I18nProvider } from "../../i18n/I18nProvider";
import { MonitorTapeChart } from "./MonitorTapeChart";

const bars: MonitorBar[] = [
  {
    code: "US.AAPL",
    source_time: "2026-07-28 09:35:00",
    ktype: "K_5M",
    open: 100,
    high: 102,
    low: 99,
    close: 101,
    volume: 1000,
    is_closed: true,
  },
  {
    code: "US.AAPL",
    source_time: "2026-07-28 09:40:00",
    ktype: "K_5M",
    open: 101,
    high: 103,
    low: 100,
    close: 102,
    volume: 1200,
    is_closed: false,
  },
];

describe("MonitorTapeChart", () => {
  it("exposes the latest bar and supports arrow, Home, and End navigation", () => {
    render(
      <I18nProvider>
        <MonitorTapeChart bars={bars} symbol="US.AAPL" />
      </I18nProvider>,
    );

    const chart = screen.getByRole("img");
    expect(
      screen.getByText("2026-07-28 09:40:00", {
        selector: ".monitor-tape-readout strong",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("102.00")).toBeInTheDocument();

    fireEvent.keyDown(chart, { key: "ArrowLeft" });
    expect(
      screen.getByText("2026-07-28 09:35:00", {
        selector: ".monitor-tape-readout strong",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("101.00")).toBeInTheDocument();

    fireEvent.keyDown(chart, { key: "End" });
    expect(
      screen.getByText("2026-07-28 09:40:00", {
        selector: ".monitor-tape-readout strong",
      }),
    ).toBeInTheDocument();

    fireEvent.keyDown(chart, { key: "Home" });
    expect(
      screen.getByText("2026-07-28 09:35:00", {
        selector: ".monitor-tape-readout strong",
      }),
    ).toBeInTheDocument();
  });

  it("drops incomplete bars instead of plotting invalid coordinates", () => {
    render(
      <I18nProvider>
        <MonitorTapeChart
          symbol="US.AAPL"
          bars={[{ ...bars[0], high: null }]}
        />
      </I18nProvider>,
    );

    expect(screen.getByText(/暂未返回可绘制|has not returned/)).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
