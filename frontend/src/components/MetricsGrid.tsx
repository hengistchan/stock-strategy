import type { BacktestMetrics } from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import type { Locale } from "../i18n/core";
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
    <>
      <div className="metric-ledger">
        <div className="metric-primary"><span>{t("metrics.return")}</span><strong className={tone(metrics.total_return_pct)}>{formatSignedPercent(metrics.total_return_pct, locale)}</strong></div>
        <div><span>{t("metrics.benchmark")}</span><strong className={tone(metrics.benchmark_return_pct)}>{formatSignedPercent(metrics.benchmark_return_pct, locale)}</strong></div>
        <div><span>{t("metrics.drawdown")}</span><strong className={tone(metrics.max_drawdown_pct)}>{formatSignedPercent(metrics.max_drawdown_pct, locale)}</strong></div>
        <div><span>Sharpe</span><strong className={tone(metrics.sharpe_ratio)}>{formatNumber(metrics.sharpe_ratio, 2, locale)}</strong></div>
        <div><span>{t("metrics.trades")}</span><strong>{formatNumber(metrics.total_trades, 0, locale)}</strong></div>
        <div><span>{t("metrics.fees")}</span><strong>{formatCurrency(metrics.total_fees, locale)}</strong></div>
      </div>
      <details className="metric-details">
        <summary>{t("metrics.extended")}</summary>
        <dl>
          <ExtendedMetric label="Sortino" value={metrics.sortino_ratio} locale={locale} />
          <ExtendedMetric label="Calmar" value={metrics.calmar_ratio} locale={locale} />
          <ExtendedMetric label={t("metrics.volatility")} value={metrics.annualized_volatility_pct} locale={locale} percent />
          <ExtendedMetric label="Alpha" value={metrics.alpha_pct} locale={locale} percent />
          <ExtendedMetric label="Beta" value={metrics.beta} locale={locale} />
          <ExtendedMetric label={t("metrics.informationRatio")} value={metrics.information_ratio} locale={locale} />
          <ExtendedMetric label={t("metrics.expectancy")} value={metrics.expectancy} locale={locale} currency />
          <ExtendedMetric label={t("metrics.winLossRatio")} value={metrics.average_win_loss_ratio} locale={locale} />
          <ExtendedMetric label={t("metrics.holdingBars")} value={metrics.average_holding_bars} locale={locale} />
          <ExtendedMetric label={t("metrics.lossStreak")} value={metrics.max_consecutive_losses} locale={locale} digits={0} />
          <ExtendedMetric label={t("metrics.drawdownDuration")} value={metrics.max_drawdown_duration_days} locale={locale} digits={0} />
          <ExtendedMetric label={t("metrics.recoveryFactor")} value={metrics.recovery_factor} locale={locale} />
          <ExtendedMetric label={t("metrics.turnover")} value={metrics.turnover_pct} locale={locale} percent />
        </dl>
      </details>
    </>
  );
}

function ExtendedMetric({
  label,
  value,
  locale,
  percent = false,
  currency = false,
  digits = 2,
}: {
  label: string;
  value: number | null | undefined;
  locale: Locale;
  percent?: boolean;
  currency?: boolean;
  digits?: number;
}) {
  const formatted = value === null || value === undefined
    ? "—"
    : currency
      ? formatCurrency(value, locale)
      : percent
        ? formatSignedPercent(value, locale)
        : formatNumber(value, digits, locale);
  return <div><dt>{label}</dt><dd>{formatted}</dd></div>;
}
