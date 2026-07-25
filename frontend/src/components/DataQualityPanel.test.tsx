import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DataQualityPanel } from "./DataQualityPanel";

describe("DataQualityPanel", () => {
  it("distinguishes suspected calendar gaps from confirmed missing data", () => {
    render(<DataQualityPanel report={{
      rows: 100,
      duplicates: 0,
      missing_intervals: 2,
      missing_interval_samples: ["2025-01-20"],
      timezone: "America/New_York",
      calendar: "us-weekday-approximation-v1",
      calendar_precision: "approximate",
      corporate_actions_applied: true,
      corporate_action_mode: "delegated_to_opend_adjustment",
      adjustment: "QFQ",
      suspicious_price_jumps: [],
      source: "opend",
      source_version: "10.6",
      fx_conversion: "not_required_single_currency",
    }} />);

    fireEvent.click(screen.getByText("行情质量报告"));
    expect(screen.getByText(/节假日可能被计入疑似缺口/)).toBeInTheDocument();
    expect(screen.getByText("QFQ · delegated_to_opend_adjustment")).toBeInTheDocument();
  });
});
