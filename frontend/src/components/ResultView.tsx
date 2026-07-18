import type { BacktestJob, BacktestResult } from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import { formatDateTime, formatNumber, formatSignedCurrency, shortDate } from "../lib/format";
import { MetricsGrid } from "./MetricsGrid";
import { PriceChart } from "./PriceChart";
import { TradeTable } from "./TradeTable";

interface ResultViewProps {
  job?: BacktestJob;
  result?: BacktestResult;
  loading: boolean;
  emptyContext?: "archive" | "create";
}

export function ResultView({ job, result, loading, emptyContext = "archive" }: ResultViewProps) {
  const { locale, t } = useI18n();
  if (!job) {
    const isCreating = emptyContext === "create";
    return (
      <section className="result-empty">
        <div className="empty-plot" aria-hidden="true"><span /><span /><span /><span /><span /><i /></div>
        <div>
          <p className="eyebrow">{t(isCreating ? "result.newBacktestLabel" : "result.noRun")}</p>
          <h2>{t(isCreating ? "result.newBacktestTitle" : "result.emptyTitle")}</h2>
          <p>{t(isCreating ? "result.newBacktestBody" : "result.emptyBody")}</p>
        </div>
      </section>
    );
  }

  if (job.status !== "succeeded" || loading || !result) {
    const stderrDetail = job.stderr.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).at(-1);
    const copy = {
      queued: [t("result.queuedLabel"), t("result.queuedTitle"), t("result.queuedBody")],
      running: [t("result.runningLabel"), t("result.runningTitle", { symbol: job.request.symbol }), `${job.request.start} → ${job.request.end} · ${job.request.ktype}`],
      failed: [t("result.failedLabel"), t("result.failedTitle"), stderrDetail ?? job.error ?? t("result.failedBody")],
      succeeded: [t("result.succeededLabel"), t("result.succeededTitle"), t("result.succeededBody")],
    }[job.status];
    return (
      <section className="job-state" data-status={job.status}>
        <div className="job-state-mark" aria-hidden="true"><span /></div>
        <div><p className="eyebrow">{copy[0]}</p><h2>{copy[1]}</h2><p>{copy[2]}</p></div>
      </section>
    );
  }

  const { summary, trades, price_series: priceSeries } = result;
  const ktype = summary.settings.opend?.ktype ?? job.request.ktype;
  const autype = summary.settings.opend?.autype ?? job.request.autype;
  const session = summary.settings.opend?.session ?? job.request.session ?? "ALL";
  const endingPosition = summary.settings.ending_position;
  const strategyParameters = summary.settings.strategy_parameters as Record<string, boolean | number | string> | undefined;
  const hasOpenPosition = Math.abs(endingPosition?.quantity ?? 0) > 1e-9;
  const contractVersion = summary.settings.engine_contract?.version;
  const isLegacyResult = contractVersion !== 2;
  return (
    <section className="result-sheet">
      <div className="result-title-row">
        <div>
          <p className="eyebrow">{summary.strategy.toUpperCase().replaceAll("_", " ")}</p>
          <h2>{summary.symbol} <small>{shortDate(summary.period.start)} → {shortDate(summary.period.end)}</small></h2>
          <p className="completion-time">{t("result.completedAt", { time: formatDateTime(job.finished_at, locale) })}</p>
        </div>
        <div className="evidence-stamp" data-legacy={isLegacyResult}>
          <span>{isLegacyResult ? "LEGACY RESULT" : `OPEND CONTRACT V${contractVersion}`}</span>
          <small>{t("result.bars", { count: formatNumber(summary.period.bars, 0, locale) })} · {autype} · {session}</small>
        </div>
      </div>

      <MetricsGrid metrics={summary.metrics} />
      {strategyParameters && Object.keys(strategyParameters).length > 0 ? (
        <aside className="result-parameters" aria-label={t("result.parameterSnapshot")}>
          <span>PARAMETER SNAPSHOT</span>
          {Object.entries(strategyParameters).map(([name, value]) => (
            <code key={name}>{name}=<strong>{String(value)}</strong></code>
          ))}
        </aside>
      ) : null}
      {isLegacyResult ? (
        <aside className="legacy-result-warning" role="status">
          {t("result.legacyWarning")}
        </aside>
      ) : null}
      {hasOpenPosition && endingPosition ? (
        <aside className="ending-position" aria-label={t("result.openPosition")}>
          <div><span>OPEN POSITION</span><strong>{t("result.openPositionTitle")}</strong></div>
          <dl>
            <div><dt>{t("result.sideQuantity")}</dt><dd>{endingPosition.side} · {formatNumber(Math.abs(endingPosition.quantity), 0, locale)}</dd></div>
            <div><dt>{t("result.averagePrice")}</dt><dd>{formatNumber(endingPosition.average_price, 2, locale)}</dd></div>
            <div><dt>{t("result.markPrice")}</dt><dd>{formatNumber(endingPosition.mark_price, 2, locale)}</dd></div>
            <div><dt>{t("result.unrealizedPnl")}</dt><dd className={endingPosition.unrealized_pnl >= 0 ? "positive" : "negative"}>{formatSignedCurrency(endingPosition.unrealized_pnl, locale)}</dd></div>
          </dl>
        </aside>
      ) : null}
      <PriceChart points={priceSeries} trades={trades} symbol={summary.symbol} ktype={ktype} autype={autype} />

      <figure className="report-frame">
        <figcaption><span>{t("result.reportCaption")}</span><span>RUN {job.id}</span></figcaption>
        <img src={`${result.report_url}?v=${encodeURIComponent(job.finished_at ?? "")}`} alt={t("result.reportAlt")} />
      </figure>

      <TradeTable trades={trades} ktype={ktype} exposure={summary.metrics.exposure_pct} />
      <p className="research-note">{t("result.researchNote")}</p>
    </section>
  );
}
