import { useState } from "react";
import type { BacktestJob } from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import { formatDateTime } from "../lib/format";

interface RunHistoryProps {
  jobs: BacktestJob[];
  activeJobId: string | null;
  onSelect: (jobId: string) => void;
  onRefresh: () => void;
  onCreate: () => void;
}

interface StrategyGroup {
  path: string;
  jobs: BacktestJob[];
}

interface SymbolGroup {
  symbol: string;
  jobs: BacktestJob[];
  strategies: StrategyGroup[];
}

const RUNS_PER_PAGE = 6;

export function RunHistory({ jobs, activeJobId, onSelect, onRefresh, onCreate }: RunHistoryProps) {
  const { locale, t } = useI18n();
  const [pages, setPages] = useState<Record<string, number>>({});
  const archive = groupJobs(jobs);
  const activeJob = jobs.find((job) => job.id === activeJobId) ?? jobs[0];
  const activeSymbol = archive.find((group) => group.symbol === activeJob?.request.symbol) ?? archive[0];
  const activeStrategy = activeSymbol?.strategies.find((group) => group.path === activeJob?.strategy_path)
    ?? activeSymbol?.strategies[0];
  const groupKey = `${activeSymbol?.symbol ?? ""}:${activeStrategy?.path ?? ""}`;
  const activeIndex = activeStrategy?.jobs.findIndex((job) => job.id === activeJob?.id) ?? 0;
  const inferredPage = Math.max(0, Math.floor(activeIndex / RUNS_PER_PAGE));
  const totalPages = Math.max(1, Math.ceil((activeStrategy?.jobs.length ?? 0) / RUNS_PER_PAGE));
  const page = Math.min(pages[groupKey] ?? inferredPage, totalPages - 1);
  const visibleJobs = activeStrategy?.jobs.slice(
    page * RUNS_PER_PAGE,
    (page + 1) * RUNS_PER_PAGE,
  ) ?? [];

  if (jobs.length === 0) {
    return (
      <section className="run-ledger archive-empty" aria-labelledby="runHistoryTitle">
        <span className="archive-empty-mark" aria-hidden="true">∅</span>
        <h3 id="runHistoryTitle">{t("history.empty")}</h3>
        <p>{t("history.emptyHint")}</p>
        <button type="button" onClick={onCreate}>{t("history.createFirst")} →</button>
      </section>
    );
  }

  return (
    <section className="run-ledger" aria-labelledby="runHistoryTitle">
      <div className="archive-tools">
        <span id="runHistoryTitle">{t("history.runCount", { count: jobs.length })}</span>
        <button className="text-button" type="button" onClick={onRefresh}>{t("common.refresh")}</button>
      </div>

      <div className="archive-stage">
        <span className="archive-stage-label">01 / {t("history.symbols")}</span>
        <nav className="symbol-index" aria-label={t("history.symbols")}>
          {archive.map((group) => (
            <button
              key={group.symbol}
              type="button"
              aria-current={group.symbol === activeSymbol?.symbol ? "true" : undefined}
              onClick={() => onSelect(group.jobs[0].id)}
            >
              <strong>{group.symbol}</strong>
              <small>{t("history.runCount", { count: group.jobs.length })} · {t("history.strategyCount", { count: group.strategies.length })}</small>
            </button>
          ))}
        </nav>
      </div>

      <div className="archive-stage">
        <span className="archive-stage-label">02 / {t("history.strategies")}</span>
        <nav className="strategy-index" aria-label={t("history.strategies")}>
          {activeSymbol?.strategies.map((group) => (
            <button
              key={group.path}
              type="button"
              aria-current={group.path === activeStrategy?.path ? "true" : undefined}
              onClick={() => onSelect(group.jobs[0].id)}
            >
              <span><strong>{strategyName(group.path)}</strong><small>{group.path}</small></span>
              <em>{group.jobs.length}</em>
            </button>
          ))}
        </nav>
      </div>

      <div className="archive-stage archive-runs">
        <span className="archive-stage-label">03 / {t("history.runs")}</span>
        <div className="history-list">
          {visibleJobs.map((job) => (
          <button
            key={job.id}
            className="history-item"
            type="button"
            aria-current={job.id === activeJobId}
            onClick={() => onSelect(job.id)}
          >
            <span className={`history-mark ${job.status}`} aria-hidden="true" />
            <span className="history-main">
              <strong>{job.request.start} → {job.request.end}</strong>
              <small>{job.request.ktype} · {job.request.autype} · {job.request.session ?? "ALL"}</small>
            </span>
            <span className="history-time"><strong>{t(`status.${job.status}`)}</strong>{formatDateTime(job.created_at, locale)}</span>
          </button>
          ))}
        </div>
        {totalPages > 1 ? (
          <nav className="archive-pagination" aria-label={t("history.runs")}>
            <button
              type="button"
              disabled={page === 0}
              onClick={() => setPages((current) => ({ ...current, [groupKey]: page - 1 }))}
            >
              ← {t("history.previousPage")}
            </button>
            <span>{t("history.page", { current: page + 1, total: totalPages })}</span>
            <button
              type="button"
              disabled={page === totalPages - 1}
              onClick={() => setPages((current) => ({ ...current, [groupKey]: page + 1 }))}
            >
              {t("history.nextPage")} →
            </button>
          </nav>
        ) : null}
      </div>
    </section>
  );
}

function strategyName(path: string): string {
  return path.split("/").at(-1)?.replace(/\.py$/, "").replaceAll("_", " ") ?? path;
}

function groupJobs(jobs: BacktestJob[]): SymbolGroup[] {
  const symbols = new Map<string, { jobs: BacktestJob[]; strategies: Map<string, BacktestJob[]> }>();
  jobs.forEach((job) => {
    const symbol = symbols.get(job.request.symbol) ?? {
      jobs: [] as BacktestJob[],
      strategies: new Map<string, BacktestJob[]>(),
    };
    symbol.jobs.push(job);
    const strategyJobs = symbol.strategies.get(job.strategy_path) ?? [];
    strategyJobs.push(job);
    symbol.strategies.set(job.strategy_path, strategyJobs);
    symbols.set(job.request.symbol, symbol);
  });
  return [...symbols].map(([symbol, group]) => ({
    symbol,
    jobs: group.jobs,
    strategies: [...group.strategies].map(([path, strategyJobs]) => ({ path, jobs: strategyJobs })),
  }));
}
