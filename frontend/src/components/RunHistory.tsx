import type { BacktestJob } from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import { formatDateTime } from "../lib/format";

interface RunHistoryProps {
  jobs: BacktestJob[];
  activeJobId: string | null;
  onSelect: (jobId: string) => void;
  onRefresh: () => void;
}

export function RunHistory({ jobs, activeJobId, onSelect, onRefresh }: RunHistoryProps) {
  const { locale, t } = useI18n();
  return (
    <section className="run-ledger" aria-labelledby="runHistoryTitle">
      <div className="section-heading">
        <div>
          <span className="section-code">LEDGER</span>
          <h2 id="runHistoryTitle">{t("history.title")}</h2>
        </div>
        <button className="text-button" type="button" onClick={onRefresh}>{t("common.refresh")}</button>
      </div>
      <div className="history-list">
        {jobs.length === 0 ? <p className="quiet-state">{t("history.empty")}</p> : null}
        {jobs.map((job) => (
          <button
            key={job.id}
            className="history-item"
            type="button"
            aria-current={job.id === activeJobId}
            onClick={() => onSelect(job.id)}
          >
            <span className={`history-mark ${job.status}`} aria-hidden="true" />
            <span className="history-main">
              <strong>{job.request.symbol} · {job.request.ktype} · {job.request.session ?? "ALL"}</strong>
              <small>{job.strategy_path.split("/").at(-1)?.replace(/\.py$/, "")}</small>
            </span>
            <span className="history-time">{formatDateTime(job.created_at, locale)}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
