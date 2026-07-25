import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { queryKeys } from "../api/queryKeys";
import type { StrategyDocument, StrategyVersion } from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import { formatDateTime } from "../lib/format";

interface StrategyVersionPanelProps {
  document: StrategyDocument;
}

export function StrategyVersionPanel({ document }: StrategyVersionPanelProps) {
  const { locale, t } = useI18n();
  const queryClient = useQueryClient();
  const versionsQuery = useQuery({
    queryKey: queryKeys.strategyVersions(document.path),
    queryFn: () => api.strategyVersions(document.path),
  });
  const restoreMutation = useMutation({
    mutationFn: (version: StrategyVersion) =>
      api.restoreStrategyVersion(document.path, version.revision, document.revision),
    onSuccess: (restored) => {
      queryClient.setQueryData(queryKeys.strategy(restored.path), restored);
      void queryClient.invalidateQueries({
        queryKey: queryKeys.strategyVersions(restored.path),
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.strategies });
      void queryClient.invalidateQueries({ queryKey: queryKeys.config });
    },
  });
  const versions = versionsQuery.data?.versions ?? [];

  return (
    <section className="strategy-version-panel" aria-label={t("strategy.versionHistory")}>
      <header>
        <div>
          <span className="section-code">LINEAGE</span>
          <h3>{t("strategy.versionHistory")}</h3>
        </div>
        <span>{t("strategy.versionCount", { count: versions.length })}</span>
      </header>
      {versionsQuery.isLoading ? <p>{t("strategy.versionsLoading")}</p> : null}
      {versionsQuery.error ? <p className="negative">{versionsQuery.error.message}</p> : null}
      <div className="strategy-version-list">
        {versions.map((version) => (
          <article key={version.id} data-current={version.current || undefined}>
            <div>
              <strong>{version.current ? t("strategy.currentVersion") : version.reason}</strong>
              <code>{version.revision.slice(0, 10)}</code>
              <time>{formatDateTime(version.created_at, locale)}</time>
            </div>
            <p>{t("strategy.versionUsage", {
              backtests: version.backtest_count,
              experiments: version.experiment_count,
            })}</p>
            {!document.readonly && !version.current ? (
              <button
                type="button"
                disabled={restoreMutation.isPending}
                onClick={() => {
                  if (window.confirm(t("strategy.restoreConfirm"))) {
                    restoreMutation.mutate(version);
                  }
                }}
              >
                {t("strategy.restoreVersion")}
              </button>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
