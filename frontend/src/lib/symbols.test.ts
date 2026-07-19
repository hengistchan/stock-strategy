import { describe, expect, it } from "vitest";
import { formatSymbolLabel } from "./symbols";

describe("formatSymbolLabel", () => {
  it("appends an OpenD name and keeps a code-only fallback", () => {
    expect(formatSymbolLabel("US.AAPL", { "US.AAPL": "苹果" })).toBe("US.AAPL · 苹果");
    expect(formatSymbolLabel("US.MISSING", {})).toBe("US.MISSING");
  });
});
