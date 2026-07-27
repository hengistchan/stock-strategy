export const workspacePaths = {
  backtest: "/backtests",
  backtestNew: "/backtests/new",
  backtestDetail: (jobId: string) => `/backtests/${encodeURIComponent(jobId)}`,
  iterate: "/experiments",
  experimentNew: "/experiments/new",
  experimentDetail: (experimentId: string) =>
    `/experiments/${encodeURIComponent(experimentId)}`,
  strategies: "/strategies",
  portfolios: "/portfolios",
  monitors: "/monitors",
  strategyDetail: (path: string) =>
    `/strategies/${path.split("/").map(encodeURIComponent).join("/")}`,
} as const;
