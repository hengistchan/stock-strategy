import { useId, useMemo, useState, type KeyboardEvent } from "react";
import type { MonitorBar } from "../../api/types";
import { useI18n } from "../../i18n/I18nContext";
import {
  MONITOR_MISSING_VALUE,
  formatMonitorInteger,
  formatMonitorPrice,
  formatQuoteTimestamp,
} from "./formatters";

interface MonitorTapeChartProps {
  bars: readonly MonitorBar[];
  symbol: string;
}

interface ChartBar {
  sourceTime: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
  isClosed: boolean;
}

const VIEWBOX_WIDTH = 840;
const VIEWBOX_HEIGHT = 300;
const PRICE_TOP = 18;
const PRICE_BOTTOM = 218;
const VOLUME_TOP = 238;
const VOLUME_BOTTOM = 282;

export function MonitorTapeChart({ bars, symbol }: MonitorTapeChartProps) {
  const { locale, t } = useI18n();
  const titleId = useId();
  const data = useMemo(() => normalizeBars(bars), [bars]);
  const [requestedIndex, setRequestedIndex] = useState<number | null>(null);
  const selectedIndex =
    data.length === 0
      ? -1
      : Math.min(Math.max(requestedIndex ?? data.length - 1, 0), data.length - 1);
  const selected = selectedIndex >= 0 ? data[selectedIndex] : null;

  if (data.length === 0) {
    return (
      <section className="monitor-tape monitor-panel" aria-labelledby={titleId}>
        <header className="monitor-panel-heading">
          <div>
            <p className="section-code">TAPE / K_5M</p>
            <h3 id={titleId}>{t("monitor.tapeTitle")}</h3>
          </div>
        </header>
        <p className="monitor-inline-empty">{t("monitor.tapeEmpty")}</p>
      </section>
    );
  }

  const priceMin = Math.min(...data.map((bar) => bar.low));
  const priceMax = Math.max(...data.map((bar) => bar.high));
  const priceRange = priceMax - priceMin || Math.max(Math.abs(priceMax) * 0.01, 1);
  const maxVolume = Math.max(...data.map((bar) => bar.volume ?? 0), 1);
  const slot = VIEWBOX_WIDTH / data.length;
  const candleWidth = Math.max(1.5, Math.min(8, slot * 0.55));
  const xFor = (index: number) => slot * index + slot / 2;
  const yFor = (value: number) =>
    PRICE_BOTTOM
    - ((value - priceMin) / priceRange) * (PRICE_BOTTOM - PRICE_TOP);

  function moveSelection(event: KeyboardEvent<SVGSVGElement>) {
    let next = selectedIndex;
    if (event.key === "ArrowLeft" || event.key === "ArrowDown") next -= 1;
    else if (event.key === "ArrowRight" || event.key === "ArrowUp") next += 1;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = data.length - 1;
    else return;
    event.preventDefault();
    setRequestedIndex(Math.min(Math.max(next, 0), data.length - 1));
  }

  return (
    <section className="monitor-tape monitor-panel" aria-labelledby={titleId}>
      <header className="monitor-panel-heading monitor-tape-heading">
        <div>
          <p className="section-code">TAPE / K_5M</p>
          <h3 id={titleId}>{t("monitor.tapeTitle")}</h3>
        </div>
        <p>{t("monitor.tapeKeyboardHint")}</p>
      </header>
      <output className="monitor-tape-readout" aria-live="polite">
        <span>
          <small>{t("monitor.quoteTime")}</small>
          <strong>{formatQuoteTimestamp(selected?.sourceTime)}</strong>
        </span>
        <span>
          <small>{t("monitor.open")}</small>
          <strong>{formatMonitorPrice(selected?.open, locale)}</strong>
        </span>
        <span>
          <small>{t("monitor.high")}</small>
          <strong>{formatMonitorPrice(selected?.high, locale)}</strong>
        </span>
        <span>
          <small>{t("monitor.low")}</small>
          <strong>{formatMonitorPrice(selected?.low, locale)}</strong>
        </span>
        <span>
          <small>{t("monitor.close")}</small>
          <strong>{formatMonitorPrice(selected?.close, locale)}</strong>
        </span>
        <span>
          <small>{t("monitor.volume")}</small>
          <strong>{formatMonitorInteger(selected?.volume, locale)}</strong>
        </span>
      </output>
      <div className="monitor-tape-canvas">
        <svg
          viewBox={`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`}
          role="img"
          tabIndex={0}
          aria-labelledby={`${titleId} ${titleId}-description`}
          onKeyDown={moveSelection}
        >
          <desc id={`${titleId}-description`}>
            {t("monitor.tapeAria", { symbol, count: data.length })}
          </desc>
          {[0, 0.25, 0.5, 0.75, 1].map((step) => (
            <line
              key={step}
              className="monitor-tape-grid"
              x1="0"
              x2={VIEWBOX_WIDTH}
              y1={PRICE_TOP + step * (PRICE_BOTTOM - PRICE_TOP)}
              y2={PRICE_TOP + step * (PRICE_BOTTOM - PRICE_TOP)}
            />
          ))}
          {data.map((bar, index) => {
            const x = xFor(index);
            const openY = yFor(bar.open);
            const closeY = yFor(bar.close);
            const rising = bar.close >= bar.open;
            const bodyTop = Math.min(openY, closeY);
            const bodyHeight = Math.max(1.5, Math.abs(closeY - openY));
            const volumeHeight =
              ((bar.volume ?? 0) / maxVolume) * (VOLUME_BOTTOM - VOLUME_TOP);
            return (
              <g
                key={`${bar.sourceTime}-${index}`}
                className="monitor-candle"
                data-direction={rising ? "up" : "down"}
                data-selected={index === selectedIndex}
              >
                <line x1={x} x2={x} y1={yFor(bar.high)} y2={yFor(bar.low)} />
                <rect
                  x={x - candleWidth / 2}
                  y={bodyTop}
                  width={candleWidth}
                  height={bodyHeight}
                />
                <rect
                  className="monitor-volume-bar"
                  x={x - candleWidth / 2}
                  y={VOLUME_BOTTOM - volumeHeight}
                  width={candleWidth}
                  height={Math.max(volumeHeight, 0.5)}
                />
              </g>
            );
          })}
          {selectedIndex >= 0 ? (
            <line
              className="monitor-tape-cursor"
              x1={xFor(selectedIndex)}
              x2={xFor(selectedIndex)}
              y1={PRICE_TOP}
              y2={VOLUME_BOTTOM}
            />
          ) : null}
        </svg>
      </div>
      <footer className="monitor-tape-scale" aria-hidden="true">
        <time>{formatQuoteTimestamp(data[0]?.sourceTime) || MONITOR_MISSING_VALUE}</time>
        <span>{data.length} BARS</span>
        <time>
          {formatQuoteTimestamp(data[data.length - 1]?.sourceTime)
            || MONITOR_MISSING_VALUE}
        </time>
      </footer>
    </section>
  );
}

function normalizeBars(bars: readonly MonitorBar[]): ChartBar[] {
  return bars.flatMap((bar) => {
    const open = finiteNumber(bar.open);
    const high = finiteNumber(bar.high);
    const low = finiteNumber(bar.low);
    const close = finiteNumber(bar.close);
    if (
      !bar.source_time
      || open === null
      || high === null
      || low === null
      || close === null
    ) {
      return [];
    }
    return [{
      sourceTime: bar.source_time,
      open,
      high: Math.max(high, open, close),
      low: Math.min(low, open, close),
      close,
      volume: nonNegativeNumber(bar.volume),
      isClosed: bar.is_closed,
    }];
  });
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function nonNegativeNumber(value: unknown): number | null {
  const number = finiteNumber(value);
  return number !== null && number >= 0 ? number : null;
}
