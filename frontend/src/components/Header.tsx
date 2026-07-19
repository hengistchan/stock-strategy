import type { HealthResponse } from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import { NavLink } from "react-router-dom";
import { workspacePaths } from "../lib/workspaceRoutes";

interface HeaderProps {
  health?: HealthResponse;
}

export function Header({ health }: HeaderProps) {
  const { locale, setLocale, t } = useI18n();
  const connected = health?.opend.connected === true;
  return (
    <header className="app-header">
      <div className="brand-lockup">
        <div className="brand-index" aria-hidden="true">SL/04</div>
        <div>
          <p className="eyebrow">{t("header.eyebrow")}</p>
          <h1>Strategy Lab</h1>
        </div>
      </div>

      <nav className="workspace-tabs" aria-label={t("header.workspace")}>
        <NavLink to={workspacePaths.backtest}>
          {t("header.backtest")}
          <small>{t("header.backtestHint")}</small>
        </NavLink>
        <NavLink to={workspacePaths.iterate}>
          {t("header.iterate")}
          <small>{t("header.iterateHint")}</small>
        </NavLink>
        <NavLink to={workspacePaths.strategies}>
          {t("header.strategies")}
          <small>{t("header.strategiesHint")}</small>
        </NavLink>
      </nav>

      <div className="system-status-cell" data-state={connected ? "connected" : "offline"}>
        <span className="status-dot" aria-hidden="true" />
        <span className="connection-copy">
          <strong>{connected ? t("header.connected") : t("header.offline")}</strong>
          <small>{health ? `${health.opend.host}:${health.opend.port}` : t("header.checking")}</small>
        </span>
        <button
          className="language-switch"
          type="button"
          aria-label={t("header.switchLanguage")}
          onClick={() => setLocale(locale === "zh-CN" ? "en-US" : "zh-CN")}
        >
          <span aria-hidden="true">文/A</span>
          <strong>{t("header.languageName")}</strong>
        </button>
      </div>
    </header>
  );
}
