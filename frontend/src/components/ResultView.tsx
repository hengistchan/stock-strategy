import type { BacktestJob, BacktestResult } from "../api/types";
import { formatDateTime, formatNumber, formatSignedCurrency, shortDate } from "../lib/format";
import { MetricsGrid } from "./MetricsGrid";
import { PriceChart } from "./PriceChart";
import { TradeTable } from "./TradeTable";

interface ResultViewProps {
  job?: BacktestJob;
  result?: BacktestResult;
  loading: boolean;
}

export function ResultView({ job, result, loading }: ResultViewProps) {
  if (!job) {
    return (
      <section className="result-empty">
        <div className="empty-plot" aria-hidden="true"><span /><span /><span /><span /><span /><i /></div>
        <div><p className="eyebrow">No run selected</p><h2>把一段策略变成一条可复查的证据链。</h2><p>选择策略、标的和区间后运行。这里会展示 OpenD 行情、价格、资金曲线、回撤、成交与费用。</p></div>
      </section>
    );
  }

  if (job.status !== "succeeded" || loading || !result) {
    const copy = {
      queued: ["任务已入队", "正在准备回测进程", "配置已保存，等待启动。"],
      running: ["OpenD 数据流", `正在回测 ${job.request.symbol}`, `${job.request.start} → ${job.request.end} · ${job.request.ktype}`],
      failed: ["运行未通过", "这次回测没有完成", job.error ?? "查看运行日志以定位问题。"],
      succeeded: ["正在读取结果", "回测已经完成", "正在加载指标和 OpenD 行情。"],
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
  const hasOpenPosition = Math.abs(endingPosition?.quantity ?? 0) > 1e-9;
  const contractVersion = summary.settings.engine_contract?.version;
  const isLegacyResult = contractVersion !== 2;
  return (
    <section className="result-sheet">
      <div className="result-title-row">
        <div>
          <p className="eyebrow">{summary.strategy.toUpperCase().replaceAll("_", " ")}</p>
          <h2>{summary.symbol} <small>{shortDate(summary.period.start)} → {shortDate(summary.period.end)}</small></h2>
          <p className="completion-time">完成于 {formatDateTime(job.finished_at)}</p>
        </div>
        <div className="evidence-stamp" data-legacy={isLegacyResult}>
          <span>{isLegacyResult ? "LEGACY RESULT" : `OPEND CONTRACT V${contractVersion}`}</span>
          <small>{summary.period.bars} bars · {autype} · {session}</small>
        </div>
      </div>

      <MetricsGrid metrics={summary.metrics} />
      {isLegacyResult ? (
        <aside className="legacy-result-warning" role="status">
          该任务由旧版撮合契约生成，可能包含未校验的周期、时段或期末强平语义。请使用当前配置重新运行后再比较策略效果。
        </aside>
      ) : null}
      {hasOpenPosition && endingPosition ? (
        <aside className="ending-position" aria-label="期末未平仓持仓">
          <div><span>OPEN POSITION</span><strong>期末持仓未强平</strong></div>
          <dl>
            <div><dt>方向 / 数量</dt><dd>{endingPosition.side} · {formatNumber(Math.abs(endingPosition.quantity), 0)}</dd></div>
            <div><dt>持仓均价</dt><dd>{formatNumber(endingPosition.average_price, 2)}</dd></div>
            <div><dt>期末标记价</dt><dd>{formatNumber(endingPosition.mark_price, 2)}</dd></div>
            <div><dt>未实现盈亏</dt><dd className={endingPosition.unrealized_pnl >= 0 ? "positive" : "negative"}>{formatSignedCurrency(endingPosition.unrealized_pnl)}</dd></div>
          </dl>
        </aside>
      ) : null}
      <PriceChart points={priceSeries} trades={trades} symbol={summary.symbol} ktype={ktype} autype={autype} />

      <figure className="report-frame">
        <figcaption><span>资金曲线 / 回撤 / 逐笔盈亏</span><span>RUN {job.id}</span></figcaption>
        <img src={`${result.report_url}?v=${encodeURIComponent(job.finished_at ?? "")}`} alt="回测资金曲线、基准、回撤和逐笔盈亏图" />
      </figure>

      <TradeTable trades={trades} ktype={ktype} exposure={summary.metrics.exposure_pct} />
      <p className="research-note">历史回测用于研究与机制验证，不构成买卖建议。少量交易不足以证明策略稳健。</p>
    </section>
  );
}
