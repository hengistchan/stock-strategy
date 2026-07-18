import { useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import type { EquityPoint, Trade } from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import type { Locale } from "../i18n/core";
import {
  formatMarketTimestamp,
  formatNumber,
  formatSignedCurrency,
  formatSignedPercent,
} from "../lib/format";

interface PerformanceChartProps {
  equity: EquityPoint[];
  equityCount: number;
  trades: Trade[];
  ktype: string;
  reportUrl: string;
}

interface HoverState {
  kind: "equity" | "trade";
  index: number;
  x: number;
  y: number;
}

export function PerformanceChart({ equity, equityCount, trades, ktype, reportUrl }: PerformanceChartProps) {
  const { locale, t } = useI18n();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const shellRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [hover, setHover] = useState<HoverState | null>(null);

  useEffect(() => {
    const shell = shellRef.current;
    if (!shell) return undefined;
    const observer = new ResizeObserver(([entry]) => {
      setSize({ width: Math.round(entry.contentRect.width), height: Math.round(entry.contentRect.height) });
    });
    observer.observe(shell);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !size.width || !size.height) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(size.width * dpr);
    canvas.height = Math.round(size.height * dpr);
    const context = canvas.getContext("2d");
    if (!context) return;
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    context.clearRect(0, 0, size.width, size.height);
    drawPerformance(context, size.width, size.height, equity, trades, hover, locale, {
      equity: t("performance.equity"),
      drawdown: t("performance.drawdown"),
      pnl: t("performance.tradePnl"),
      noData: t("performance.noData"),
    });
  }, [equity, hover, locale, size, t, trades]);

  function handlePointerMove(event: ReactPointerEvent<HTMLCanvasElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const left = size.width < 560 ? 48 : 62;
    const right = size.width - 18;
    if (x < left || x > right) {
      setHover(null);
      return;
    }
    const ratio = Math.max(0, Math.min(1, (x - left) / Math.max(1, right - left)));
    const isTrade = y > size.height * 0.70;
    const rows = isTrade ? trades : equity;
    if (!rows.length) {
      setHover(null);
      return;
    }
    setHover({ kind: isTrade ? "trade" : "equity", index: Math.round(ratio * (rows.length - 1)), x, y });
  }

  const equityPoint = hover?.kind === "equity" ? equity[hover.index] : undefined;
  const trade = hover?.kind === "trade" ? trades[hover.index] : undefined;

  return (
    <section className="performance-section" aria-labelledby="performanceTitle">
      <div className="performance-heading">
        <div>
          <span className="section-code">PERFORMANCE</span>
          <h3 id="performanceTitle">{t("performance.title")}</h3>
          <p>{t("performance.summary", { points: formatNumber(equityCount, 0, locale), trades: formatNumber(trades.length, 0, locale) })}</p>
        </div>
        <a href={reportUrl} target="_blank" rel="noreferrer">{t("performance.staticReport")} ↗</a>
      </div>
      <div className="performance-legend" aria-label={t("chart.legend")}>
        <span><i className="legend-equity" />{t("performance.strategyEquity")}</span>
        <span><i className="legend-benchmark" />{t("performance.benchmark")}</span>
        <span><i className="legend-drawdown" />{t("performance.drawdown")}</span>
        <span><i className="legend-profit" />{t("performance.profit")}</span>
        <span><i className="legend-loss" />{t("performance.loss")}</span>
        <em>{t("performance.hoverHint")}</em>
      </div>
      <div className="performance-chart-shell" ref={shellRef}>
        <canvas
          ref={canvasRef}
          aria-label={t("performance.aria")}
          onPointerMove={handlePointerMove}
          onPointerLeave={() => setHover(null)}
        />
        {equityPoint ? (
          <div className="performance-tooltip" style={performanceTooltipPosition(hover!, size)}>
            <strong>{formatMarketTimestamp(equityPoint.date, ktype)}</strong>
            <span><em>{t("performance.strategyEquity")}</em><b>{formatNumber(equityPoint.equity, 2, locale)}</b></span>
            <span><em>{t("performance.benchmark")}</em><b>{formatNumber(equityPoint.benchmark, 2, locale)}</b></span>
            <span><em>{t("performance.drawdown")}</em><b className="negative">{formatSignedPercent(equityPoint.drawdown * 100, locale)}</b></span>
          </div>
        ) : null}
        {trade ? (
          <div className="performance-tooltip" style={performanceTooltipPosition(hover!, size)}>
            <strong>#{trade.trade_id} · {formatMarketTimestamp(trade.exit_date, ktype)}</strong>
            <span><em>{t("trades.pnl")}</em><b className={trade.net_pnl >= 0 ? "positive" : "negative"}>{formatSignedCurrency(trade.net_pnl, locale)}</b></span>
            <span><em>{t("trades.return")}</em><b>{formatSignedPercent(trade.return_pct, locale)}</b></span>
            <span><em>{t("trades.reason")}</em><b>{trade.exit_reason}</b></span>
          </div>
        ) : null}
      </div>
    </section>
  );
}

interface PanelLabels { equity: string; drawdown: string; pnl: string; noData: string }

function drawPerformance(
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
  equity: EquityPoint[],
  trades: Trade[],
  hover: HoverState | null,
  locale: Locale,
  labels: PanelLabels,
) {
  if (!equity.length) {
    context.fillStyle = "#667c7d";
    context.font = '11px "SFMono-Regular", Menlo, monospace';
    context.fillText(labels.noData, 18, 34);
    return;
  }
  const left = width < 560 ? 48 : 62;
  const right = width - 18;
  const plotWidth = Math.max(1, right - left);
  const equityTop = 28;
  const equityBottom = height * 0.42;
  const drawdownTop = height * 0.50;
  const drawdownBottom = height * 0.65;
  const pnlTop = height * 0.73;
  const pnlBottom = height - 34;
  const xFor = (index: number, count: number) => left + (count <= 1 ? 0 : (index / (count - 1)) * plotWidth);
  const equityValues = equity.flatMap((point) => [point.equity, point.benchmark]);
  const equityMin = Math.min(...equityValues);
  const equityMax = Math.max(...equityValues);
  const equitySpread = Math.max(equityMax - equityMin, Math.abs(equityMax) * 0.01, 1);
  const equityY = (value: number) => equityBottom - ((value - equityMin) / equitySpread) * (equityBottom - equityTop);
  const drawdownMin = Math.min(...equity.map((point) => point.drawdown), -0.0001);
  const drawdownY = (value: number) => drawdownTop + (value / drawdownMin) * (drawdownBottom - drawdownTop);
  const pnlAbs = Math.max(...trades.map((trade) => Math.abs(trade.net_pnl)), 1);
  const pnlZero = (pnlTop + pnlBottom) / 2;
  const pnlY = (value: number) => pnlZero - (value / pnlAbs) * ((pnlBottom - pnlTop) / 2);

  context.save();
  context.font = '9px "SFMono-Regular", Menlo, monospace';
  context.fillStyle = "#667c7d";
  context.strokeStyle = "rgba(120, 144, 142, 0.32)";
  context.fillText(labels.equity.toUpperCase(), left, 14);
  context.fillText(labels.drawdown.toUpperCase(), left, drawdownTop - 10);
  context.fillText(labels.pnl.toUpperCase(), left, pnlTop - 10);
  [equityTop, (equityTop + equityBottom) / 2, equityBottom, drawdownTop, drawdownBottom, pnlZero].forEach((y) => {
    context.beginPath(); context.moveTo(left, Math.round(y) + 0.5); context.lineTo(right, Math.round(y) + 0.5); context.stroke();
  });
  context.fillText(formatNumber(equityMax, 0, locale), 4, equityTop + 3);
  context.fillText(formatNumber(equityMin, 0, locale), 4, equityBottom + 3);
  context.fillText("0%", 12, drawdownTop + 3);
  context.fillText(formatSignedPercent(drawdownMin * 100, locale), 2, drawdownBottom + 3);

  drawLine(context, equity.map((point) => point.equity), xFor, equityY, "#278779", []);
  drawLine(context, equity.map((point) => point.benchmark), xFor, equityY, "#d58a35", [5, 4]);

  context.beginPath();
  equity.forEach((point, index) => {
    const x = xFor(index, equity.length); const y = drawdownY(point.drawdown);
    if (index === 0) context.moveTo(x, drawdownTop); context.lineTo(x, y);
  });
  context.lineTo(right, drawdownTop); context.closePath();
  context.fillStyle = "rgba(213, 138, 53, 0.18)"; context.fill();
  drawLine(context, equity.map((point) => point.drawdown), xFor, drawdownY, "#b86832", []);

  const barWidth = Math.max(1, Math.min(5, plotWidth / Math.max(1, trades.length) * 0.76));
  trades.forEach((trade, index) => {
    const x = xFor(index, trades.length); const y = pnlY(trade.net_pnl);
    context.fillStyle = trade.net_pnl >= 0 ? "rgba(39, 135, 121, 0.72)" : "rgba(184, 104, 50, 0.72)";
    context.fillRect(x - barWidth / 2, Math.min(y, pnlZero), barWidth, Math.max(1, Math.abs(y - pnlZero)));
  });

  if (hover) {
    const count = hover.kind === "trade" ? trades.length : equity.length;
    const x = xFor(hover.index, count);
    context.strokeStyle = "rgba(16, 42, 50, 0.52)"; context.setLineDash([3, 4]);
    context.beginPath(); context.moveTo(x, equityTop); context.lineTo(x, pnlBottom); context.stroke();
  }
  context.restore();
}

function drawLine(context: CanvasRenderingContext2D, values: number[], xFor: (index: number, count: number) => number, yFor: (value: number) => number, color: string, dash: number[]) {
  if (!values.length) return;
  context.save(); context.strokeStyle = color; context.lineWidth = 1.6; context.setLineDash(dash); context.beginPath();
  values.forEach((value, index) => {
    const x = xFor(index, values.length); const y = yFor(value);
    if (index === 0) context.moveTo(x, y); else context.lineTo(x, y);
  });
  context.stroke(); context.restore();
}

function performanceTooltipPosition(hover: HoverState, size: { width: number; height: number }) {
  const width = 224;
  const height = 112;
  return {
    left: hover.x > size.width - width - 24 ? hover.x - width - 12 : hover.x + 12,
    top: Math.max(8, Math.min(size.height - height - 8, hover.y - 42)),
  };
}
