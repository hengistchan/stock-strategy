import type { HealthResponse } from "../api/types";
import { useI18n } from "../i18n/I18nContext";

export type WorkspaceMode = "backtest" | "iterate" | "strategies";

interface HeaderProps {
  health?: HealthResponse;
  mode: WorkspaceMode;
  onModeChange: (mode: WorkspaceMode) => void;
}

export function Header({ health, mode, onModeChange }: HeaderProps) {
  const { locale, setLocale, t } = useI18n();
  const connected = health?.opend.connected === true;
  return (
    <header className="app-header">
      <div className="brand-lockup">
        <div className="brand-index" aria-hidden="true">SL/03</div>
        <div>
          <p className="eyebrow">{t("header.eyebrow")}</p>
          <h1>Strategy Lab</h1>
        </div>
      </div>

      <nav className="workspace-tabs" aria-label={t("header.workspace")}>
        <button
          type="button"
          aria-current={mode === "backtest" ? "page" : undefined}
          onClick={() => onModeChange("backtest")}
        >
          {t("header.backtest")}
          <small>{t("header.backtestHint")}</small>
        </button>
        <button
          type="button"
          aria-current={mode === "iterate" ? "page" : undefined}
          onClick={() => onModeChange("iterate")}
        >
          {t("header.iterate")}
          <small>{t("header.iterateHint")}</small>
        </button>
        <button
          type="button"
          aria-current={mode === "strategies" ? "page" : undefined}
          onClick={() => onModeChange("strategies")}
        >
          {t("header.strategies")}
          <small>{t("header.strategiesHint")}</small>
        </button>
      </nav>

      <div className="header-actions">
        <button
          className="language-switch"
          type="button"
          aria-label={t("header.switchLanguage")}
          onClick={() => setLocale(locale === "zh-CN" ? "en-US" : "zh-CN")}
        >
          <span aria-hidden="true">文/A</span>
          <strong>{t("header.languageName")}</strong>
        </button>
        <div className="connection-badge" data-state={connected ? "connected" : "offline"}>
          <span className="status-dot" aria-hidden="true" />
          <span>{connected ? t("header.connected") : t("header.offline")}</span>
          <small>{health ? `${health.opend.host}:${health.opend.port}` : t("header.checking")}</small>
        </div>
      </div>
    </header>
  );
}
