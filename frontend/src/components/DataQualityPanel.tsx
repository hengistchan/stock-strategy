import type { MarketDataQualityReport } from "../api/types";
import { useI18n } from "../i18n/I18nContext";

export function DataQualityPanel({ report }: { report: MarketDataQualityReport }) {
  const { t } = useI18n();
  const warnings = report.duplicates
    + report.missing_intervals
    + report.suspicious_price_jumps.length;
  return (
    <details className="data-quality-panel">
      <summary>
        <span>DATA QUALITY</span>
        <strong>{t("quality.title")}</strong>
        <em data-warning={warnings > 0 || undefined}>
          {warnings > 0 ? t("quality.warningCount", { count: warnings }) : t("quality.clean")}
        </em>
      </summary>
      <dl>
        <div><dt>{t("quality.source")}</dt><dd>{report.source} · {report.source_version}</dd></div>
        <div><dt>{t("quality.adjustment")}</dt><dd>{report.adjustment} · {report.corporate_action_mode}</dd></div>
        <div><dt>{t("quality.calendar")}</dt><dd>{report.calendar} · {report.calendar_precision}</dd></div>
        <div><dt>{t("quality.timezone")}</dt><dd>{report.timezone}</dd></div>
        <div><dt>{t("quality.missing")}</dt><dd>{report.missing_intervals}</dd></div>
        <div><dt>{t("quality.jumps")}</dt><dd>{report.suspicious_price_jumps.length}</dd></div>
      </dl>
      {report.calendar_precision === "approximate" ? <p>{t("quality.approximate")}</p> : null}
    </details>
  );
}
