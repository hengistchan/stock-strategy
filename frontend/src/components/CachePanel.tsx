import type { CacheResponse } from "../api/types";
import { formatDateTime } from "../lib/format";

interface CachePanelProps {
  cache?: CacheResponse;
  loading: boolean;
  deletingId: string | null;
  onDelete: (id: string) => void;
  onRefresh: () => void;
}

export function CachePanel({ cache, loading, deletingId, onDelete, onRefresh }: CachePanelProps) {
  return (
    <section className="cache-panel" aria-labelledby="cachePanelTitle">
      <header>
        <div><span className="section-code">MARKET DATA</span><h2 id="cachePanelTitle">OpenD 缓存</h2></div>
        <div><strong>{cache?.entries.length ?? 0}</strong><span>{formatBytes(cache?.total_bytes ?? 0)}</span><button type="button" onClick={onRefresh}>刷新</button></div>
      </header>
      {loading ? <p className="quiet-state">正在读取缓存目录…</p> : null}
      {!loading && cache?.entries.length === 0 ? <p className="quiet-state">首次实验会在这里生成可复用的行情缓存。</p> : null}
      <div className="cache-list">
        {cache?.entries.map((entry) => (
          <article key={entry.id}>
            <div><strong>{entry.symbol}</strong><span>{entry.ktype} · {entry.autype} · {entry.session}</span></div>
            <dl>
              <div><dt>请求区间</dt><dd>{entry.start} → {entry.end}</dd></div>
              <div><dt>实际数据</dt><dd>{entry.rows} bars · {formatBytes(entry.bytes)}</dd></div>
              <div><dt>更新时间</dt><dd>{formatDateTime(entry.updated_at)}</dd></div>
            </dl>
            <button type="button" disabled={deletingId === entry.id} onClick={() => onDelete(entry.id)}>{deletingId === entry.id ? "删除中" : "删除缓存"}</button>
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
