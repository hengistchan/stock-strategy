export const queryKeys = {
  health: ["health"] as const,
  diagnostics: ["diagnostics"] as const,
  config: ["config"] as const,
  strategies: ["strategies"] as const,
  strategy: (path: string) => ["strategy", path] as const,
  strategyVersions: (path: string) => ["strategy-versions", path] as const,
  jobs: ["jobs"] as const,
  job: (jobId: string | null) => ["job", jobId] as const,
  result: (jobId: string | null) => ["result", jobId] as const,
  prices: (jobId: string, offset: number, limit: number) =>
    ["prices", jobId, offset, limit] as const,
  experiments: ["experiments"] as const,
  experiment: (experimentId: string | null) =>
    ["experiment", experimentId] as const,
  cache: ["cache"] as const,
  symbolNames: (symbols: string[]) => ["symbol-names", symbols] as const,
  monitoring: ["monitoring"] as const,
  monitoringStatus: ["monitoring", "status"] as const,
  monitoringDiagnostics: ["monitoring", "diagnostics"] as const,
  watchlist: ["monitoring", "watchlist"] as const,
  monitorSnapshot: (code: string | null) =>
    ["monitoring", "snapshot", code] as const,
  monitorBars: (code: string | null, count: number, ktype: string) =>
    ["monitoring", "bars", code, count, ktype] as const,
  optionExpirations: (code: string | null) =>
    ["monitoring", "option-expirations", code] as const,
  optionChain: (code: string | null, expiration: string | null) =>
    ["monitoring", "option-chain", code, expiration] as const,
  optionContract: (code: string | null) =>
    ["monitoring", "option-contract", code] as const,
  monitorRules: (code?: string) =>
    ["monitoring", "rules", code ?? "all"] as const,
  monitorAlerts: (code?: string, unacknowledgedOnly = false) =>
    ["monitoring", "alerts", code ?? "all", unacknowledgedOnly] as const,
};
