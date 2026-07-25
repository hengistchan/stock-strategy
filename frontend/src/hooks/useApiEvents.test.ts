import { describe, expect, it } from "vitest";
import { parseStateEvent } from "./useApiEvents";


describe("parseStateEvent", () => {
  it("accepts state events and rejects malformed payloads", () => {
    expect(
      parseStateEvent(
        new MessageEvent("job.updated", {
          data: JSON.stringify({ id: "job-1", status: "running" }),
        }),
      ),
    ).toEqual({ id: "job-1", status: "running" });
    expect(
      parseStateEvent(new MessageEvent("job.updated", { data: "not-json" })),
    ).toBeNull();
    expect(
      parseStateEvent(
        new MessageEvent("job.updated", {
          data: JSON.stringify({ id: 1, status: "running" }),
        }),
      ),
    ).toBeNull();
  });
});
