import { describe, expect, it } from "vitest";
import {
  FUTU_SYMBOL_HTML_PATTERN,
  formatSymbolLabel,
  normalizeFutuSymbol,
} from "./symbols";

describe("formatSymbolLabel", () => {
  it("appends an OpenD name and keeps a code-only fallback", () => {
    expect(formatSymbolLabel("US.AAPL", { "US.AAPL": "苹果" })).toBe("US.AAPL · 苹果");
    expect(formatSymbolLabel("US.MISSING", {})).toBe("US.MISSING");
  });

  it("normalizes valid Futu codes and rejects free-form input", () => {
    expect(normalizeFutuSymbol(" hk.00700 ")).toBe("HK.00700");
    expect(normalizeFutuSymbol("US.AAPL260731C100000")).toBe(
      "US.AAPL260731C100000",
    );
    expect(normalizeFutuSymbol("Apple")).toBeNull();
    expect(normalizeFutuSymbol("U.AAPL")).toBeNull();
  });

  it("keeps the browser pattern valid under Unicode Sets semantics", () => {
    const browserPattern = new RegExp(
      `^(?:${FUTU_SYMBOL_HTML_PATTERN})$`,
      "v",
    );
    expect(browserPattern.test("US.BRK-B")).toBe(true);
    expect(browserPattern.test("Apple")).toBe(false);
  });
});
