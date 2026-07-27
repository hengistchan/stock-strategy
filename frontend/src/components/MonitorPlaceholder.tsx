import { useI18n } from "../i18n/I18nContext";

export function MonitorPlaceholder() {
  const { t } = useI18n();

  return (
    <main className="monitor-placeholder">
      <aside className="monitor-placeholder-intro" aria-labelledby="monitorPlaceholderTitle">
        <span className="section-code">LIVE WATCH</span>
        <h2 id="monitorPlaceholderTitle">{t("monitor.title")}</h2>
        <p>{t("monitor.intro")}</p>
      </aside>
      <section className="monitor-placeholder-desk" aria-labelledby="monitorPlaceholderEmptyTitle">
        <div className="monitor-placeholder-mark" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <div>
          <p className="eyebrow">{t("monitor.placeholderLabel")}</p>
          <h2 id="monitorPlaceholderEmptyTitle">{t("monitor.placeholderTitle")}</h2>
          <p>{t("monitor.placeholderBody")}</p>
        </div>
      </section>
    </main>
  );
}
