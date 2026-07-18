import type { BacktestMetrics } from "../api/types";
import { formatCurrency, formatNumber, formatSignedPercent } from "../lib/format";

interface MetricsGridProps {
  metrics: BacktestMetrics;
}

function tone(value: number): string {
  return value > 0 ? "positive" : value < 0 ? "negative" : "";
}

export function MetricsGrid({ metrics }: MetricsGridProps) {
  return (
    <div className="metric-ledger">
      <div className="metric-primary"><span>策略收益</span><strong className={tone(metrics.total_return_pct)}>{formatSignedPercent(metrics.total_return_pct)}</strong></div>
      <div><span>买入持有</span><strong className={tone(metrics.benchmark_return_pct)}>{formatSignedPercent(metrics.benchmark_return_pct)}</strong></div>
      <div><span>最大回撤</span><strong className={tone(metrics.max_drawdown_pct)}>{formatSignedPercent(metrics.max_drawdown_pct)}</strong></div>
      <div><span>Sharpe</span><strong className={tone(metrics.sharpe_ratio)}>{formatNumber(metrics.sharpe_ratio, 2)}</strong></div>
      <div><span>闭合交易</span><strong>{formatNumber(metrics.total_trades, 0)}</strong></div>
      <div><span>总费用</span><strong>{formatCurrency(metrics.total_fees)}</strong></div>
    </div>
  );
}
