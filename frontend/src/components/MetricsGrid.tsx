import type { BacktestMetrics } from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import { formatCurrency, formatNumber, formatSignedPercent } from "../lib/format";

interface MetricsGridProps {
  metrics: BacktestMetrics;
}

function tone(value: number): string {
  return value > 0 ? "positive" : value < 0 ? "negative" : "";
}

export function MetricsGrid({ metrics }: MetricsGridProps) {
  const { locale, t } = useI18n();
  return (
    <div className="metric-ledger">
      <div className="metric-primary"><span>{t("metrics.return")}</span><strong className={tone(metrics.total_return_pct)}>{formatSignedPercent(metrics.total_return_pct, locale)}</strong></div>
      <div><span>{t("metrics.benchmark")}</span><strong className={tone(metrics.benchmark_return_pct)}>{formatSignedPercent(metrics.benchmark_return_pct, locale)}</strong></div>
      <div><span>{t("metrics.drawdown")}</span><strong className={tone(metrics.max_drawdown_pct)}>{formatSignedPercent(metrics.max_drawdown_pct, locale)}</strong></div>
      <div><span>Sharpe</span><strong className={tone(metrics.sharpe_ratio)}>{formatNumber(metrics.sharpe_ratio, 2, locale)}</strong></div>
      <div><span>{t("metrics.trades")}</span><strong>{formatNumber(metrics.total_trades, 0, locale)}</strong></div>
      <div><span>{t("metrics.fees")}</span><strong>{formatCurrency(metrics.total_fees, locale)}</strong></div>
    </div>
  );
}
