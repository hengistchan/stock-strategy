import type {
  MonitorBarsResponse,
  SnapshotResponse,
} from "../../api/types";
import { useI18n } from "../../i18n/I18nContext";
import {
  formatMonitorInteger,
  formatMonitorPercent,
  formatMonitorPrice,
  formatMonitorSignedPrice,
  formatQuoteTimestamp,
} from "./formatters";
import { classifyMonitorError } from "./monitorError";
import { MonitorStatePanel } from "./MonitorStatePanel";
import { MonitorTapeChart } from "./MonitorTapeChart";

interface UnderlyingOverviewProps {
  symbol: string;
  snapshot?: SnapshotResponse;
  bars?: MonitorBarsResponse;
  snapshotLoading: boolean;
  barsLoading: boolean;
  snapshotError: unknown;
  barsError: unknown;
  onRetry: () => void;
}

export function UnderlyingOverview({
  symbol,
  snapshot,
  bars,
  snapshotLoading,
  barsLoading,
  snapshotError,
  barsError,
  onRetry,
}: UnderlyingOverviewProps) {
  const { locale, t } = useI18n();

  if (snapshotLoading && !snapshot) {
    return <MonitorStatePanel state="checking" compact />;
  }
  if (snapshotError && !snapshot) {
    return (
      <MonitorStatePanel
        state={classifyMonitorError(snapshotError)}
        compact
        detail={errorMessage(snapshotError)}
        onRetry={onRetry}
      />
    );
  }
  if (!snapshot) {
    return <MonitorStatePanel state="unavailable" compact onRetry={onRetry} />;
  }

  const quote = snapshot.snapshot as Record<string, unknown>;
  const changeRate = numberField(quote, "change_rate");
  const changeTone =
    changeRate === null ? "neutral" : changeRate > 0 ? "positive" : changeRate < 0 ? "negative" : "neutral";
  const previousClose = numberField(quote, "previous_close");
  const lastPrice = numberField(quote, "last_price");
  const absoluteChange =
    lastPrice !== null && previousClose !== null ? lastPrice - previousClose : null;
  const metrics = [
    {
      label: t("monitor.open"),
      value: formatMonitorPrice(numberField(quote, "open_price"), locale),
    },
    {
      label: t("monitor.high"),
      value: formatMonitorPrice(numberField(quote, "high_price"), locale),
    },
    {
      label: t("monitor.low"),
      value: formatMonitorPrice(numberField(quote, "low_price"), locale),
    },
    {
      label: t("monitor.previousClose"),
      value: formatMonitorPrice(previousClose, locale),
    },
    {
      label: t("monitor.bid"),
      value: formatMonitorPrice(numberField(quote, "bid_price"), locale),
    },
    {
      label: t("monitor.ask"),
      value: formatMonitorPrice(numberField(quote, "ask_price"), locale),
    },
    {
      label: t("monitor.volume"),
      value: formatMonitorInteger(numberField(quote, "volume"), locale),
    },
    {
      label: t("monitor.turnover"),
      value: formatMonitorInteger(numberField(quote, "turnover"), locale),
    },
    {
      label: t("monitor.turnoverRate"),
      value: formatMonitorPercent(numberField(quote, "turnover_rate"), locale),
    },
    {
      label: t("monitor.amplitude"),
      value: formatMonitorPercent(numberField(quote, "amplitude"), locale),
    },
    {
      label: t("monitor.volumeRatio"),
      value: formatMonitorPrice(numberField(quote, "volume_ratio"), locale),
    },
    {
      label: t("monitor.lotSize"),
      value: formatMonitorInteger(numberField(quote, "lot_size"), locale),
    },
  ];

  return (
    <div className="monitor-overview">
      {snapshot.freshness === "stale" || snapshot.freshness === "market_closed" ? (
        <div
          className="monitor-freshness-banner"
          data-freshness={snapshot.freshness}
          role="status"
        >
          <strong>
            {t(
              snapshot.freshness === "stale"
                ? "monitor.stateStaleTitle"
                : "monitor.stateClosedTitle",
            )}
          </strong>
          <span>
            {t(
              snapshot.freshness === "stale"
                ? "monitor.stateStaleBody"
                : "monitor.stateClosedBody",
            )}
          </span>
        </div>
      ) : null}
      <section className="monitor-quote-hero" aria-labelledby="monitorQuoteTitle">
        <div>
          <p className="section-code">UNDERLYING / OPEND</p>
          <h2 id="monitorQuoteTitle">
            {snapshot.snapshot.name || symbol}
            <small>{symbol}</small>
          </h2>
          <p>
            {t("monitor.quoteAsOfWithAge", {
              time: formatQuoteTimestamp(snapshot.snapshot.source_time),
              age: formatMonitorInteger(snapshot.age_seconds, locale),
            })}
          </p>
        </div>
        <div className="monitor-last-price" data-tone={changeTone}>
          <strong>{formatMonitorPrice(lastPrice, locale)}</strong>
          <span>
            {formatMonitorSignedPrice(absoluteChange, locale)}
            {" · "}
            {formatMonitorPercent(changeRate, locale, 2, true)}
          </span>
        </div>
      </section>

      <section className="monitor-quote-metrics" aria-label={t("monitor.quoteMetrics")}>
        {metrics.map((metric) => (
          <article key={metric.label}>
            <small>{metric.label}</small>
            <strong>{metric.value}</strong>
          </article>
        ))}
      </section>

      {barsLoading && !bars ? (
        <div className="monitor-panel">
          <p className="monitor-inline-empty">{t("monitor.tapeLoading")}</p>
        </div>
      ) : barsError && !bars ? (
        <MonitorStatePanel
          state={classifyMonitorError(barsError)}
          compact
          detail={errorMessage(barsError)}
          onRetry={onRetry}
        />
      ) : (
        <MonitorTapeChart bars={bars?.bars ?? []} symbol={symbol} />
      )}

      <p className="monitor-research-note">{t("monitor.researchOnly")}</p>
    </div>
  );
}

function numberField(record: Record<string, unknown>, key: string): number | null {
  const value = record[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function errorMessage(error: unknown): string | null {
  return error instanceof Error ? error.message : null;
}
