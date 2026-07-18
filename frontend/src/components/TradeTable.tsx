import { useMemo, useState } from "react";
import type { Trade } from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import {
  formatMarketTimestamp,
  formatNumber,
  formatSignedCurrency,
  formatSignedPercent,
} from "../lib/format";

interface TradeTableProps {
  trades: Trade[];
  ktype: string;
  exposure: number;
}

export function TradeTable({ trades, ktype, exposure }: TradeTableProps) {
  const { locale, t } = useI18n();
  const [pageSize, setPageSize] = useState(25);
  const [page, setPage] = useState(1);
  const pageCount = Math.max(1, Math.ceil(trades.length / pageSize));
  const effectivePage = Math.min(page, pageCount);
  const visibleTrades = useMemo(
    () => trades.slice((effectivePage - 1) * pageSize, effectivePage * pageSize),
    [effectivePage, pageSize, trades],
  );
  const firstRow = trades.length ? (effectivePage - 1) * pageSize + 1 : 0;
  const lastRow = Math.min(effectivePage * pageSize, trades.length);
  return (
    <section className="trade-section">
      <div className="trade-heading">
        <div><span className="section-code">TRADES</span><h3>{t("trades.title")}</h3></div>
        <p>{t("trades.summary", { count: trades.length, exposure: formatNumber(exposure, 1, locale) })}</p>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>#</th><th>{t("trades.side")}</th><th>{t("trades.entry")}</th><th>{t("trades.exit")}</th><th>{t("trades.quantity")}</th><th>{t("trades.pnl")}</th><th>{t("trades.return")}</th><th>{t("trades.reason")}</th></tr></thead>
          <tbody>
            {trades.length === 0 ? (
              <tr><td colSpan={8}>{t("trades.empty")}</td></tr>
            ) : visibleTrades.map((trade) => (
              <tr key={trade.trade_id}>
                <td>{trade.trade_id}</td><td>{trade.side}</td>
                <td>{formatMarketTimestamp(trade.entry_date, ktype)}</td>
                <td>{formatMarketTimestamp(trade.exit_date, ktype)}</td>
                <td>{formatNumber(trade.quantity, 0, locale)}</td>
                <td className={trade.net_pnl >= 0 ? "positive" : "negative"}>{formatSignedCurrency(trade.net_pnl, locale)}</td>
                <td className={trade.return_pct >= 0 ? "positive" : "negative"}>{formatSignedPercent(trade.return_pct, locale)}</td>
                <td>{trade.exit_reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {trades.length > 0 ? (
        <nav className="trade-pagination" aria-label={t("trades.pagination")}>
          <span>{t("trades.rows", { start: firstRow, end: lastRow, total: formatNumber(trades.length, 0, locale) })}</span>
          <label>
            {t("trades.perPage")}
            <select value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1); }}>
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </label>
          <div>
            <button type="button" onClick={() => setPage(1)} disabled={effectivePage === 1} aria-label={t("trades.firstPage")}>«</button>
            <button type="button" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={effectivePage === 1} aria-label={t("trades.previousPage")}>‹</button>
            <label className="trade-page-input">
              {t("trades.page")}
              <input
                type="number"
                min={1}
                max={pageCount}
                value={effectivePage}
                onChange={(event) => setPage(Math.max(1, Math.min(pageCount, Number(event.target.value) || 1)))}
              />
              <span>/ {pageCount}</span>
            </label>
            <button type="button" onClick={() => setPage((current) => Math.min(pageCount, current + 1))} disabled={effectivePage === pageCount} aria-label={t("trades.nextPage")}>›</button>
            <button type="button" onClick={() => setPage(pageCount)} disabled={effectivePage === pageCount} aria-label={t("trades.lastPage")}>»</button>
          </div>
        </nav>
      ) : null}
    </section>
  );
}
