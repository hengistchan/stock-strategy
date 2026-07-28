import { useI18n } from "../../i18n/I18nContext";
import type { TranslationKey } from "../../i18n/translations";

export type MonitorState =
  | "checking"
  | "offline"
  | "reconnecting"
  | "stale"
  | "market_closed"
  | "permission"
  | "quota"
  | "unavailable"
  | "empty"
  | "error";

interface MonitorStatePanelProps {
  state: MonitorState;
  compact?: boolean;
  detail?: string | null;
  onRetry?: () => void;
}

const COPY: Record<
  MonitorState,
  { code: string; title: TranslationKey; body: TranslationKey }
> = {
  checking: {
    code: "SYNC",
    title: "monitor.stateCheckingTitle",
    body: "monitor.stateCheckingBody",
  },
  offline: {
    code: "OFFLINE",
    title: "monitor.stateOfflineTitle",
    body: "monitor.stateOfflineBody",
  },
  reconnecting: {
    code: "RECONNECT",
    title: "monitor.stateReconnectingTitle",
    body: "monitor.stateReconnectingBody",
  },
  stale: {
    code: "STALE",
    title: "monitor.stateStaleTitle",
    body: "monitor.stateStaleBody",
  },
  market_closed: {
    code: "CLOSED",
    title: "monitor.stateClosedTitle",
    body: "monitor.stateClosedBody",
  },
  permission: {
    code: "ACCESS",
    title: "monitor.statePermissionTitle",
    body: "monitor.statePermissionBody",
  },
  quota: {
    code: "QUOTA",
    title: "monitor.stateQuotaTitle",
    body: "monitor.stateQuotaBody",
  },
  unavailable: {
    code: "NO DATA",
    title: "monitor.stateUnavailableTitle",
    body: "monitor.stateUnavailableBody",
  },
  empty: {
    code: "WATCH",
    title: "monitor.stateEmptyTitle",
    body: "monitor.stateEmptyBody",
  },
  error: {
    code: "ERROR",
    title: "monitor.stateErrorTitle",
    body: "monitor.stateErrorBody",
  },
};

export function MonitorStatePanel({
  state,
  compact = false,
  detail,
  onRetry,
}: MonitorStatePanelProps) {
  const { t } = useI18n();
  const copy = COPY[state];
  return (
    <section
      className={`monitor-state ${compact ? "compact" : ""}`}
      data-state={state}
      role={state === "error" || state === "offline" ? "alert" : "status"}
    >
      <div className="monitor-state-mark" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <div>
        <p className="section-code">{copy.code}</p>
        <h2>{t(copy.title)}</h2>
        <p>{detail || t(copy.body)}</p>
        {onRetry ? (
          <button type="button" onClick={onRetry}>
            {t("monitor.retry")}
          </button>
        ) : null}
      </div>
    </section>
  );
}
