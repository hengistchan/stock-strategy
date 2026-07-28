import { describe, expect, it } from "vitest";
import { ApiError } from "../../api/client";
import { classifyMonitorError } from "./monitorError";

describe("classifyMonitorError", () => {
  it("keeps permission, quota, offline, and unavailable states distinct", () => {
    expect(
      classifyMonitorError(
        new ApiError("permission denied", 503, "market_data_permission_denied"),
      ),
    ).toBe("permission");
    expect(
      classifyMonitorError(
        new ApiError("quota exhausted", 503, "market_data_quota_exhausted"),
      ),
    ).toBe("quota");
    expect(
      classifyMonitorError(
        new ApiError("OpenD unavailable", 503, "opend_unavailable"),
      ),
    ).toBe("offline");
    expect(
      classifyMonitorError(
        new ApiError("missing chain", 404, "option_chain_not_found"),
      ),
    ).toBe("unavailable");
  });

  it("falls back to a generic error for unknown failures", () => {
    expect(classifyMonitorError(new Error("network failed"))).toBe("error");
    expect(
      classifyMonitorError(new ApiError("failed", 503, "market_data_request_failed")),
    ).toBe("error");
  });
});
