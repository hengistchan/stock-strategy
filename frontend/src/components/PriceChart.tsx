import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import type {
  PointerEvent as ReactPointerEvent,
  WheelEvent as ReactWheelEvent,
} from "react";
import { api } from "../api/client";
import { queryKeys } from "../api/queryKeys";
import type { PricePoint, PriceWindow, Trade } from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import type { Locale } from "../i18n/core";
import {
  formatCompactVolume,
  formatMarketTimestamp,
  formatNumber,
  formatPrice,
  formatSignedPercent,
  isIntradayKline,
  marketTimeKey,
  shortDate,
} from "../lib/format";

const MIN_VISIBLE_BARS = 30;
const MAX_VISIBLE_BARS = 420;
const DEFAULT_VISIBLE_BARS = 120;
const PRICE_CHUNK_SIZE = 1_200;
const PRICE_CHUNK_STRIDE = 600;

interface PriceChartProps {
  jobId: string;
  points: PricePoint[];
  pointOffset: number;
  totalPoints: number;
  overview: PricePoint[];
  trades: Trade[];
  symbol: string;
  ktype: string;
  autype: string;
}

interface Viewport {
  start: number;
  count: number;
}

interface HoverState {
  index: number;
  x: number;
  y: number;
}

interface ChartGeometry {
  plotLeft: number;
  plotRight: number;
  step: number;
  visibleLength: number;
}

export function PriceChart({
  jobId,
  points,
  pointOffset,
  totalPoints,
  overview,
  trades,
  symbol,
  ktype,
  autype,
}: PriceChartProps) {
  const { locale, t } = useI18n();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const shellRef = useRef<HTMLDivElement>(null);
  const geometryRef = useRef<ChartGeometry | null>(null);
  const dragRef = useRef<{ x: number; start: number } | null>(null);
  const lensDragRef = useRef(false);
  const [viewport, setViewport] = useState<Viewport>(() => initialViewport(totalPoints));
  const [hover, setHover] = useState<HoverState | null>(null);
  const [dragging, setDragging] = useState(false);
  const [chartSize, setChartSize] = useState({ width: 0, height: 0 });

  const chunkOffset = useMemo(
    () => chunkOffsetFor(viewport, totalPoints),
    [totalPoints, viewport],
  );
  const initialWindow = useMemo<PriceWindow | undefined>(() => {
    const coversViewport = pointOffset <= viewport.start
      && pointOffset + points.length >= viewport.start + viewport.count;
    if (!coversViewport) return undefined;
    return { offset: pointOffset, total: totalPoints, points };
  }, [pointOffset, points, totalPoints, viewport]);
  const pricesQuery = useQuery({
    queryKey: queryKeys.prices(jobId, chunkOffset, PRICE_CHUNK_SIZE),
    queryFn: () => api.prices(jobId, chunkOffset, PRICE_CHUNK_SIZE),
    initialData: initialWindow,
    placeholderData: (previous) => previous,
    staleTime: Infinity,
  });
  const loaded = pricesQuery.data;
  const localStart = loaded ? viewport.start - loaded.offset : -1;
  const visible = useMemo(
    () => loaded && localStart >= 0 && localStart + viewport.count <= loaded.points.length
      ? loaded.points.slice(localStart, localStart + viewport.count)
      : [],
    [loaded, localStart, viewport.count],
  );
  const averages = useMemo(() => ({
    ma20: movingAverage(loaded?.points ?? [], 20),
    ma60: movingAverage(loaded?.points ?? [], 60),
  }), [loaded?.points]);
  const visibleMa20 = useMemo(
    () => localStart >= 0 ? averages.ma20.slice(localStart, localStart + visible.length) : [],
    [averages.ma20, localStart, visible.length],
  );
  const visibleMa60 = useMemo(
    () => localStart >= 0 ? averages.ma60.slice(localStart, localStart + visible.length) : [],
    [averages.ma60, localStart, visible.length],
  );
  const displayPoint = hover ? visible[hover.index] : visible.at(-1);
  const displayIndex = hover ? hover.index : visible.length - 1;
  const change = displayPoint ? pointChange(visible, displayIndex) : 0;

  useEffect(() => {
    const shell = shellRef.current;
    if (!shell) return undefined;
    const observer = new ResizeObserver(([entry]) => {
      setChartSize({
        width: Math.round(entry.contentRect.width),
        height: Math.round(entry.contentRect.height),
      });
    });
    observer.observe(shell);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || chartSize.width === 0 || chartSize.height === 0) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(chartSize.width * dpr);
    canvas.height = Math.round(chartSize.height * dpr);
    const context = canvas.getContext("2d");
    if (!context) return;
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    context.clearRect(0, 0, chartSize.width, chartSize.height);
    geometryRef.current = drawChart({
      context,
      width: chartSize.width,
      height: chartSize.height,
      points: visible,
      trades,
      ma20: visibleMa20,
      ma60: visibleMa60,
      hoverIndex: hover?.index ?? null,
      ktype,
      locale,
      noDataText: pricesQuery.isFetching ? t("chart.loadingWindow") : t("chart.noData"),
    });
  }, [chartSize, hover?.index, ktype, locale, pricesQuery.isFetching, t, trades, visible, visibleMa20, visibleMa60]);

  function setStart(start: number) {
    setViewport((current) => ({ ...current, start: clampStart(start, current.count, totalPoints) }));
    setHover(null);
  }

  function zoom(factor: number, anchor = 0.5) {
    setViewport((current) => {
      const maximum = Math.min(MAX_VISIBLE_BARS, Math.max(MIN_VISIBLE_BARS, totalPoints));
      const count = Math.max(
        Math.min(MIN_VISIBLE_BARS, totalPoints),
        Math.min(maximum, Math.round(current.count * factor)),
      );
      const start = clampStart(
        Math.round(current.start + anchor * (current.count - count)),
        count,
        totalPoints,
      );
      return { start, count };
    });
    setHover(null);
  }

  function handlePointerMove(event: ReactPointerEvent<HTMLCanvasElement>) {
    const geometry = geometryRef.current;
    if (!geometry || visible.length === 0) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    if (dragRef.current) {
      const plotWidth = Math.max(1, geometry.plotRight - geometry.plotLeft);
      const bars = Math.round(((dragRef.current.x - event.clientX) / plotWidth) * viewport.count);
      setStart(dragRef.current.start + bars);
      return;
    }
    if (x < geometry.plotLeft || x > geometry.plotRight) {
      setHover(null);
      return;
    }
    const index = Math.max(0, Math.min(
      geometry.visibleLength - 1,
      Math.floor((x - geometry.plotLeft) / geometry.step),
    ));
    setHover({ index, x, y });
  }

  function handlePointerDown(event: ReactPointerEvent<HTMLCanvasElement>) {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { x: event.clientX, start: viewport.start };
    setDragging(true);
    setHover(null);
  }

  function endDrag(event: ReactPointerEvent<HTMLCanvasElement>) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    dragRef.current = null;
    setDragging(false);
  }

  function handleWheel(event: ReactWheelEvent<HTMLCanvasElement>) {
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    const anchor = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    zoom(event.deltaY > 0 ? 1.22 : 0.82, anchor);
  }

  function moveLens(event: ReactPointerEvent<HTMLDivElement>) {
    if (!lensDragRef.current && event.type !== "pointerdown") return;
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    setStart(Math.round(ratio * totalPoints - viewport.count / 2));
  }

  const ariaLabel = visible.length
    ? t("chart.aria", {
      start: formatMarketTimestamp(visible[0].date, ktype),
      end: formatMarketTimestamp(visible.at(-1)!.date, ktype),
      symbol,
      count: visible.length,
    })
    : t("chart.emptyAria", { symbol });
  const lensLeft = totalPoints ? (viewport.start / totalPoints) * 100 : 0;
  const lensWidth = totalPoints ? Math.max(1.2, (viewport.count / totalPoints) * 100) : 100;

  return (
    <section className="price-section" aria-labelledby="priceChartTitle">
      <div className="price-heading">
        <div>
          <span className="section-code">MARKET TAPE</span>
          <h3 id="priceChartTitle">{t("chart.title")}</h3>
          <p>OpenD · {ktype} · {autype} · {t("chart.bars", { count: formatNumber(totalPoints, 0, locale) })}</p>
        </div>
        <div className="chart-controls" aria-label={t("chart.navigation")}>
          <button type="button" onClick={() => zoom(1.35)} aria-label={t("chart.zoomOut")}>−</button>
          <span>{formatNumber(viewport.count, 0, locale)} / {formatNumber(totalPoints, 0, locale)}</span>
          <button type="button" onClick={() => zoom(0.72)} aria-label={t("chart.zoomIn")}>＋</button>
          <button type="button" className="latest-button" onClick={() => setStart(totalPoints - viewport.count)}>{t("chart.latest")}</button>
        </div>
      </div>

      <div className="price-readout" aria-live="polite">
        <Readout label={t("chart.date")} value={displayPoint ? formatMarketTimestamp(displayPoint.date, ktype) : "—"} />
        <Readout label={t("chart.open")} value={displayPoint ? formatPrice(displayPoint.open, locale) : "—"} />
        <Readout label={t("chart.high")} value={displayPoint ? formatPrice(displayPoint.high, locale) : "—"} />
        <Readout label={t("chart.low")} value={displayPoint ? formatPrice(displayPoint.low, locale) : "—"} />
        <Readout label={t("chart.close")} value={displayPoint ? formatPrice(displayPoint.close, locale) : "—"} />
        <Readout label={t("chart.change")} value={displayPoint ? formatSignedPercent(change, locale) : "—"} tone={change >= 0 ? "positive" : "negative"} />
        <Readout label={t("chart.volume")} value={displayPoint ? formatCompactVolume(displayPoint.volume, locale) : "—"} />
      </div>

      <div className="chart-legend" aria-label={t("chart.legend")}>
        <span><i className="legend-candle" />OHLC</span>
        <span><i className="legend-ma20" />MA20</span>
        <span><i className="legend-ma60" />MA60</span>
        <span><i className="legend-entry">▲</i>{t("chart.entry")}</span>
        <span><i className="legend-exit">▼</i>{t("chart.exit")}</span>
        <span className="chart-interaction-hint">{t("chart.interactionHint")}</span>
      </div>

      <div className="price-chart-shell" ref={shellRef} data-dragging={dragging}>
        <canvas
          ref={canvasRef}
          aria-label={ariaLabel}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onPointerLeave={() => { if (!dragRef.current) setHover(null); }}
          onWheel={handleWheel}
        />
        {pricesQuery.isFetching ? <span className="chart-loading">{t("chart.loadingWindow")}</span> : null}
        {hover && displayPoint && !dragging ? (
          <div className="price-tooltip" style={tooltipPosition(hover, chartSize)}>
            <strong>{formatMarketTimestamp(displayPoint.date, ktype)}</strong>
            <span><em>{t("chart.open")}</em><b>{formatPrice(displayPoint.open, locale)}</b></span>
            <span><em>{t("chart.high")}</em><b>{formatPrice(displayPoint.high, locale)}</b></span>
            <span><em>{t("chart.low")}</em><b>{formatPrice(displayPoint.low, locale)}</b></span>
            <span><em>{t("chart.close")}</em><b>{formatPrice(displayPoint.close, locale)}</b></span>
            <span><em>{t("chart.change")}</em><b>{formatSignedPercent(change, locale)}</b></span>
            <span><em>{t("chart.volume")}</em><b>{formatNumber(displayPoint.volume, 0, locale)}</b></span>
          </div>
        ) : null}
      </div>

      <div
        className="time-lens"
        aria-label={t("chart.timeline")}
        onPointerDown={(event) => {
          lensDragRef.current = true;
          event.currentTarget.setPointerCapture(event.pointerId);
          moveLens(event);
        }}
        onPointerMove={moveLens}
        onPointerUp={(event) => {
          lensDragRef.current = false;
          if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
        }}
        onPointerCancel={() => { lensDragRef.current = false; }}
      >
        <svg viewBox="0 0 1000 64" preserveAspectRatio="none" aria-hidden="true">
          <path d={overviewPath(overview)} />
        </svg>
        <span className="time-lens-window" style={{ left: `${lensLeft}%`, width: `${Math.min(lensWidth, 100 - lensLeft)}%` }}><i /><i /></span>
        <small>{overview[0] ? formatMarketTimestamp(overview[0].date, ktype) : "—"}</small>
        <small>{overview.at(-1) ? formatMarketTimestamp(overview.at(-1)!.date, ktype) : "—"}</small>
      </div>
      <p className="chart-method">{t("chart.method")}</p>
    </section>
  );
}

function initialViewport(total: number): Viewport {
  const count = Math.min(DEFAULT_VISIBLE_BARS, total);
  return { start: Math.max(0, total - count), count };
}

function chunkOffsetFor(viewport: Viewport, total: number): number {
  if (total <= PRICE_CHUNK_SIZE) return 0;
  const ideal = Math.floor((viewport.start - 300) / PRICE_CHUNK_STRIDE) * PRICE_CHUNK_STRIDE;
  return Math.max(0, Math.min(total - PRICE_CHUNK_SIZE, ideal));
}

function clampStart(start: number, count: number, total: number): number {
  return Math.max(0, Math.min(Math.max(0, total - count), start));
}

function overviewPath(points: PricePoint[]): string {
  if (points.length === 0) return "";
  const minimum = Math.min(...points.map((point) => point.close));
  const maximum = Math.max(...points.map((point) => point.close));
  const spread = Math.max(maximum - minimum, 0.0001);
  return points.map((point, index) => {
    const x = points.length === 1 ? 0 : (index / (points.length - 1)) * 1000;
    const y = 58 - ((point.close - minimum) / spread) * 52;
    return `${index ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");
}

interface ReadoutProps { label: string; value: string; tone?: string }
function Readout({ label, value, tone = "" }: ReadoutProps) {
  return <span><small>{label}</small><strong className={tone}>{value}</strong></span>;
}

function movingAverage(points: PricePoint[], period: number): Array<number | null> {
  const values: Array<number | null> = new Array(points.length).fill(null);
  let sum = 0;
  points.forEach((point, index) => {
    sum += point.close;
    if (index >= period) sum -= points[index - period].close;
    if (index >= period - 1) values[index] = sum / period;
  });
  return values;
}

function pointChange(points: PricePoint[], index: number): number {
  const point = points[index];
  if (!point) return 0;
  const previous = index > 0 ? points[index - 1].close : point.open;
  return previous ? (point.close / previous - 1) * 100 : 0;
}

function tooltipPosition(hover: HoverState, size: { width: number; height: number }) {
  const width = 188;
  const height = 154;
  return {
    left: hover.x > size.width - width - 24 ? hover.x - width - 12 : hover.x + 12,
    top: Math.max(8, Math.min(size.height - height - 8, hover.y - 24)),
  };
}

interface DrawOptions {
  context: CanvasRenderingContext2D;
  width: number;
  height: number;
  points: PricePoint[];
  trades: Trade[];
  ma20: Array<number | null>;
  ma60: Array<number | null>;
  hoverIndex: number | null;
  ktype: string;
  locale: Locale;
  noDataText: string;
}

function drawChart(options: DrawOptions): ChartGeometry | null {
  const { context, width, height, points, trades, ma20, ma60, hoverIndex, ktype, locale, noDataText } = options;
  if (points.length === 0) {
    context.fillStyle = "#667c7d";
    context.font = '11px "SFMono-Regular", Menlo, monospace';
    context.fillText(noDataText, 18, 34);
    return null;
  }
  const compact = width < 560;
  const plotLeft = compact ? 10 : 18;
  const plotRight = width - (compact ? 48 : 64);
  const priceTop = 24;
  const priceBottom = height - (compact ? 112 : 124);
  const volumeTop = priceBottom + 27;
  const volumeBottom = height - 36;
  const step = (plotRight - plotLeft) / points.length;
  const candleWidth = Math.max(1, Math.min(8, step * 0.64));
  const rawMin = Math.min(...points.map((point) => point.low));
  const rawMax = Math.max(...points.map((point) => point.high));
  const spread = Math.max(rawMax - rawMin, Math.abs(rawMax) * 0.01, 0.01);
  const priceMin = rawMin - spread * 0.055;
  const priceMax = rawMax + spread * 0.055;
  const volumeMax = Math.max(...points.map((point) => point.volume), 1);
  const xForLocal = (index: number) => plotLeft + (index + 0.5) * step;
  const yForPrice = (price: number) => priceTop + ((priceMax - price) / (priceMax - priceMin)) * (priceBottom - priceTop);
  const yForVolume = (volume: number) => volumeBottom - (volume / volumeMax) * (volumeBottom - volumeTop);

  drawGrid(context, { width, height, plotLeft, plotRight, priceTop, priceBottom, volumeTop, volumeBottom, priceMin, priceMax, visible: points, xForLocal, ktype, locale });
  drawVolumes(context, points, xForLocal, yForVolume, candleWidth, volumeBottom);
  drawAverage(context, ma20, xForLocal, yForPrice, "#278779", []);
  drawAverage(context, ma60, xForLocal, yForPrice, "#d58a35", [5, 4]);
  drawCandles(context, points, xForLocal, yForPrice, candleWidth);
  drawTradeMarkers(context, points, trades, xForLocal, yForPrice);

  if (hoverIndex !== null && points[hoverIndex]) {
    const x = xForLocal(hoverIndex);
    const y = yForPrice(points[hoverIndex].close);
    context.save();
    context.strokeStyle = "rgba(16, 42, 50, 0.48)";
    context.setLineDash([3, 4]);
    context.beginPath();
    context.moveTo(x, priceTop); context.lineTo(x, volumeBottom);
    context.moveTo(plotLeft, y); context.lineTo(plotRight, y);
    context.stroke(); context.restore();
  }
  return { plotLeft, plotRight, step, visibleLength: points.length };
}

interface GridOptions {
  width: number; height: number; plotLeft: number; plotRight: number;
  priceTop: number; priceBottom: number; volumeTop: number; volumeBottom: number;
  priceMin: number; priceMax: number; visible: PricePoint[];
  xForLocal: (index: number) => number; ktype: string; locale: Locale;
}

function drawGrid(context: CanvasRenderingContext2D, options: GridOptions) {
  const { width, height, plotLeft, plotRight, priceTop, priceBottom, volumeTop, volumeBottom, priceMin, priceMax, visible, xForLocal, ktype, locale } = options;
  context.save();
  context.font = '9px "SFMono-Regular", Menlo, monospace';
  context.fillStyle = "#667c7d";
  context.strokeStyle = "rgba(120, 144, 142, 0.35)";
  for (let tick = 0; tick < 5; tick += 1) {
    const ratio = tick / 4;
    const y = priceTop + ratio * (priceBottom - priceTop);
    const price = priceMax - ratio * (priceMax - priceMin);
    context.beginPath(); context.moveTo(plotLeft, Math.round(y) + 0.5); context.lineTo(plotRight, Math.round(y) + 0.5); context.stroke();
    context.fillText(formatPrice(price, locale), plotRight + 7, y + 3);
  }
  context.beginPath(); context.moveTo(plotLeft, volumeTop - 9.5); context.lineTo(plotRight, volumeTop - 9.5); context.stroke();
  context.fillText("VOL", plotLeft, volumeTop - 14);
  context.fillText("0", plotRight + 7, volumeBottom + 3);
  const tickCount = width < 560 ? 3 : 5;
  const sameDay = shortDate(visible[0].date) === shortDate(visible.at(-1)!.date);
  for (let tick = 0; tick < tickCount; tick += 1) {
    const index = Math.round((tick / (tickCount - 1)) * (visible.length - 1));
    const x = xForLocal(index);
    const label = compactChartDate(visible[index].date, sameDay, ktype);
    const labelWidth = context.measureText(label).width;
    context.fillText(label, Math.max(2, Math.min(width - labelWidth - 2, x - labelWidth / 2)), height - 14);
  }
  context.restore();
}

function drawVolumes(context: CanvasRenderingContext2D, points: PricePoint[], xForLocal: (index: number) => number, yForVolume: (volume: number) => number, width: number, bottom: number) {
  points.forEach((point, index) => {
    const y = yForVolume(point.volume);
    context.fillStyle = point.close >= point.open ? "rgba(39, 135, 121, 0.30)" : "rgba(213, 138, 53, 0.38)";
    context.fillRect(xForLocal(index) - width / 2, y, Math.max(1, width), bottom - y);
  });
}

function drawCandles(context: CanvasRenderingContext2D, points: PricePoint[], xForLocal: (index: number) => number, yForPrice: (price: number) => number, width: number) {
  points.forEach((point, index) => {
    const rising = point.close >= point.open;
    const color = rising ? "#278779" : "#d58a35";
    const x = xForLocal(index);
    const yOpen = yForPrice(point.open);
    const yClose = yForPrice(point.close);
    const bodyTop = Math.min(yOpen, yClose);
    const bodyHeight = Math.max(1, Math.abs(yClose - yOpen));
    context.strokeStyle = color;
    context.lineWidth = Math.max(1, Math.min(1.4, width * 0.22));
    context.beginPath(); context.moveTo(x, yForPrice(point.high)); context.lineTo(x, yForPrice(point.low)); context.stroke();
    if (rising) {
      context.fillStyle = "#f7faf8";
      context.fillRect(x - width / 2, bodyTop, width, bodyHeight);
      context.strokeRect(x - width / 2, bodyTop, width, bodyHeight);
    } else {
      context.fillStyle = color;
      context.fillRect(x - width / 2, bodyTop, width, bodyHeight);
    }
  });
}

function drawAverage(context: CanvasRenderingContext2D, values: Array<number | null>, xForLocal: (index: number) => number, yForPrice: (price: number) => number, color: string, dash: number[]) {
  context.save(); context.strokeStyle = color; context.lineWidth = 1.6; context.setLineDash(dash); context.beginPath();
  let started = false;
  values.forEach((value, index) => {
    if (value === null) return;
    const x = xForLocal(index); const y = yForPrice(value);
    if (!started) { context.moveTo(x, y); started = true; } else context.lineTo(x, y);
  });
  if (started) context.stroke(); context.restore();
}

function drawTradeMarkers(context: CanvasRenderingContext2D, points: PricePoint[], trades: Trade[], xForLocal: (index: number) => number, yForPrice: (price: number) => number) {
  const indexByDate = new Map(points.map((point, index) => [marketTimeKey(point.date), index]));
  trades.forEach((trade) => {
    const entry = indexByDate.get(marketTimeKey(trade.entry_date));
    if (entry !== undefined) drawTriangle(context, xForLocal(entry), yForPrice(points[entry].low) + 13, "up", "#278779");
    const exit = indexByDate.get(marketTimeKey(trade.exit_date));
    if (exit !== undefined) drawTriangle(context, xForLocal(exit), yForPrice(points[exit].high) - 13, "down", "#d58a35");
  });
}

function drawTriangle(context: CanvasRenderingContext2D, x: number, y: number, direction: "up" | "down", color: string) {
  const size = 6;
  context.save(); context.fillStyle = color; context.strokeStyle = "#f7faf8"; context.beginPath();
  if (direction === "up") { context.moveTo(x, y - size); context.lineTo(x - size, y + size); context.lineTo(x + size, y + size); }
  else { context.moveTo(x, y + size); context.lineTo(x - size, y - size); context.lineTo(x + size, y - size); }
  context.closePath(); context.fill(); context.stroke(); context.restore();
}

function compactChartDate(value: string, sameDay: boolean, ktype: string): string {
  const timestamp = value.replace("T", " ");
  if (!isIntradayKline(ktype)) return timestamp.slice(2, 10);
  return sameDay ? timestamp.slice(11, 16) : timestamp.slice(5, 16);
}
