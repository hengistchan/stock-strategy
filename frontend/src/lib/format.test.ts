import { describe, expect, it } from "vitest";
import { formatMarketTimestamp, isIntradayKline, marketTimeKey } from "./format";

describe("market time formatting", () => {
  it("keeps minute precision for intraday OpenD bars", () => {
    expect(formatMarketTimestamp("2025-12-31 14:15:00", "K_5M")).toBe(
      "2025-12-31 14:15",
    );
  });

  it("uses date precision for daily bars", () => {
    expect(formatMarketTimestamp("2025-12-31 00:00:00", "K_DAY")).toBe(
      "2025-12-31",
    );
  });

  it("normalizes ISO timestamps for trade marker matching", () => {
    expect(marketTimeKey("2025-12-31T14:15:00+08:00")).toBe(
      "2025-12-31 14:15:00",
    );
    expect(isIntradayKline("K_60M")).toBe(true);
  });

  it("keeps time precision for every supported multi-hour K-line", () => {
    expect(formatMarketTimestamp("2025-12-31 13:45:00", "K_10M")).toBe(
      "2025-12-31 13:45",
    );
    expect(formatMarketTimestamp("2025-12-31 13:45:00", "K_240M")).toBe(
      "2025-12-31 13:45",
    );
  });
});
