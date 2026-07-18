import { useState } from "react";
import type { Experiment, ExperimentRun } from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import type { Locale } from "../i18n/core";
import { formatDateTime, formatNumber, formatSignedPercent } from "../lib/format";

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
  const { locale, t } = useI18n();
  const objectiveLabels: Record<string, string> = {
    sharpe_ratio: "Sharpe",
    total_return_pct: t("metrics.return"),
    max_drawdown_pct: t("metrics.drawdown"),
  };
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
      <aside className="experiment-ledger" aria-label={t("experiment.archiveAria")}>
        <div className="experiment-ledger-heading">
          <span className="section-code">EXPERIMENTS</span>
          <h2>{t("experiment.archive")}</h2>
        </div>
        <div className="experiment-ledger-list">
          {experiments.length === 0 ? <p className="quiet-state">{t("experiment.emptyArchive")}</p> : null}
          {experiments.map((item) => (
            <button
              key={item.id}
              type="button"
              aria-current={item.id === activeExperimentId ? "true" : undefined}
              onClick={() => onSelectExperiment(item.id)}
            >
              <span className={`history-mark ${item.status}`} aria-hidden="true" />
              <span><strong>{item.name}</strong><small>{item.progress.completed}/{item.progress.total} · {objectiveLabels[item.objective]}</small></span>
              <time>{formatDateTime(item.created_at, locale)}</time>
            </button>
          ))}
        </div>
      </aside>

      <div className="experiment-results">
        {!experiment ? (
          <div className="experiment-empty">
            <span className="section-code">NO MATRIX YET</span>
            <h2>{t("experiment.emptyTitle")}</h2>
            <p>{t("experiment.emptyBody")}</p>
          </div>
        ) : (
          <>
            <header className="experiment-title">
              <div>
                <span className="section-code">RANKING TAPE</span>
                <h2>{experiment.name}</h2>
                <p>{experiment.strategy_path} · {experiment.base_request.symbol} · {t("experiment.priority", { objective: objectiveLabels[experiment.objective] })}</p>
              </div>
              <div className="experiment-progress" data-status={experiment.status}>
                <strong>{experiment.progress.completed}/{experiment.progress.total}</strong>
                <span>{t(`status.${experiment.status}`)}</span>
              </div>
            </header>

            <div className="experiment-progress-track" aria-label={t("experiment.progress", { completed: experiment.progress.completed, total: experiment.progress.total })}>
              <span style={{ width: `${experiment.progress.total ? experiment.progress.completed / experiment.progress.total * 100 : 0}%` }} />
            </div>

            {comparableRuns.length > 0 ? (
              <section className="comparison-strip" aria-label={t("experiment.comparisonAria")}>
                <div className="comparison-heading"><span>COMPARE</span><strong>{comparableRuns.length} / 3</strong></div>
                {comparableRuns.map((run) => <ComparisonCard key={run.job_id} run={run} onOpenRun={onOpenRun} />)}
              </section>
            ) : (
              <p className="comparison-hint">{t("experiment.comparisonHint")}</p>
            )}

            <div className="experiment-table-wrap">
              <table className="experiment-table">
                <thead><tr><th>{t("experiment.compare")}</th><th>{t("experiment.rank")}</th><th>{t("experiment.parameters")}</th><th>{t("metrics.return")}</th><th>Sharpe</th><th>{t("metrics.drawdown")}</th><th>{t("metrics.trades")}</th><th>{t("experiment.result")}</th></tr></thead>
                <tbody>
                  {orderedRuns.map((run) => {
                    const selected = Boolean(run.job_id && selectedJobIds.includes(run.job_id));
                    return (
                      <tr key={run.index} data-status={run.status}>
                        <td><input aria-label={t("experiment.compareRun", { index: run.index })} type="checkbox" checked={selected} disabled={run.status !== "succeeded"} onChange={() => toggleComparison(run)} /></td>
                        <td className="rank-cell">{run.rank ? `#${run.rank}` : "—"}</td>
                        <td><ParameterSet parameters={run.parameters} /></td>
                        <td className={tone(run.metrics?.total_return_pct)}>{metricPercent(run.metrics?.total_return_pct, locale)}</td>
                        <td className={tone(run.metrics?.sharpe_ratio)}>{metricNumber(run.metrics?.sharpe_ratio, locale)}</td>
                        <td className={tone(run.metrics?.max_drawdown_pct)}>{metricPercent(run.metrics?.max_drawdown_pct, locale)}</td>
                        <td>{run.metrics?.total_trades ?? "—"}</td>
                        <td>{run.job_id && run.status === "succeeded" ? <button type="button" onClick={() => onOpenRun(run.job_id!)}>{t("experiment.fullReport")}</button> : <span>{run.status === "failed" ? run.error : t(`status.${run.status}`)}</span>}</td>
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
  const { locale, t } = useI18n();
  return (
    <article className="comparison-card">
      <header><span>#{run.rank}</span><ParameterSet parameters={run.parameters} /></header>
      <dl>
        <div><dt>{t("metrics.return")}</dt><dd className={tone(run.metrics?.total_return_pct)}>{metricPercent(run.metrics?.total_return_pct, locale)}</dd></div>
        <div><dt>Sharpe</dt><dd>{metricNumber(run.metrics?.sharpe_ratio, locale)}</dd></div>
        <div><dt>{t("metrics.drawdown")}</dt><dd>{metricPercent(run.metrics?.max_drawdown_pct, locale)}</dd></div>
      </dl>
      <button type="button" onClick={() => onOpenRun(run.job_id!)}>{t("experiment.viewEvidence")}</button>
    </article>
  );
}

function ParameterSet({ parameters }: { parameters: ExperimentRun["parameters"] }) {
  return <span className="parameter-set">{Object.entries(parameters).map(([name, value]) => <code key={name}>{name}={String(value)}</code>)}</span>;
}

function metricPercent(value: number | undefined, locale: Locale): string {
  return value === undefined ? "—" : formatSignedPercent(value, locale);
}

function metricNumber(value: number | undefined, locale: Locale): string {
  return value === undefined ? "—" : formatNumber(value, 2, locale);
}

function tone(value: number | undefined): string {
  if (value === undefined || value === 0) return "";
  return value > 0 ? "positive" : "negative";
}
