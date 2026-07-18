export type JobStatus = "queued" | "running" | "succeeded" | "failed";
export type ParameterValue = boolean | number | string;

export interface StrategyParameterDefinition {
  name: string;
  label: string;
  label_i18n?: Record<string, string>;
  description: string;
  description_i18n?: Record<string, string>;
  type: "int" | "float" | "bool" | "string";
  default: ParameterValue;
  min?: number;
  max?: number;
  step?: number;
  choices?: ParameterValue[];
  candidates: ParameterValue[];
}

export interface StrategyMetadata {
  path: string;
  name: string;
  group: string;
  readonly: boolean;
  revision: string;
  size: number;
  updated_at: string;
  parameters?: StrategyParameterDefinition[];
}

export interface StrategyDocument extends StrategyMetadata {
  content: string;
}

export interface AppConfig {
  strategies: StrategyMetadata[];
  kline_types: string[];
  adjustment_types: string[];
  session_types: string[];
}

export interface HealthResponse {
  status: string;
  opend: {
    connected: boolean;
    host: string;
    port: number;
  };
}

export interface BacktestRequest {
  strategy: string;
  symbol: string;
  start: string;
  end: string;
  ktype: string;
  autype: string;
  session?: string;
  initial_cash: number;
  commission_bps: number;
  min_commission: number;
  slippage_bps: number;
  warmup_bars: number;
  allow_short: boolean;
  liquidate_on_end?: boolean;
  parameters?: Record<string, ParameterValue>;
  refresh_cache?: boolean;
}

export interface BacktestJob {
  id: string;
  status: JobStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  request: BacktestRequest;
  strategy_path: string;
  run_dir: string | null;
  stdout: string;
  stderr: string;
  error: string | null;
}

export interface PricePoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Trade {
  trade_id: number;
  symbol: string;
  side: string;
  entry_date: string;
  exit_date: string;
  entry_price: number;
  exit_price: number;
  quantity: number;
  gross_pnl: number;
  fees: number;
  net_pnl: number;
  return_pct: number;
  bars_held: number;
  exit_reason: string;
}

export interface BacktestMetrics {
  total_return_pct: number;
  benchmark_return_pct: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  total_trades: number;
  total_fees: number;
  exposure_pct: number;
  [key: string]: number;
}

export interface BacktestSummary {
  strategy: string;
  symbol: string;
  period: {
    start: string;
    end: string;
    bars: number;
  };
  settings: {
    engine_contract?: {
      version: number;
      strict_single_period: boolean;
      day_order_scope: string;
      end_position_policy: string;
    };
    ending_position?: {
      quantity: number;
      side: string;
      average_price: number;
      mark_price: number;
      unrealized_pnl: number;
    };
    opend?: {
      ktype: string;
      autype: string;
      session?: string;
      extended_time?: boolean;
      cache_path: string;
    };
    [key: string]: unknown;
  };
  metrics: BacktestMetrics;
}

export interface BacktestResult {
  job: BacktestJob;
  summary: BacktestSummary;
  price_series: PricePoint[];
  trades: Trade[];
  equity_curve: Array<Record<string, number | string>>;
  report_url: string;
}

export interface JobsResponse {
  jobs: BacktestJob[];
}

export interface StrategiesResponse {
  strategies: StrategyMetadata[];
}

export type ExperimentObjective =
  | "total_return_pct"
  | "sharpe_ratio"
  | "max_drawdown_pct";

export interface ExperimentRequest {
  name: string;
  base: BacktestRequest;
  parameter_grid: Record<string, ParameterValue[]>;
  objective: ExperimentObjective;
}

export interface ExperimentRun {
  index: number;
  parameters: Record<string, ParameterValue>;
  job_id: string | null;
  status: JobStatus;
  metrics: BacktestMetrics | null;
  score: number | null;
  rank: number | null;
  error: string | null;
}

export interface Experiment {
  id: string;
  name: string;
  status: JobStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  objective: ExperimentObjective;
  base_request: BacktestRequest;
  parameter_grid: Record<string, ParameterValue[]>;
  strategy_path: string;
  progress: { completed: number; total: number };
  runs: ExperimentRun[];
}

export interface ExperimentsResponse {
  experiments: Experiment[];
}

export interface CacheEntry {
  id: string;
  symbol: string;
  start: string;
  end: string;
  ktype: string;
  autype: string;
  session: string;
  path: string;
  bytes: number;
  rows: number;
  first_time: string | null;
  last_time: string | null;
  updated_at: string;
}

export interface CacheResponse {
  entries: CacheEntry[];
  total_bytes: number;
}
