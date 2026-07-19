import { useState } from "react";
import { api } from "../api/client";
import type { DiagnosticCheck, DiagnosticsResponse, HealthResponse } from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import type { TranslationKey } from "../i18n/translations";

interface SystemStatusPanelProps {
  health?: HealthResponse;
}

const checkLabels: Record<DiagnosticCheck["id"], TranslationKey> = {
  python: "diagnostics.python",
  futu_api: "diagnostics.futuApi",
  workspace: "diagnostics.workspace",
  opend: "diagnostics.opend",
  quote_directory: "diagnostics.quoteDirectory",
};

const checkActions: Record<DiagnosticCheck["id"], TranslationKey> = {
  python: "diagnostics.actionPython",
  futu_api: "diagnostics.actionFutuApi",
  workspace: "diagnostics.actionWorkspace",
  opend: "diagnostics.actionOpend",
  quote_directory: "diagnostics.actionQuoteDirectory",
};

export function SystemStatusPanel({ health }: SystemStatusPanelProps) {
  const { locale, setLocale, t } = useI18n();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<DiagnosticsResponse>();
  const [error, setError] = useState<string>();
  const connected = health?.opend.connected === true;
  const state = health ? (connected ? "connected" : "offline") : "checking";

  async function loadDiagnostics() {
    setLoading(true);
    setError(undefined);
    try {
      setReport(await api.diagnostics());
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : String(requestError));
    } finally {
      setLoading(false);
    }
  }

  function togglePanel() {
    const nextOpen = !open;
    setOpen(nextOpen);
    if (nextOpen && !report && !loading) {
      void loadDiagnostics();
    }
  }

  return (
    <div className="system-status-cell" data-state={state}>
      <button
        className="connection-status-trigger"
        type="button"
        aria-expanded={open}
        aria-controls="system-diagnostics-panel"
        onClick={togglePanel}
      >
        <span className="status-dot" aria-hidden="true" />
        <span className="connection-copy">
          <strong>{connected ? t("header.connected") : health ? t("header.offline") : t("header.checking")}</strong>
          <small>{health ? `${health.opend.host}:${health.opend.port}` : t("header.checking")}</small>
        </span>
        <span className="status-disclosure" aria-hidden="true">{open ? "−" : "+"}</span>
      </button>
      <button
        className="language-switch"
        type="button"
        aria-label={t("header.switchLanguage")}
        onClick={() => setLocale(locale === "zh-CN" ? "en-US" : "zh-CN")}
      >
        <span aria-hidden="true">文/A</span>
        <strong>{t("header.languageName")}</strong>
      </button>

      {open ? (
        <section
          id="system-diagnostics-panel"
          className="diagnostics-panel"
          aria-label={t("diagnostics.title")}
        >
          <div className="diagnostics-heading">
            <div>
              <small>{t("diagnostics.eyebrow")}</small>
              <strong>{report ? (report.ready ? t("diagnostics.ready") : t("diagnostics.actionRequired")) : t("diagnostics.title")}</strong>
            </div>
            <button type="button" onClick={() => void loadDiagnostics()} disabled={loading}>
              {loading ? t("diagnostics.loading") : t("common.refresh")}
            </button>
          </div>
          {error ? <p className="diagnostics-error">{error}</p> : null}
          {report ? (
            <ul className="diagnostics-list">
              {report.checks.map((check) => (
                <li key={check.id} data-status={check.status}>
                  <span className="diagnostics-mark" aria-hidden="true" />
                  <div>
                    <strong>{t(checkLabels[check.id])}</strong>
                    <p>{check.detail}</p>
                    {check.status !== "pass" ? <small>{t(checkActions[check.id])}</small> : null}
                  </div>
                  <span className="diagnostics-state">{t(
                    check.status === "pass"
                      ? "diagnostics.pass"
                      : check.status === "fail"
                        ? "diagnostics.fail"
                        : "diagnostics.statusBlocked",
                  )}</span>
                </li>
              ))}
            </ul>
          ) : loading ? <p className="diagnostics-loading">{t("diagnostics.loading")}</p> : null}
        </section>
      ) : null}
    </div>
  );
}
