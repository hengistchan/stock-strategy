import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { NavLink, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import type {
  MonitorAlert,
  MonitoringDiagnosticsResponse,
  MonitorRule,
  MonitorRuleRequest,
  MonitoredInstrument,
  SymbolMatch,
  WatchlistResponse,
} from "../../api/types";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { useI18n } from "../../i18n/I18nContext";
import { workspacePaths } from "../../lib/workspaceRoutes";
import { AlertWorkspace } from "./AlertWorkspace";
import { formatQuoteTimestamp } from "./formatters";
import { MonitorStatePanel } from "./MonitorStatePanel";
import { OptionChainPanel } from "./OptionChainPanel";
import { OptionContractDialog } from "./OptionContractDialog";
import { UnderlyingOverview } from "./UnderlyingOverview";
import { WatchlistRail } from "./WatchlistRail";

interface MonitorWorkspaceProps {
  opendConnected: boolean | null;
  onNotice: (message: string) => void;
}

type MonitorMode = "overview" | "options" | "alerts";

export function MonitorWorkspace({
  opendConnected,
  onNotice,
}: MonitorWorkspaceProps) {
  const { t } = useI18n();
  const params = useParams<{ symbol?: string; contractCode?: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const symbol = params.symbol?.trim().toUpperCase() ?? null;
  const contractCode = params.contractCode?.trim().toUpperCase() ?? null;
  const mode: MonitorMode = location.pathname.endsWith("/alerts")
    ? "alerts"
    : location.pathname.includes("/options")
      ? "options"
      : "overview";
  const [unacknowledgedOnly, setUnacknowledgedOnly] = useState(false);

  const statusQuery = useQuery({
    queryKey: queryKeys.monitoringStatus,
    queryFn: api.monitoringStatus,
    refetchInterval: 5_000,
  });
  const diagnosticsQuery = useQuery({
    queryKey: queryKeys.monitoringDiagnostics,
    queryFn: api.monitoringDiagnostics,
    enabled:
      statusQuery.data?.phase === "degraded"
      || statusQuery.data?.phase === "reconnecting",
    refetchOnWindowFocus: false,
  });
  const watchlistQuery = useQuery({
    queryKey: queryKeys.watchlist,
    queryFn: api.watchlist,
    refetchInterval: 5_000,
  });
  const snapshotQuery = useQuery({
    queryKey: queryKeys.monitorSnapshot(symbol),
    queryFn: () => api.underlyingSnapshot(symbol ?? ""),
    enabled: Boolean(symbol) && opendConnected !== false,
    refetchInterval: 3_000,
  });
  const barsQuery = useQuery({
    queryKey: queryKeys.monitorBars(symbol, 120, "K_5M"),
    queryFn: () => api.underlyingBars(symbol ?? "", 120, "K_5M"),
    enabled: Boolean(symbol) && opendConnected !== false && mode === "overview",
    refetchInterval: 15_000,
  });
  const expirationsQuery = useQuery({
    queryKey: queryKeys.optionExpirations(symbol),
    queryFn: () => api.optionExpirations(symbol ?? ""),
    enabled: Boolean(symbol) && opendConnected !== false && mode === "options",
    staleTime: 60_000,
  });
  const requestedExpiration = searchParams.get("expiration");
  const expiration =
    expirationsQuery.data?.expirations.some(
      (item) => item.expiration === requestedExpiration,
    )
      ? requestedExpiration
      : expirationsQuery.data?.expirations[0]?.expiration ?? null;
  const chainQuery = useQuery({
    queryKey: queryKeys.optionChain(symbol, expiration),
    queryFn: () => api.optionChain(symbol ?? "", expiration ?? ""),
    enabled:
      Boolean(symbol)
      && Boolean(expiration)
      && opendConnected !== false
      && mode === "options",
    refetchInterval: 5_000,
  });
  const contractQuery = useQuery({
    queryKey: queryKeys.optionContract(contractCode),
    queryFn: () => api.optionContract(contractCode ?? ""),
    enabled: Boolean(contractCode) && opendConnected !== false,
    refetchInterval: 5_000,
  });
  const rulesQuery = useQuery({
    queryKey: queryKeys.monitorRules(symbol ?? undefined),
    queryFn: () => api.monitorRules(symbol ?? undefined),
    enabled: Boolean(symbol) && mode === "alerts",
    refetchInterval: 10_000,
  });
  const alertsQuery = useQuery({
    queryKey: queryKeys.monitorAlerts(symbol ?? undefined, unacknowledgedOnly),
    queryFn: () =>
      api.monitorAlerts(symbol ?? undefined, unacknowledgedOnly, undefined, 100),
    enabled: Boolean(symbol) && mode === "alerts",
    refetchInterval: 5_000,
  });

  const addMutation = useMutation({
    mutationFn: async (candidate: SymbolMatch) => {
      const watchlist =
        queryClient.getQueryData<WatchlistResponse>(queryKeys.watchlist)
        ?? watchlistQuery.data;
      const existing = watchlist?.instruments.find(
        (instrument) =>
          instrument.code.toUpperCase() === candidate.code.toUpperCase(),
      );
      if (existing?.enabled) return { instrument: existing, duplicate: true };
      if (existing) {
        const instrument = await api.updateWatchlistItem(existing.code, {
          enabled: true,
        });
        return { instrument, duplicate: true };
      }
      const instrument = await api.addWatchlistItem({
        code: candidate.code,
        name: candidate.name || candidate.code,
        instrument_type: "stock",
        enabled: true,
      });
      return { instrument, duplicate: false };
    },
    onSuccess: ({ instrument, duplicate }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.watchlist });
      onNotice(
        t(
          duplicate ? "monitor.watchlistAlreadyAdded" : "monitor.watchlistAdded",
          { code: instrument.code },
        ),
      );
      navigate(workspacePaths.monitorSymbol(instrument.code));
    },
    onError: (error) => onNotice(errorMessage(error, t("monitor.actionFailed"))),
  });

  const watchlistUpdateMutation = useMutation({
    mutationFn: ({
      instrument,
      enabled,
    }: {
      instrument: MonitoredInstrument;
      enabled: boolean;
    }) => api.updateWatchlistItem(instrument.code, { enabled }),
    onSuccess: (instrument) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.watchlist });
      onNotice(
        t(instrument.enabled ? "monitor.symbolEnabled" : "monitor.symbolDisabled", {
          code: instrument.code,
        }),
      );
    },
    onError: (error) => onNotice(errorMessage(error, t("monitor.actionFailed"))),
  });

  const watchlistDeleteMutation = useMutation({
    mutationFn: (instrument: MonitoredInstrument) =>
      api.deleteWatchlistItem(instrument.code).then(() => instrument),
    onSuccess: (instrument) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.watchlist });
      if (symbol === instrument.code) navigate(workspacePaths.monitors);
      onNotice(t("monitor.watchlistRemoved", { code: instrument.code }));
    },
    onError: (error) => onNotice(errorMessage(error, t("monitor.actionFailed"))),
  });

  const ruleCreateMutation = useMutation({
    mutationFn: api.createMonitorRule,
    onSuccess: (rule) => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.monitorRules(symbol ?? undefined),
      });
      onNotice(t("monitor.ruleCreated", { name: rule.name }));
    },
    onError: (error) => onNotice(errorMessage(error, t("monitor.actionFailed"))),
  });
  const ruleUpdateMutation = useMutation({
    mutationFn: (rule: MonitorRule) =>
      api.updateMonitorRule(rule.id, { enabled: !rule.enabled }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.monitorRules(symbol ?? undefined),
      });
    },
    onError: (error) => onNotice(errorMessage(error, t("monitor.actionFailed"))),
  });
  const ruleDeleteMutation = useMutation({
    mutationFn: (rule: MonitorRule) =>
      api.deleteMonitorRule(rule.id).then(() => rule),
    onSuccess: (rule) => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.monitorRules(symbol ?? undefined),
      });
      onNotice(t("monitor.ruleDeleted", { name: rule.name }));
    },
    onError: (error) => onNotice(errorMessage(error, t("monitor.actionFailed"))),
  });
  const alertAcknowledgeMutation = useMutation({
    mutationFn: (alert: MonitorAlert) => api.acknowledgeMonitorAlert(alert.id),
    onSuccess: (alert) => {
      void queryClient.invalidateQueries({
        queryKey: ["monitoring", "alerts"],
      });
      onNotice(t("monitor.alertAcknowledged", { name: alert.rule_name }));
    },
    onError: (error) => onNotice(errorMessage(error, t("monitor.actionFailed"))),
  });

  const selectedInstrument = watchlistQuery.data?.instruments.find(
    (instrument) => instrument.code === symbol,
  );
  const status = statusQuery.data;
  const diagnosticsDetail = diagnosticsQuery.data?.checks
    ?.filter((check) => check.status !== "pass")
    .map((check) => check.hint || check.detail)
    .filter(Boolean)
    .join(" · ");
  const workspaceUnavailable =
    opendConnected === false
      ? "offline"
      : opendConnected === null
        ? "checking"
        : null;
  const busyCode =
    watchlistUpdateMutation.isPending
      ? watchlistUpdateMutation.variables?.instrument.code ?? null
      : watchlistDeleteMutation.isPending
        ? watchlistDeleteMutation.variables?.code ?? null
        : null;

  function retryMarketData() {
    const requests: Promise<unknown>[] = [
      queryClient.refetchQueries({ queryKey: queryKeys.health }),
      statusQuery.refetch(),
      diagnosticsQuery.refetch(),
      watchlistQuery.refetch(),
    ];
    if (symbol && opendConnected !== false) {
      requests.push(snapshotQuery.refetch());
      if (mode === "overview") requests.push(barsQuery.refetch());
      if (mode === "options") {
        requests.push(expirationsQuery.refetch());
        if (expiration) requests.push(chainQuery.refetch());
        if (contractCode) requests.push(contractQuery.refetch());
      }
    }
    if (symbol && mode === "alerts") {
      requests.push(rulesQuery.refetch(), alertsQuery.refetch());
    }
    void Promise.all(requests);
  }

  function setExpiration(next: string) {
    const paramsCopy = new URLSearchParams(searchParams);
    paramsCopy.set("expiration", next);
    setSearchParams(paramsCopy, { replace: true });
  }

  return (
    <main className="monitor-workspace">
      <WatchlistRail
        activeSymbol={symbol}
        instruments={watchlistQuery.data?.instruments ?? []}
        opendConnected={opendConnected}
        busyCode={busyCode}
        adding={addMutation.isPending}
        onAdd={(candidate) => addMutation.mutate(candidate)}
        onToggle={(instrument) =>
          watchlistUpdateMutation.mutate({
            instrument,
            enabled: !instrument.enabled,
          })}
        onDelete={(instrument) => {
          if (window.confirm(t("monitor.removeConfirm", { code: instrument.code }))) {
            watchlistDeleteMutation.mutate(instrument);
          }
        }}
      />

      <section className="monitor-desk">
        <MonitorStatusStrip
          phase={status?.phase ?? (opendConnected === false ? "stopped" : "starting")}
          rulesPaused={status?.rules_paused ?? true}
          marketState={
            (symbol && status?.market_states?.[symbol.split(".", 1)[0].toLowerCase()])
            || snapshotQuery.data?.market_state
            || "UNKNOWN"
          }
          freshness={snapshotQuery.data?.freshness ?? selectedInstrument?.freshness ?? "unavailable"}
          lastSuccessAt={status?.last_success_at}
          lastError={status?.last_error || diagnosticsDetail}
          subscriptionBudget={status?.generic_subscription_budget}
        />
        <MonitorDiagnosticsPanel
          data={diagnosticsQuery.data}
          loading={diagnosticsQuery.isFetching}
          error={diagnosticsQuery.error}
          onRun={() => void diagnosticsQuery.refetch()}
        />

        {symbol ? (
          <header className="monitor-symbol-header">
            <div>
              <p className="section-code">
                {selectedInstrument?.market || symbol.split(".", 1)[0]} / LIVE WATCH
              </p>
              <h1>
                {selectedInstrument?.name || snapshotQuery.data?.snapshot.name || symbol}
                <small>{symbol}</small>
              </h1>
            </div>
            <nav aria-label={t("monitor.symbolNavigation")}>
              <NavLink end to={workspacePaths.monitorSymbol(symbol)}>
                {t("monitor.overview")}
              </NavLink>
              <NavLink to={workspacePaths.monitorOptions(symbol)}>
                {t("monitor.options")}
              </NavLink>
              <NavLink to={workspacePaths.monitorAlerts(symbol)}>
                {t("monitor.alerts")}
              </NavLink>
            </nav>
          </header>
        ) : null}

        {workspaceUnavailable ? (
          <MonitorStatePanel
            state={workspaceUnavailable}
            detail={diagnosticsDetail}
            onRetry={retryMarketData}
          />
        ) : status?.phase === "reconnecting" && !snapshotQuery.data ? (
          <MonitorStatePanel
            state="reconnecting"
            detail={status.last_error}
            onRetry={retryMarketData}
          />
        ) : !symbol ? (
          <MonitorStatePanel
            state={watchlistQuery.isLoading ? "checking" : "empty"}
            detail={
              watchlistQuery.error instanceof Error
                ? watchlistQuery.error.message
                : undefined
            }
            onRetry={watchlistQuery.error ? () => void watchlistQuery.refetch() : undefined}
          />
        ) : mode === "options" ? (
          <OptionChainPanel
            symbol={symbol}
            expirations={expirationsQuery.data?.expirations ?? []}
            expiration={expiration}
            data={chainQuery.data}
            expirationsLoading={expirationsQuery.isLoading}
            chainLoading={chainQuery.isLoading}
            error={expirationsQuery.error || chainQuery.error}
            onExpirationChange={setExpiration}
            onOpenContract={(code) =>
              navigate({
                pathname: workspacePaths.monitorContract(symbol, code),
                search: searchParams.toString(),
              })}
            onRetry={retryMarketData}
          />
        ) : mode === "alerts" ? (
          <AlertWorkspace
            key={symbol}
            symbol={symbol}
            rules={rulesQuery.data?.rules ?? []}
            alerts={alertsQuery.data?.alerts ?? []}
            loading={rulesQuery.isLoading || alertsQuery.isLoading}
            unacknowledgedOnly={unacknowledgedOnly}
            busyRuleId={
              ruleUpdateMutation.isPending
                ? ruleUpdateMutation.variables?.id ?? null
                : ruleDeleteMutation.isPending
                  ? ruleDeleteMutation.variables?.id ?? null
                  : null
            }
            busyAlertId={
              alertAcknowledgeMutation.isPending
                ? alertAcknowledgeMutation.variables?.id ?? null
                : null
            }
            creatingRule={ruleCreateMutation.isPending}
            onUnacknowledgedOnlyChange={setUnacknowledgedOnly}
            onCreateRule={(payload: MonitorRuleRequest) =>
              ruleCreateMutation.mutate(payload)}
            onToggleRule={(rule) => ruleUpdateMutation.mutate(rule)}
            onDeleteRule={(rule) => {
              if (window.confirm(t("monitor.deleteRuleConfirm", { name: rule.name }))) {
                ruleDeleteMutation.mutate(rule);
              }
            }}
            onAcknowledge={(alert) => alertAcknowledgeMutation.mutate(alert)}
          />
        ) : (
          <UnderlyingOverview
            symbol={symbol}
            snapshot={snapshotQuery.data}
            bars={barsQuery.data}
            snapshotLoading={snapshotQuery.isLoading}
            barsLoading={barsQuery.isLoading}
            snapshotError={snapshotQuery.error}
            barsError={barsQuery.error}
            onRetry={retryMarketData}
          />
        )}
      </section>

      {symbol && contractCode ? (
        <OptionContractDialog
          contractCode={contractCode}
          data={contractQuery.data}
          loading={contractQuery.isLoading}
          error={contractQuery.error}
          onClose={() =>
            navigate({
              pathname: workspacePaths.monitorOptions(symbol),
              search: searchParams.toString(),
            })}
          onRetry={() => void contractQuery.refetch()}
        />
      ) : null}
    </main>
  );
}

interface MonitorDiagnosticsPanelProps {
  data?: MonitoringDiagnosticsResponse;
  loading: boolean;
  error: unknown;
  onRun: () => void;
}

function MonitorDiagnosticsPanel({
  data,
  loading,
  error,
  onRun,
}: MonitorDiagnosticsPanelProps) {
  const { t } = useI18n();
  const failedCount =
    data?.checks.filter((check) => check.status !== "pass").length ?? 0;
  return (
    <details
      className="monitor-diagnostics-panel"
      onToggle={(event) => {
        if (
          event.currentTarget.open
          && !data
          && !loading
          && !error
        ) {
          onRun();
        }
      }}
    >
      <summary>
        <span>MON-13</span>
        <strong>{t("monitor.diagnosticsTitle")}</strong>
        <em data-ready={data?.ready === true}>
          {loading
            ? t("monitor.diagnosticsLoading")
            : data
              ? failedCount === 0
                ? t("monitor.diagnosticsReady")
                : t("monitor.diagnosticsIssues", { count: failedCount })
              : error
                ? t("monitor.diagnosticsError")
                : t("monitor.diagnosticsNotRun")}
        </em>
      </summary>
      <div>
        {loading && !data ? (
          <p>{t("monitor.diagnosticsLoading")}</p>
        ) : error && !data ? (
          <>
            <p className="negative">
              {error instanceof Error ? error.message : t("monitor.diagnosticsError")}
            </p>
            <button type="button" onClick={onRun}>
              {t("monitor.retry")}
            </button>
          </>
        ) : data ? (
          data.checks.length === 0 ? (
            <p>{t("monitor.diagnosticsReady")}</p>
          ) : (
            <ul>
              {data.checks.map((check) => (
                <li key={check.id} data-status={check.status}>
                  <span>{check.status.toUpperCase()}</span>
                  <div>
                    <strong>{check.id}</strong>
                    <p>{check.detail}</p>
                    {check.hint ? (
                      <small>
                        {t("monitor.diagnosticsHint")}: {check.hint}
                      </small>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )
        ) : (
          <button type="button" onClick={onRun}>
            {t("monitor.diagnosticsRun")}
          </button>
        )}
      </div>
    </details>
  );
}

interface MonitorStatusStripProps {
  phase: "stopped" | "starting" | "ready" | "degraded" | "reconnecting";
  rulesPaused: boolean;
  marketState: string;
  freshness: "live" | "stale" | "market_closed" | "unavailable";
  lastSuccessAt?: string | null;
  lastError?: string | null;
  subscriptionBudget?: Record<string, unknown> | null;
}

function MonitorStatusStrip({
  phase,
  rulesPaused,
  marketState,
  freshness,
  lastSuccessAt,
  lastError,
  subscriptionBudget,
}: MonitorStatusStripProps) {
  const { t } = useI18n();
  const remaining = numberField(subscriptionBudget, "generic_remaining");
  return (
    <section
      className="monitor-status-strip"
      data-phase={phase}
      aria-label={t("monitor.runtimeStatus")}
    >
      <span>
        <i className={`monitor-status-dot ${phase}`} aria-hidden="true" />
        <small>{t("monitor.runtime")}</small>
        <strong>{phaseLabel(phase, t)}</strong>
      </span>
      <span>
        <small>{t("monitor.marketState")}</small>
        <strong>{marketState || "UNKNOWN"}</strong>
      </span>
      <span>
        <small>{t("monitor.freshness")}</small>
        <strong>{t(`monitor.freshness.${freshness}`)}</strong>
      </span>
      <span>
        <small>{t("monitor.rulesState")}</small>
        <strong>{rulesPaused ? t("monitor.paused") : t("monitor.evaluating")}</strong>
      </span>
      <span>
        <small>{t("monitor.subscriptionRemaining")}</small>
        <strong>{remaining ?? "—"}</strong>
      </span>
      <span className="monitor-status-message">
        <small>{lastError ? t("monitor.lastError") : t("monitor.lastSuccess")}</small>
        <strong>
          {lastError || formatQuoteTimestamp(lastSuccessAt) || "—"}
        </strong>
      </span>
    </section>
  );
}

function phaseLabel(
  phase: MonitorStatusStripProps["phase"],
  t: ReturnType<typeof useI18n>["t"],
): string {
  const labels = {
    stopped: t("monitor.phaseStopped"),
    starting: t("monitor.phaseStarting"),
    ready: t("monitor.phaseReady"),
    degraded: t("monitor.phaseDegraded"),
    reconnecting: t("monitor.phaseReconnecting"),
  };
  return labels[phase];
}

function numberField(
  record: Record<string, unknown> | null | undefined,
  key: string,
): number | null {
  const value = record?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}
