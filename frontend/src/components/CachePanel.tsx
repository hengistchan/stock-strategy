import type { CacheResponse } from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import { formatDateTime } from "../lib/format";

interface CachePanelProps {
  cache?: CacheResponse;
  loading: boolean;
  deletingId: string | null;
  onDelete: (id: string) => void;
  onRefresh: () => void;
}

export function CachePanel({ cache, loading, deletingId, onDelete, onRefresh }: CachePanelProps) {
  const { locale, t } = useI18n();
  return (
    <section className="cache-panel" aria-labelledby="cachePanelTitle">
      <header>
        <div><span className="section-code">MARKET DATA</span><h2 id="cachePanelTitle">{t("cache.title")}</h2></div>
        <div><strong>{cache?.entries.length ?? 0}</strong><span>{formatBytes(cache?.total_bytes ?? 0)}</span><button type="button" onClick={onRefresh}>{t("common.refresh")}</button></div>
      </header>
      {loading ? <p className="quiet-state">{t("cache.loading")}</p> : null}
      {!loading && cache?.entries.length === 0 ? <p className="quiet-state">{t("cache.empty")}</p> : null}
      <div className="cache-list">
        {cache?.entries.map((entry) => (
          <article key={entry.id}>
            <div><strong>{entry.symbol}</strong><span>{entry.ktype} · {entry.autype} · {entry.session}</span></div>
            <dl>
              <div><dt>{t("cache.requestRange")}</dt><dd>{entry.start} → {entry.end}</dd></div>
              <div><dt>{t("cache.actualData")}</dt><dd>{t("result.bars", { count: entry.rows })} · {formatBytes(entry.bytes)}</dd></div>
              <div><dt>{t("cache.updatedAt")}</dt><dd>{formatDateTime(entry.updated_at, locale)}</dd></div>
            </dl>
            <button type="button" disabled={deletingId === entry.id} onClick={() => onDelete(entry.id)}>{deletingId === entry.id ? t("cache.deleting") : t("cache.delete")}</button>
          </article>
        ))}
      </div>
    </section>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
