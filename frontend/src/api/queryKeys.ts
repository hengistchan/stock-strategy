export const queryKeys = {
  health: ["health"] as const,
  diagnostics: ["diagnostics"] as const,
  config: ["config"] as const,
  strategies: ["strategies"] as const,
  strategy: (path: string) => ["strategy", path] as const,
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
};
