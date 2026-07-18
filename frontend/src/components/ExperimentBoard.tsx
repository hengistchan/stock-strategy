import { useState } from "react";
import type { Experiment, ExperimentRun } from "../api/types";
import { formatDateTime, formatNumber, formatSignedPercent } from "../lib/format";

const OBJECTIVE_LABELS: Record<string, string> = {
  sharpe_ratio: "Sharpe",
  total_return_pct: "策略收益",
  max_drawdown_pct: "最大回撤",
};

interface ExperimentBoardProps {
  experiments: Experiment[];
  experiment?: Experiment;
  activeExperimentId: string | null;
  onSelectExperiment: (id: string) => void;
  onOpenRun: (jobId: string) => void;
}

export function ExperimentBoard({
  experiments,
  experiment,
  activeExperimentId,
  onSelectExperiment,
  onOpenRun,
}: ExperimentBoardProps) {
  const [selectedJobIds, setSelectedJobIds] = useState<string[]>([]);
  const orderedRuns = [...(experiment?.runs ?? [])].sort((left, right) => {
    if (left.rank === null && right.rank === null) return left.index - right.index;
    if (left.rank === null) return 1;
    if (right.rank === null) return -1;
    return left.rank - right.rank;
  });
  const comparableRuns = orderedRuns.filter(
    (run) => run.job_id && selectedJobIds.includes(run.job_id),
  );

  function toggleComparison(run: ExperimentRun) {
    if (!run.job_id || run.status !== "succeeded") return;
    setSelectedJobIds((current) => {
      if (current.includes(run.job_id!)) return current.filter((id) => id !== run.job_id);
      if (current.length >= 3) return [...current.slice(1), run.job_id!];
      return [...current, run.job_id!];
    });
  }

  return (
    <section className="experiment-board" aria-live="polite">
      <aside className="experiment-ledger" aria-label="参数实验记录">
        <div className="experiment-ledger-heading">
          <span className="section-code">EXPERIMENTS</span>
          <h2>实验档案</h2>
        </div>
        <div className="experiment-ledger-list">
          {experiments.length === 0 ? <p className="quiet-state">尚无参数实验。</p> : null}
          {experiments.map((item) => (
            <button
              key={item.id}
              type="button"
              aria-current={item.id === activeExperimentId ? "true" : undefined}
              onClick={() => onSelectExperiment(item.id)}
            >
              <span className={`history-mark ${item.status}`} aria-hidden="true" />
              <span><strong>{item.name}</strong><small>{item.progress.completed}/{item.progress.total} · {OBJECTIVE_LABELS[item.objective]}</small></span>
              <time>{formatDateTime(item.created_at)}</time>
            </button>
          ))}
        </div>
      </aside>

      <div className="experiment-results">
        {!experiment ? (
          <div className="experiment-empty">
            <span className="section-code">NO MATRIX YET</span>
            <h2>用相同市场条件，比较策略参数。</h2>
            <p>左侧定义候选值。每组参数都会生成独立、可回看的回测记录。</p>
          </div>
        ) : (
          <>
            <header className="experiment-title">
              <div>
                <span className="section-code">RANKING TAPE</span>
                <h2>{experiment.name}</h2>
                <p>{experiment.strategy_path} · {experiment.base_request.symbol} · {OBJECTIVE_LABELS[experiment.objective]}优先</p>
              </div>
              <div className="experiment-progress" data-status={experiment.status}>
                <strong>{experiment.progress.completed}/{experiment.progress.total}</strong>
                <span>{experiment.status === "running" ? "运行中" : experiment.status}</span>
              </div>
            </header>

            <div className="experiment-progress-track" aria-label={`已完成 ${experiment.progress.completed} / ${experiment.progress.total}`}>
              <span style={{ width: `${experiment.progress.total ? experiment.progress.completed / experiment.progress.total * 100 : 0}%` }} />
            </div>

            {comparableRuns.length > 0 ? (
              <section className="comparison-strip" aria-label="已选结果对比">
                <div className="comparison-heading"><span>COMPARE</span><strong>{comparableRuns.length} / 3</strong></div>
                {comparableRuns.map((run) => <ComparisonCard key={run.job_id} run={run} onOpenRun={onOpenRun} />)}
              </section>
            ) : (
              <p className="comparison-hint">勾选最多 3 个成功结果，固定在上方并排比较。</p>
            )}

            <div className="experiment-table-wrap">
              <table className="experiment-table">
                <thead><tr><th>比较</th><th>排名</th><th>参数</th><th>收益</th><th>Sharpe</th><th>最大回撤</th><th>交易</th><th>结果</th></tr></thead>
                <tbody>
                  {orderedRuns.map((run) => {
                    const selected = Boolean(run.job_id && selectedJobIds.includes(run.job_id));
                    return (
                      <tr key={run.index} data-status={run.status}>
                        <td><input aria-label={`比较第 ${run.index} 组`} type="checkbox" checked={selected} disabled={run.status !== "succeeded"} onChange={() => toggleComparison(run)} /></td>
                        <td className="rank-cell">{run.rank ? `#${run.rank}` : "—"}</td>
                        <td><ParameterSet parameters={run.parameters} /></td>
                        <td className={tone(run.metrics?.total_return_pct)}>{metricPercent(run.metrics?.total_return_pct)}</td>
                        <td className={tone(run.metrics?.sharpe_ratio)}>{metricNumber(run.metrics?.sharpe_ratio)}</td>
                        <td className={tone(run.metrics?.max_drawdown_pct)}>{metricPercent(run.metrics?.max_drawdown_pct)}</td>
                        <td>{run.metrics?.total_trades ?? "—"}</td>
                        <td>{run.job_id && run.status === "succeeded" ? <button type="button" onClick={() => onOpenRun(run.job_id!)}>完整报告</button> : <span>{run.status === "failed" ? run.error : run.status}</span>}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function ComparisonCard({ run, onOpenRun }: { run: ExperimentRun; onOpenRun: (jobId: string) => void }) {
  return (
    <article className="comparison-card">
      <header><span>#{run.rank}</span><ParameterSet parameters={run.parameters} /></header>
      <dl>
        <div><dt>收益</dt><dd className={tone(run.metrics?.total_return_pct)}>{metricPercent(run.metrics?.total_return_pct)}</dd></div>
        <div><dt>Sharpe</dt><dd>{metricNumber(run.metrics?.sharpe_ratio)}</dd></div>
        <div><dt>回撤</dt><dd>{metricPercent(run.metrics?.max_drawdown_pct)}</dd></div>
      </dl>
      <button type="button" onClick={() => onOpenRun(run.job_id!)}>查看回测证据 →</button>
    </article>
  );
}

function ParameterSet({ parameters }: { parameters: ExperimentRun["parameters"] }) {
  return <span className="parameter-set">{Object.entries(parameters).map(([name, value]) => <code key={name}>{name}={String(value)}</code>)}</span>;
}

function metricPercent(value: number | undefined): string {
  return value === undefined ? "—" : formatSignedPercent(value);
}

function metricNumber(value: number | undefined): string {
  return value === undefined ? "—" : formatNumber(value, 2);
}

function tone(value: number | undefined): string {
  if (value === undefined || value === 0) return "";
  return value > 0 ? "positive" : "negative";
}
