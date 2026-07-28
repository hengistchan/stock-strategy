import { describe, expect, it } from "vitest";
import {
  MONITOR_MISSING_VALUE,
  formatGreek,
  formatMonitorInteger,
  formatMonitorPrice,
  formatMonitorRatio,
  formatOptionIv,
  formatQuoteTimestamp,
} from "./formatters";

describe("monitor formatters", () => {
  it("treats Futu option IV as percentage points without multiplying by 100", () => {
    expect(formatOptionIv(20, "en-US")).toBe("20.00%");
    expect(formatOptionIv(0.2, "en-US")).toBe("0.20%");
  });

  it("formats Greeks and monitor quantities at their domain precision", () => {
    expect(formatGreek(0.523456, "en-US")).toBe("0.5235");
    expect(formatGreek(-0.0123, "en-US")).toBe("-0.0123");
    expect(formatMonitorPrice(0.125, "en-US")).toBe("0.1250");
    expect(formatMonitorPrice(125.5, "en-US")).toBe("125.50");
    expect(formatMonitorInteger(12345, "en-US")).toBe("12,345");
    expect(formatMonitorRatio(1.5, "en-US")).toBe("1.50×");
  });

  it("uses an em dash for absent, invalid, and non-finite values", () => {
    for (const value of [null, undefined, "", "N/A", "NaN", Number.NaN, Infinity]) {
      expect(formatOptionIv(value, "en-US")).toBe(MONITOR_MISSING_VALUE);
      expect(formatGreek(value, "en-US")).toBe(MONITOR_MISSING_VALUE);
    }
    expect(formatMonitorPrice(-1, "en-US")).toBe(MONITOR_MISSING_VALUE);
    expect(formatMonitorInteger(-1, "en-US")).toBe(MONITOR_MISSING_VALUE);
    expect(formatMonitorRatio(-1, "en-US")).toBe(MONITOR_MISSING_VALUE);
  });

  it("preserves valid OpenD market wall-clock time without timezone conversion", () => {
    expect(formatQuoteTimestamp("2026-07-27 10:30:05")).toBe(
      "2026-07-27 10:30:05",
    );
    expect(formatQuoteTimestamp("2026-07-27T10:30:05+08:00")).toBe(
      "2026-07-27 10:30:05",
    );
    expect(formatQuoteTimestamp("2026-07-27")).toBe("2026-07-27");
  });

  it("rejects missing and impossible source timestamps", () => {
    expect(formatQuoteTimestamp("N/A")).toBe(MONITOR_MISSING_VALUE);
    expect(formatQuoteTimestamp("not-a-date")).toBe(MONITOR_MISSING_VALUE);
    expect(formatQuoteTimestamp("2026-02-30 10:30:00")).toBe(
      MONITOR_MISSING_VALUE,
    );
    expect(formatQuoteTimestamp("2026-07-27 25:00:00")).toBe(
      MONITOR_MISSING_VALUE,
    );
  });
});
