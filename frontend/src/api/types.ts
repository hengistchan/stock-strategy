export type JobStatus =
  | "queued"
  | "running"
  | "cancelling"
  | "succeeded"
  | "failed"
  | "cancelled";
export type ExperimentStatus = JobStatus | "completed_with_errors";
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
  compatibility?: StrategyCompatibility;
}

export interface StrategyCompatibility {
  supported: boolean;
  issues: Array<"unsupported_names" | "multiple_session_types">;
  unsupported_names: string[];
  bar_types: string[];
  driver_bar_type?: string | null;
  session_types?: string[];
  required_session?: string | null;
}

export interface StrategyDocument extends StrategyMetadata {
  content: string;
}

export interface StrategyVersion {
  id: string;
  revision: string;
  created_at: string;
  reason: "created" | "saved" | "restored" | "imported";
  source_path: string;
  current: boolean;
  backtest_count: number;
  experiment_count: number;
}

export interface StrategyVersionsResponse {
  strategy_path: string;
  versions: StrategyVersion[];
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

export type DiagnosticStatus = "pass" | "fail" | "blocked";

export interface DiagnosticCheck {
  id: "python" | "futu_api" | "workspace" | "opend" | "quote_directory";
  status: DiagnosticStatus;
  detail: string;
  hint: string | null;
}

export interface DiagnosticsResponse {
  ready: boolean;
  host: string;
  port: number;
  checks: DiagnosticCheck[];
}

export interface SymbolMatch {
  code: string;
  name: string;
  market: string;
}

export interface SymbolSearchResponse {
  query: string;
  symbols: SymbolMatch[];
}

export interface SymbolResolveResponse {
  symbols: SymbolMatch[];
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
  fee_model?: "simple" | "futu_auto" | "futu_us" | "futu_hk";
  slippage_model?: "bps" | "spread";
  execution_model?: "deterministic" | "volume" | "conservative";
  max_volume_participation?: number;
  spread_bps?: number;
  impact_bps?: number;
  fixed_tick?: number;
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
  strategy_revision?: string;
  strategy_snapshot_path?: string;
  market_data_path?: string | null;
  retry_of?: string | null;
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

export interface PriceWindow {
  offset: number;
  total: number;
  points: PricePoint[];
}

export interface EquityPoint {
  date: string;
  equity: number;
  benchmark: number;
  drawdown: number;
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
  annualized_return_pct?: number | null;
  [key: string]: number | null | undefined;
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
    market_metadata?: {
      name?: string;
      [key: string]: unknown;
    };
    market_data_quality?: MarketDataQualityReport;
    [key: string]: unknown;
  };
  metrics: BacktestMetrics;
}

export interface MarketDataQualityReport {
  rows: number;
  duplicates: number;
  missing_intervals: number;
  missing_interval_samples: string[];
  timezone: string;
  calendar: string;
  calendar_precision: "exact" | "approximate";
  corporate_actions_applied: boolean;
  corporate_action_mode: string;
  adjustment: string;
  suspicious_price_jumps: Array<{
    from: string;
    to: string;
    change_pct: number;
  }>;
  source: string;
  source_version: string;
  fx_conversion: string;
}

export interface BacktestResult {
  job: BacktestJob;
  summary: BacktestSummary;
  price_series: PricePoint[];
  price_series_offset: number;
  price_series_count: number;
  price_overview: PricePoint[];
  trades: Trade[];
  equity_curve: EquityPoint[];
  equity_curve_count: number;
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

export type ConstraintMetric =
  | "total_return_pct"
  | "sharpe_ratio"
  | "max_drawdown_pct"
  | "total_trades"
  | "total_fees"
  | "exposure_pct";

export interface MetricConstraint {
  metric: ConstraintMetric;
  op: ">=" | "<=";
  value: number;
}

export interface ExperimentRequest {
  name: string;
  base: BacktestRequest;
  parameter_grid: Record<string, ParameterValue[]>;
  objective: ExperimentObjective;
  validation?: EvaluationWindow;
  test?: EvaluationWindow;
  walk_forward_folds?: number;
  constraints?: MetricConstraint[];
  symbols?: string[];
}

export interface EvaluationWindow {
  start: string;
  end: string;
}

export interface ExperimentPhase {
  job_id: string | null;
  status: JobStatus;
  metrics: BacktestMetrics | null;
  error: string | null;
  window: EvaluationWindow;
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
  phases?: Record<string, ExperimentPhase>;
  constraints_satisfied?: boolean | null;
  constraint_violations?: Array<MetricConstraint & { actual?: number | null }>;
  pareto_optimal?: boolean;
  symbol?: string | null;
}

export interface Experiment {
  id: string;
  name: string;
  status: ExperimentStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  objective: ExperimentObjective;
  kind?: "parameter_search" | "batch_validation";
  constraints?: MetricConstraint[];
  symbols?: string[];
  base_request: BacktestRequest;
  validation_window?: EvaluationWindow | null;
  test_window?: EvaluationWindow | null;
  walk_forward_folds?: number;
  walk_forward_windows?: Array<{
    train: EvaluationWindow;
    validation: EvaluationWindow;
  }>;
  parameter_grid: Record<string, ParameterValue[]>;
  strategy_path: string;
  progress: { completed: number; total: number };
  runs: ExperimentRun[];
  research_summary?: {
    mode: "in_sample" | "train_validation_test" | "walk_forward" | "batch_validation";
    selected_parameters: Record<string, ParameterValue> | null;
    out_of_sample: boolean;
    validation_metrics?: BacktestMetrics | null;
    test_metrics?: BacktestMetrics | null;
    positive_window_ratio?: number | null;
    worst_window_drawdown_pct?: number | null;
    parameter_stability?: number | null;
    window_results?: Array<{
      window: EvaluationWindow;
      metrics: BacktestMetrics;
    }>;
    symbol_count?: number;
    successful_symbol_count?: number;
    positive_symbol_ratio?: number | null;
    median_return_pct?: number | null;
    median_sharpe_ratio?: number | null;
    worst_symbol?: string | null;
    worst_symbol_return_pct?: number | null;
  };
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

export interface PortfolioRequest {
  weights: Record<string, number>;
  start: string;
  end: string;
  initial_cash: number;
  commission_bps: number;
  min_commission: number;
  slippage_bps: number;
  rebalance: "buy_and_hold" | "monthly" | "quarterly";
  ktype: "K_DAY";
  autype: "QFQ" | "HFQ" | "NONE";
  session: "ALL" | "RTH" | "ETH";
}

export interface PortfolioResult {
  id: string;
  created_at: string;
  source: "opend";
  request: PortfolioRequest;
  market_data_sha256: Record<string, string>;
  metrics: BacktestMetrics;
  period: { start: string; end: string; bars: number };
  weights: Record<string, number>;
  positions: Array<{
    symbol: string;
    quantity: number;
    mark_price: number;
    market_value: number;
  }>;
  cash: number;
  transactions: Array<{
    date: string;
    symbol: string;
    side: "BUY" | "SELL";
    quantity: number;
    price: number;
    fee: number;
    notional: number;
  }>;
  equity_curve: EquityPoint[];
  engine_contract: {
    shared_cash: boolean;
    unified_clock: string;
    integer_shares: boolean;
    execution: string;
    currency: string;
  };
}

export interface CacheResponse {
  entries: CacheEntry[];
  total_bytes: number;
}
