export const workspacePaths = {
  backtest: "/backtests",
  backtestNew: "/backtests/new",
  backtestNewForSymbol: (code: string) =>
    `/backtests/new?symbol=${encodeURIComponent(code.trim().toUpperCase())}`,
  backtestDetail: (jobId: string) => `/backtests/${encodeURIComponent(jobId)}`,
  iterate: "/experiments",
  experimentNew: "/experiments/new",
  experimentDetail: (experimentId: string) =>
    `/experiments/${encodeURIComponent(experimentId)}`,
  strategies: "/strategies",
  portfolios: "/portfolios",
  monitors: "/monitors",
  monitorSymbol: (code: string) =>
    `/monitors/${encodeURIComponent(code)}`,
  monitorOptions: (code: string) =>
    `/monitors/${encodeURIComponent(code)}/options`,
  monitorContract: (code: string, contractCode: string) =>
    `/monitors/${encodeURIComponent(code)}/options/${encodeURIComponent(contractCode)}`,
  monitorAlerts: (code: string) =>
    `/monitors/${encodeURIComponent(code)}/alerts`,
  strategyDetail: (path: string) =>
    `/strategies/${path.split("/").map(encodeURIComponent).join("/")}`,
} as const;
