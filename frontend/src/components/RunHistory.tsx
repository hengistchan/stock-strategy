import { useState } from "react";
import type { BacktestJob } from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import { formatDateTime } from "../lib/format";
import { formatSymbolLabel, type SymbolNameMap } from "../lib/symbols";

interface RunHistoryProps {
  jobs: BacktestJob[];
  activeJobId: string | null;
  onSelect: (jobId: string) => void;
  onRefresh: () => void;
  onCreate: () => void;
  symbolNames?: SymbolNameMap;
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

export function RunHistory({ jobs, activeJobId, onSelect, onRefresh, onCreate, symbolNames = {} }: RunHistoryProps) {
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

      <div className="archive-picker-stack">
        <label className="archive-picker-row">
          <span className="archive-picker-index">01 / {t("history.symbols")}</span>
          <span className="archive-picker-control">
            <span className="archive-select-shell">
              <select
                aria-label={t("history.symbols")}
                value={activeSymbol?.symbol}
                onChange={(event) => {
                  const selected = archive.find((group) => group.symbol === event.target.value);
                  if (selected?.jobs[0]) onSelect(selected.jobs[0].id);
                }}
              >
                {archive.map((group) => (
                  <option key={group.symbol} value={group.symbol}>{formatSymbolLabel(group.symbol, symbolNames)}</option>
                ))}
              </select>
              <span className="archive-select-arrow" aria-hidden="true">⌄</span>
            </span>
            <small>
              {t("history.runCount", { count: activeSymbol?.jobs.length ?? 0 })}
              {" · "}
              {t("history.strategyCount", { count: activeSymbol?.strategies.length ?? 0 })}
            </small>
          </span>
        </label>

        <label className="archive-picker-row">
          <span className="archive-picker-index">02 / {t("history.strategies")}</span>
          <span className="archive-picker-control">
            <span className="archive-select-shell">
              <select
                aria-label={t("history.strategies")}
                value={activeStrategy?.path}
                onChange={(event) => {
                  const selected = activeSymbol?.strategies.find(
                    (group) => group.path === event.target.value,
                  );
                  if (selected?.jobs[0]) onSelect(selected.jobs[0].id);
                }}
              >
                {activeSymbol?.strategies.map((group) => (
                  <option key={group.path} value={group.path}>
                    {strategyName(group.path)} · {t("history.runCount", { count: group.jobs.length })}
                  </option>
                ))}
              </select>
              <span className="archive-select-arrow" aria-hidden="true">⌄</span>
            </span>
            <small title={activeStrategy?.path}>{activeStrategy?.path}</small>
          </span>
        </label>
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
