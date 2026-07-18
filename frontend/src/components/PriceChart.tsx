import { useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import type { PricePoint, Trade } from "../api/types";
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

type ChartRange = 63 | 126 | 252 | "all";

interface PriceChartProps {
  points: PricePoint[];
  trades: Trade[];
  symbol: string;
  ktype: string;
  autype: string;
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
  startIndex: number;
  visibleLength: number;
}

interface DrawOptions {
  context: CanvasRenderingContext2D;
  width: number;
  height: number;
  points: PricePoint[];
  trades: Trade[];
  ma20: Array<number | null>;
  ma60: Array<number | null>;
  range: ChartRange;
  hoverIndex: number | null;
  ktype: string;
}

export function PriceChart({ points, trades, symbol, ktype, autype }: PriceChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const shellRef = useRef<HTMLDivElement>(null);
  const geometryRef = useRef<ChartGeometry | null>(null);
  const [range, setRange] = useState<ChartRange>(252);
  const [hover, setHover] = useState<HoverState | null>(null);
  const [chartSize, setChartSize] = useState({ width: 0, height: 0 });
  const ma20 = useMemo(() => movingAverage(points, 20), [points]);
  const ma60 = useMemo(() => movingAverage(points, 60), [points]);
  const displayPoint = hover ? points[hover.index] : points.at(-1);
  const displayIndex = hover ? hover.index : points.length - 1;
  const change = displayPoint ? pointChange(points, displayIndex) : 0;
  const ranges: Array<{ value: ChartRange; label: string }> = isIntradayKline(ktype)
    ? [{ value: 63, label: "63根" }, { value: 126, label: "126根" }, { value: 252, label: "252根" }, { value: "all", label: "全部" }]
    : [{ value: 63, label: "3M" }, { value: 126, label: "6M" }, { value: 252, label: "1Y" }, { value: "all", label: "ALL" }];

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
      points,
      trades,
      ma20,
      ma60,
      range,
      hoverIndex: hover?.index ?? null,
      ktype,
    });
  }, [chartSize, hover?.index, ktype, ma20, ma60, points, range, trades]);

  function handlePointerMove(event: ReactPointerEvent<HTMLCanvasElement>) {
    const geometry = geometryRef.current;
    if (!geometry || points.length === 0) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    if (x < geometry.plotLeft || x > geometry.plotRight) {
      setHover(null);
      return;
    }
    const localIndex = Math.max(
      0,
      Math.min(
        geometry.visibleLength - 1,
        Math.floor((x - geometry.plotLeft) / geometry.step),
      ),
    );
    setHover({ index: geometry.startIndex + localIndex, x, y });
  }

  const visibleCount = range === "all" ? points.length : Math.min(range, points.length);
  const visibleStart = points.length - visibleCount;
  const visible = points.slice(visibleStart);
  const ariaLabel = visible.length
    ? `${formatMarketTimestamp(visible[0].date, ktype)} 至 ${formatMarketTimestamp(visible.at(-1)!.date, ktype)} 的 ${symbol} OpenD OHLC 蜡烛图，共 ${visible.length} 根。`
    : `${symbol} 暂无可绘制的 OpenD OHLC 数据。`;

  return (
    <section className="price-section" aria-labelledby="priceChartTitle">
      <div className="price-heading">
        <div>
          <span className="section-code">MARKET TAPE</span>
          <h3 id="priceChartTitle">价格与成交位置</h3>
          <p>OpenD · {ktype} · {autype} · {formatNumber(points.length, 0)} 根 K 线</p>
        </div>
        <div className="range-switch" aria-label="价格图区间">
          {ranges.map((item) => (
            <button
              key={item.value}
              type="button"
              aria-pressed={range === item.value}
              onClick={() => { setRange(item.value); setHover(null); }}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      <div className="price-readout" aria-live="polite">
        <Readout label="DATE" value={displayPoint ? formatMarketTimestamp(displayPoint.date, ktype) : "—"} />
        <Readout label="OPEN" value={displayPoint ? formatPrice(displayPoint.open) : "—"} />
        <Readout label="HIGH" value={displayPoint ? formatPrice(displayPoint.high) : "—"} />
        <Readout label="LOW" value={displayPoint ? formatPrice(displayPoint.low) : "—"} />
        <Readout label="CLOSE" value={displayPoint ? formatPrice(displayPoint.close) : "—"} />
        <Readout label="CHANGE" value={displayPoint ? formatSignedPercent(change) : "—"} tone={change >= 0 ? "positive" : "negative"} />
        <Readout label="VOLUME" value={displayPoint ? formatCompactVolume(displayPoint.volume) : "—"} />
      </div>

      <div className="chart-legend" aria-label="图例">
        <span><i className="legend-candle" />OHLC</span>
        <span><i className="legend-ma20" />MA20</span>
        <span><i className="legend-ma60" />MA60</span>
        <span><i className="legend-entry">▲</i>入场</span>
        <span><i className="legend-exit">▼</i>出场</span>
      </div>

      <div className="price-chart-shell" ref={shellRef}>
        <canvas
          ref={canvasRef}
          aria-label={ariaLabel}
          onPointerMove={handlePointerMove}
          onPointerLeave={() => setHover(null)}
        />
        {hover && displayPoint ? (
          <div className="price-tooltip" style={tooltipPosition(hover, chartSize)}>
            <strong>{formatMarketTimestamp(displayPoint.date, ktype)}</strong>
            <span><em>开</em><b>{formatPrice(displayPoint.open)}</b></span>
            <span><em>高</em><b>{formatPrice(displayPoint.high)}</b></span>
            <span><em>低</em><b>{formatPrice(displayPoint.low)}</b></span>
            <span><em>收</em><b>{formatPrice(displayPoint.close)}</b></span>
            <span><em>涨跌</em><b>{formatSignedPercent(change)}</b></span>
            <span><em>成交量</em><b>{formatNumber(displayPoint.volume, 0)}</b></span>
          </div>
        ) : null}
      </div>
      <p className="chart-method">价格轴按当前可见区间缩放；成交量从零起算。移动光标查看每根 K 线的准确价格。</p>
    </section>
  );
}

interface ReadoutProps {
  label: string;
  value: string;
  tone?: string;
}

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

function drawChart(options: DrawOptions): ChartGeometry | null {
  const { context, width, height, points, trades, ma20, ma60, range, hoverIndex, ktype } = options;
  if (points.length === 0) {
    context.fillStyle = "#667c7d";
    context.font = '11px "SFMono-Regular", Menlo, monospace';
    context.fillText("本次回测未返回可绘制的 OpenD OHLCV 数据。", 18, 34);
    return null;
  }

  const visibleCount = range === "all" ? points.length : Math.min(range, points.length);
  const startIndex = points.length - visibleCount;
  const visible = points.slice(startIndex);
  const compact = width < 560;
  const plotLeft = compact ? 10 : 18;
  const plotRight = width - (compact ? 48 : 64);
  const priceTop = 24;
  const priceBottom = height - (compact ? 112 : 124);
  const volumeTop = priceBottom + 27;
  const volumeBottom = height - 36;
  const step = (plotRight - plotLeft) / visible.length;
  const candleWidth = Math.max(1, Math.min(8, step * 0.64));
  const rawMin = visible.reduce((minimum, point) => Math.min(minimum, point.low), Infinity);
  const rawMax = visible.reduce((maximum, point) => Math.max(maximum, point.high), -Infinity);
  const spread = Math.max(rawMax - rawMin, Math.abs(rawMax) * 0.01, 0.01);
  const priceMin = rawMin - spread * 0.055;
  const priceMax = rawMax + spread * 0.055;
  const volumeMax = visible.reduce((maximum, point) => Math.max(maximum, point.volume), 1);
  const xForLocal = (index: number) => plotLeft + (index + 0.5) * step;
  const yForPrice = (price: number) => priceTop + ((priceMax - price) / (priceMax - priceMin)) * (priceBottom - priceTop);
  const yForVolume = (volume: number) => volumeBottom - (volume / volumeMax) * (volumeBottom - volumeTop);

  drawGrid(context, { width, height, plotLeft, plotRight, priceTop, priceBottom, volumeTop, volumeBottom, priceMin, priceMax, visible, xForLocal, ktype });
  drawVolumes(context, visible, xForLocal, yForVolume, candleWidth, volumeBottom);
  drawAverage(context, ma20, startIndex, visible.length, xForLocal, yForPrice, "#278779", []);
  drawAverage(context, ma60, startIndex, visible.length, xForLocal, yForPrice, "#d58a35", [5, 4]);
  drawCandles(context, visible, xForLocal, yForPrice, candleWidth);
  drawTradeMarkers(context, visible, trades, xForLocal, yForPrice);

  if (hoverIndex !== null && hoverIndex >= startIndex && hoverIndex < points.length) {
    const localIndex = hoverIndex - startIndex;
    const x = xForLocal(localIndex);
    const y = yForPrice(points[hoverIndex].close);
    context.save();
    context.strokeStyle = "rgba(16, 42, 50, 0.48)";
    context.setLineDash([3, 4]);
    context.beginPath();
    context.moveTo(x, priceTop);
    context.lineTo(x, volumeBottom);
    context.moveTo(plotLeft, y);
    context.lineTo(plotRight, y);
    context.stroke();
    context.restore();
  }
  return { plotLeft, plotRight, step, startIndex, visibleLength: visible.length };
}

interface GridOptions {
  width: number;
  height: number;
  plotLeft: number;
  plotRight: number;
  priceTop: number;
  priceBottom: number;
  volumeTop: number;
  volumeBottom: number;
  priceMin: number;
  priceMax: number;
  visible: PricePoint[];
  xForLocal: (index: number) => number;
  ktype: string;
}

function drawGrid(context: CanvasRenderingContext2D, options: GridOptions) {
  const { width, height, plotLeft, plotRight, priceTop, priceBottom, volumeTop, volumeBottom, priceMin, priceMax, visible, xForLocal, ktype } = options;
  context.save();
  context.font = '9px "SFMono-Regular", Menlo, monospace';
  context.fillStyle = "#667c7d";
  context.strokeStyle = "rgba(120, 144, 142, 0.35)";
  for (let tick = 0; tick < 5; tick += 1) {
    const ratio = tick / 4;
    const y = priceTop + ratio * (priceBottom - priceTop);
    const price = priceMax - ratio * (priceMax - priceMin);
    context.beginPath();
    context.moveTo(plotLeft, Math.round(y) + 0.5);
    context.lineTo(plotRight, Math.round(y) + 0.5);
    context.stroke();
    context.fillText(formatPrice(price), plotRight + 7, y + 3);
  }
  context.beginPath();
  context.moveTo(plotLeft, volumeTop - 9.5);
  context.lineTo(plotRight, volumeTop - 9.5);
  context.stroke();
  context.fillText("VOL", plotLeft, volumeTop - 14);
  context.fillText("0", plotRight + 7, volumeBottom + 3);

  const tickCount = width < 560 ? 3 : 5;
  const sameDay = shortDate(visible[0].date) === shortDate(visible.at(-1)!.date);
  for (let tick = 0; tick < tickCount; tick += 1) {
    const localIndex = Math.round((tick / (tickCount - 1)) * (visible.length - 1));
    const x = xForLocal(localIndex);
    const label = compactChartDate(visible[localIndex].date, sameDay, ktype);
    const labelWidth = context.measureText(label).width;
    context.fillText(label, Math.max(2, Math.min(width - labelWidth - 2, x - labelWidth / 2)), height - 14);
  }
  context.restore();
}

function drawVolumes(context: CanvasRenderingContext2D, visible: PricePoint[], xForLocal: (index: number) => number, yForVolume: (volume: number) => number, candleWidth: number, volumeBottom: number) {
  visible.forEach((point, index) => {
    const y = yForVolume(point.volume);
    context.fillStyle = point.close >= point.open ? "rgba(39, 135, 121, 0.30)" : "rgba(213, 138, 53, 0.38)";
    context.fillRect(xForLocal(index) - candleWidth / 2, y, Math.max(1, candleWidth), volumeBottom - y);
  });
}

function drawCandles(context: CanvasRenderingContext2D, visible: PricePoint[], xForLocal: (index: number) => number, yForPrice: (price: number) => number, candleWidth: number) {
  visible.forEach((point, index) => {
    const rising = point.close >= point.open;
    const color = rising ? "#278779" : "#d58a35";
    const x = xForLocal(index);
    const yOpen = yForPrice(point.open);
    const yClose = yForPrice(point.close);
    const bodyTop = Math.min(yOpen, yClose);
    const bodyHeight = Math.max(1, Math.abs(yClose - yOpen));
    context.strokeStyle = color;
    context.lineWidth = Math.max(1, Math.min(1.4, candleWidth * 0.22));
    context.beginPath();
    context.moveTo(x, yForPrice(point.high));
    context.lineTo(x, yForPrice(point.low));
    context.stroke();
    if (rising) {
      context.fillStyle = "#f7faf8";
      context.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight);
      context.strokeRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight);
    } else {
      context.fillStyle = color;
      context.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight);
    }
  });
}

function drawAverage(context: CanvasRenderingContext2D, averages: Array<number | null>, startIndex: number, visibleLength: number, xForLocal: (index: number) => number, yForPrice: (price: number) => number, color: string, dash: number[]) {
  context.save();
  context.strokeStyle = color;
  context.lineWidth = 1.6;
  context.setLineDash(dash);
  context.beginPath();
  let started = false;
  for (let localIndex = 0; localIndex < visibleLength; localIndex += 1) {
    const value = averages[startIndex + localIndex];
    if (value === null) continue;
    const x = xForLocal(localIndex);
    const y = yForPrice(value);
    if (!started) { context.moveTo(x, y); started = true; } else { context.lineTo(x, y); }
  }
  if (started) context.stroke();
  context.restore();
}

function drawTradeMarkers(context: CanvasRenderingContext2D, visible: PricePoint[], trades: Trade[], xForLocal: (index: number) => number, yForPrice: (price: number) => number) {
  const indexByDate = new Map(visible.map((point, index) => [marketTimeKey(point.date), index]));
  trades.forEach((trade) => {
    const entryIndex = indexByDate.get(marketTimeKey(trade.entry_date));
    if (entryIndex !== undefined) drawTriangle(context, xForLocal(entryIndex), yForPrice(visible[entryIndex].low) + 13, "up", "#278779");
    const exitIndex = indexByDate.get(marketTimeKey(trade.exit_date));
    if (exitIndex !== undefined) drawTriangle(context, xForLocal(exitIndex), yForPrice(visible[exitIndex].high) - 13, "down", "#d58a35");
  });
}

function drawTriangle(context: CanvasRenderingContext2D, x: number, y: number, direction: "up" | "down", color: string) {
  const size = 6;
  context.save();
  context.fillStyle = color;
  context.strokeStyle = "#f7faf8";
  context.beginPath();
  if (direction === "up") {
    context.moveTo(x, y - size); context.lineTo(x - size, y + size); context.lineTo(x + size, y + size);
  } else {
    context.moveTo(x, y + size); context.lineTo(x - size, y - size); context.lineTo(x + size, y - size);
  }
  context.closePath(); context.fill(); context.stroke(); context.restore();
}

function compactChartDate(value: string, sameDay: boolean, ktype: string): string {
  const timestamp = value.replace("T", " ");
  if (!isIntradayKline(ktype)) return timestamp.slice(2, 10);
  return sameDay ? timestamp.slice(11, 16) : timestamp.slice(5, 16);
}
