import type { HealthResponse } from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import { NavLink } from "react-router-dom";
import { workspacePaths } from "../lib/workspaceRoutes";
import { SystemStatusPanel } from "./SystemStatusPanel";

interface HeaderProps {
  health?: HealthResponse;
}

export function Header({ health }: HeaderProps) {
  const { t } = useI18n();
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

      <SystemStatusPanel health={health} />
    </header>
  );
}
