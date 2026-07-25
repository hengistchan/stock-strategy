import type { PerformanceAnalysis } from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import type { Locale } from "../i18n/core";
import type { TranslationKey } from "../i18n/translations";
import { formatNumber, formatSignedPercent } from "../lib/format";

interface PerformanceDistributionPanelProps {
  analysis: PerformanceAnalysis;
}

const regimeKeys: Record<string, TranslationKey> = {
  up: "distribution.regime.up",
  down: "distribution.regime.down",
  flat: "distribution.regime.flat",
};

function tone(value: number | null): string {
  return value === null ? "" : value > 0 ? "positive" : value < 0 ? "negative" : "";
}

export function PerformanceDistributionPanel({
  analysis,
}: PerformanceDistributionPanelProps) {
  const { locale, t } = useI18n();
  const returns = analysis.return_distribution;
  const drawdowns = analysis.drawdown_distribution;
  const latestRolling = analysis.rolling.at(-1);
  const recentMonths = analysis.monthly_returns.slice(-12);

  return (
    <section className="distribution-panel" aria-label={t("distribution.title")}>
      <header>
        <div>
          <span className="section-code">DISTRIBUTION</span>
          <h3>{t("distribution.title")}</h3>
        </div>
        <p>{t("distribution.subtitle")}</p>
      </header>

      <div className="distribution-summary">
        <Metric label={t("distribution.returnP10")} value={returns.p10} percent locale={locale} />
        <Metric label={t("distribution.returnMedian")} value={returns.median} percent locale={locale} />
        <Metric label={t("distribution.returnP90")} value={returns.p90} percent locale={locale} />
        <Metric label={t("distribution.returnVolatility")} value={returns.std} percent locale={locale} />
        <Metric label={t("distribution.drawdownP10")} value={drawdowns.p10} percent locale={locale} />
        <Metric label={t("distribution.rollingSharpe")} value={latestRolling?.sharpe_ratio ?? null} locale={locale} />
      </div>

      <div className="distribution-sections">
        <div>
          <h4>{t("distribution.monthly")}</h4>
          {recentMonths.length ? (
            <div className="period-return-grid">
              {recentMonths.map((row) => (
                <div key={row.period}>
                  <span>{row.period}</span>
                  <strong className={tone(row.return_pct)}>
                    {formatSignedPercent(row.return_pct, locale)}
                  </strong>
                </div>
              ))}
            </div>
          ) : <p className="distribution-empty">{t("distribution.noData")}</p>}
        </div>

        <div>
          <h4>{t("distribution.regimes")}</h4>
          {analysis.attribution.market_regime.length ? (
            <dl className="regime-list">
              {analysis.attribution.market_regime.map((row) => (
                <div key={row.bucket}>
                  <dt>{t(regimeKeys[row.bucket] ?? "distribution.regime.flat")}</dt>
                  <dd className={tone(row.return_pct)}>
                    {formatSignedPercent(row.return_pct, locale)}
                    <small>{t("distribution.observations", { count: row.observations })}</small>
                  </dd>
                </div>
              ))}
            </dl>
          ) : <p className="distribution-empty">{t("distribution.noData")}</p>}
        </div>
      </div>
    </section>
  );
}

function Metric({
  label,
  value,
  percent = false,
  locale,
}: {
  label: string;
  value: number | null;
  percent?: boolean;
  locale: Locale;
}) {
  return (
    <div>
      <span>{label}</span>
      <strong className={tone(value)}>
        {value === null
          ? "—"
          : percent
            ? formatSignedPercent(value, locale)
            : formatNumber(value, 2, locale)}
      </strong>
    </div>
  );
}
