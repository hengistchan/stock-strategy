import type { BacktestJob } from "../api/types";

export type BacktestRail = "archive" | "create";

export function resolveVisibleJobId(
  rail: BacktestRail,
  activeJobId: string | null,
  jobs: BacktestJob[],
): string | null {
  if (rail === "create") return null;

  return activeJobId
    ?? jobs.find((job) => job.status === "succeeded")?.id
    ?? jobs[0]?.id
    ?? null;
}
