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
            ) : trades.map((trade) => (
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
    </section>
  );
}
