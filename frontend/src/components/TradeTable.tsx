import type { Trade } from "../api/types";
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
  return (
    <section className="trade-section">
      <div className="trade-heading">
        <div><span className="section-code">TRADES</span><h3>成交账簿</h3></div>
        <p>{trades.length} 笔闭合交易 · 资金使用率 {formatNumber(exposure, 1)}%</p>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>#</th><th>方向</th><th>入场</th><th>出场</th><th>数量</th><th>净盈亏</th><th>收益率</th><th>退出</th></tr></thead>
          <tbody>
            {trades.length === 0 ? (
              <tr><td colSpan={8}>本次没有闭合交易。检查预热、信号条件与行情区间。</td></tr>
            ) : trades.map((trade) => (
              <tr key={trade.trade_id}>
                <td>{trade.trade_id}</td><td>{trade.side}</td>
                <td>{formatMarketTimestamp(trade.entry_date, ktype)}</td>
                <td>{formatMarketTimestamp(trade.exit_date, ktype)}</td>
                <td>{formatNumber(trade.quantity, 0)}</td>
                <td className={trade.net_pnl >= 0 ? "positive" : "negative"}>{formatSignedCurrency(trade.net_pnl)}</td>
                <td className={trade.return_pct >= 0 ? "positive" : "negative"}>{formatSignedPercent(trade.return_pct)}</td>
                <td>{trade.exit_reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
