import { useEffect, useId, useRef } from "react";
import type { OptionContractResponse } from "../../api/types";
import { useI18n } from "../../i18n/I18nContext";
import {
  formatGreek,
  formatMonitorInteger,
  formatMonitorPercent,
  formatMonitorPrice,
  formatMonitorRatio,
  formatOptionIv,
  formatQuoteTimestamp,
} from "./formatters";
import { classifyMonitorError } from "./monitorError";
import { MonitorStatePanel } from "./MonitorStatePanel";

interface OptionContractDialogProps {
  contractCode: string;
  data?: OptionContractResponse;
  loading: boolean;
  error: unknown;
  onClose: () => void;
  onRetry: () => void;
}

export function OptionContractDialog({
  contractCode,
  data,
  loading,
  error,
  onClose,
  onRetry,
}: OptionContractDialogProps) {
  const { locale, t } = useI18n();
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const previouslyFocused =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    if (typeof dialog.showModal === "function") {
      if (!dialog.open) dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }
    closeRef.current?.focus();
    return () => {
      if (typeof dialog.close === "function" && dialog.open) dialog.close();
      else dialog.removeAttribute("open");
      previouslyFocused?.focus();
    };
  }, []);

  const contract = data?.contract as Record<string, unknown> | undefined;
  const analytics = data?.analytics as Record<string, unknown> | undefined;
  const terms = [
    [t("monitor.optionType"), textField(contract, "option_type")],
    [t("monitor.strike"), formatMonitorPrice(numberField(contract, "strike_price"), locale)],
    [t("monitor.expiration"), textField(contract, "expiration")],
    [t("monitor.daysToExpiry"), formatMonitorInteger(numberField(contract, "days_to_expiry"), locale)],
    [t("monitor.lotSize"), formatMonitorInteger(numberField(contract, "lot_size"), locale)],
    [t("monitor.contractSize"), formatMonitorInteger(numberField(contract, "option_contract_size"), locale)],
    [t("monitor.expirationCycle"), textField(contract, "expiration_cycle")],
    [t("monitor.settlement"), textField(contract, "settlement_mode")],
  ];
  const quote = [
    [t("monitor.last"), formatMonitorPrice(numberField(contract, "last_price"), locale)],
    [t("monitor.bid"), formatMonitorPrice(numberField(contract, "bid_price"), locale)],
    [t("monitor.ask"), formatMonitorPrice(numberField(contract, "ask_price"), locale)],
    [t("monitor.mid"), formatMonitorPrice(numberField(contract, "mid_price"), locale)],
    [t("monitor.spread"), formatMonitorPrice(numberField(contract, "bid_ask_spread"), locale)],
    [t("monitor.spreadPct"), formatMonitorPercent(numberField(contract, "bid_ask_spread_pct"), locale)],
    [t("monitor.volume"), formatMonitorInteger(numberField(contract, "volume"), locale)],
    [t("monitor.openInterestDaily"), formatMonitorInteger(numberField(contract, "option_open_interest"), locale)],
    [t("monitor.volumeOiRatio"), formatMonitorRatio(numberField(contract, "volume_open_interest_ratio"), locale)],
    [t("monitor.impliedVolatility"), formatOptionIv(numberField(contract, "option_implied_volatility"), locale)],
    [t("monitor.premium"), formatMonitorPrice(numberField(contract, "option_premium"), locale)],
    [t("monitor.quoteTime"), formatQuoteTimestamp(textField(contract, "source_time"))],
  ];
  const greeks = [
    ["DELTA", formatGreek(numberField(contract, "option_delta"), locale)],
    ["GAMMA", formatGreek(numberField(contract, "option_gamma"), locale)],
    ["VEGA", formatGreek(numberField(contract, "option_vega"), locale)],
    ["THETA", formatGreek(numberField(contract, "option_theta"), locale)],
    ["RHO", formatGreek(numberField(contract, "option_rho"), locale)],
  ];

  return (
    <dialog
      ref={dialogRef}
      className="option-contract-dialog"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <header>
        <div>
          <p className="section-code">CONTRACT / OPEND</p>
          <h2 id={titleId}>{data?.contract.name || contractCode}</h2>
          <p id={descriptionId}>{contractCode}</p>
        </div>
        <button
          ref={closeRef}
          type="button"
          aria-label={t("monitor.closeContract")}
          onClick={onClose}
        >
          ×
        </button>
      </header>

      {loading && !data ? (
        <p className="monitor-inline-empty">{t("monitor.contractLoading")}</p>
      ) : error && !data ? (
        <MonitorStatePanel
          state={classifyMonitorError(error)}
          compact
          detail={error instanceof Error ? error.message : null}
          onRetry={onRetry}
        />
      ) : data ? (
        <div className="option-contract-body">
          <div className="option-contract-status">
            <span className={`monitor-status-dot ${data.freshness}`} aria-hidden="true" />
            <strong>{t(`monitor.freshness.${data.freshness}`)}</strong>
            <span>OPEND · READ ONLY</span>
          </div>

          <section aria-labelledby={`${titleId}-terms`}>
            <h3 id={`${titleId}-terms`}>{t("monitor.contractTerms")}</h3>
            <dl className="option-contract-grid">
              {terms.map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section aria-labelledby={`${titleId}-quote`}>
            <h3 id={`${titleId}-quote`}>{t("monitor.quoteAndInterest")}</h3>
            <dl className="option-contract-grid quote">
              {quote.map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section aria-labelledby={`${titleId}-greeks`}>
            <h3 id={`${titleId}-greeks`}>{t("monitor.greeks")}</h3>
            <dl className="option-greeks-grid">
              {greeks.map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section className="option-analytics-note" aria-labelledby={`${titleId}-history`}>
            <h3 id={`${titleId}-history`}>{t("monitor.analyticsHistory")}</h3>
            <p>
              {t("monitor.analyticsHistoryBody", {
                volatility: arrayLength(analytics?.volatility_history),
                probability: arrayLength(analytics?.exercise_probability_history),
              })}
            </p>
          </section>
        </div>
      ) : null}
    </dialog>
  );
}

function numberField(
  record: Record<string, unknown> | undefined,
  key: string,
): number | null {
  const value = record?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function textField(
  record: Record<string, unknown> | undefined,
  key: string,
): string {
  const value = record?.[key];
  return typeof value === "string" && value.trim() ? value : "—";
}

function arrayLength(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}
