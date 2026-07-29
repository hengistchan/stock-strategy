import { useId, useState, type FormEvent } from "react";
import type {
  InstrumentType,
  MonitorAlert,
  MonitorRule,
  MonitorRuleRequest,
  RuleMetric,
  RuleOperator,
  RuleSeverity,
} from "../../api/types";
import { useI18n } from "../../i18n/I18nContext";
import {
  formatGreek,
  formatQuoteTimestamp,
} from "./formatters";
import { MonitorStatePanel } from "./MonitorStatePanel";

interface AlertWorkspaceProps {
  symbol: string;
  rules: readonly MonitorRule[];
  alerts: readonly MonitorAlert[];
  loading: boolean;
  unacknowledgedOnly: boolean;
  busyRuleId: string | null;
  busyAlertId: string | null;
  creatingRule: boolean;
  onUnacknowledgedOnlyChange: (value: boolean) => void;
  onCreateRule: (payload: MonitorRuleRequest) => void;
  onToggleRule: (rule: MonitorRule) => void;
  onDeleteRule: (rule: MonitorRule) => void;
  onAcknowledge: (alert: MonitorAlert) => void;
}

const STOCK_METRICS: RuleMetric[] = [
  "last_price",
  "change_rate",
  "change_rate_5m",
  "volume",
  "mid_price",
  "bid_ask_spread",
  "bid_ask_spread_pct",
  "ma20",
  "ma60",
  "ma20_ma60_spread_pct",
  "rsi14",
];

const OPTION_METRICS: RuleMetric[] = [
  "last_price",
  "change_rate",
  "change_rate_5m",
  "volume",
  "mid_price",
  "bid_ask_spread",
  "bid_ask_spread_pct",
  "option_implied_volatility",
  "historical_volatility",
  "iv_hv_premium",
  "option_open_interest",
  "volume_open_interest_ratio",
  "option_delta",
  "option_gamma",
  "option_vega",
  "option_theta",
  "option_rho",
  "days_to_expiry",
  "strike_distance_pct",
  "expiry_gamma_risk",
  "expiry_theta_risk",
  "call_put_volume_ratio",
  "call_put_open_interest_ratio",
];

export function AlertWorkspace({
  symbol,
  rules,
  alerts,
  loading,
  unacknowledgedOnly,
  busyRuleId,
  busyAlertId,
  creatingRule,
  onUnacknowledgedOnlyChange,
  onCreateRule,
  onToggleRule,
  onDeleteRule,
  onAcknowledge,
}: AlertWorkspaceProps) {
  const { locale, t } = useI18n();
  const formTitleId = useId();
  const [name, setName] = useState("");
  const [code, setCode] = useState(symbol);
  const [instrumentType, setInstrumentType] = useState<InstrumentType>("stock");
  const [metric, setMetric] = useState<RuleMetric>("last_price");
  const [operator, setOperator] = useState<RuleOperator>("crosses_above");
  const [threshold, setThreshold] = useState("");
  const [severity, setSeverity] = useState<RuleSeverity>("warning");
  const [cooldown, setCooldown] = useState("300");
  const [dailyLimit, setDailyLimit] = useState("10");
  const [session, setSession] = useState<"regular" | "extended" | "all">("regular");
  const metrics = instrumentType === "stock" ? STOCK_METRICS : OPTION_METRICS;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const thresholdNumber = Number(threshold);
    const cooldownNumber = Number(cooldown);
    const dailyLimitNumber = Number(dailyLimit);
    if (
      !name.trim()
      || !code.trim()
      || !Number.isFinite(thresholdNumber)
      || !Number.isInteger(cooldownNumber)
      || !Number.isInteger(dailyLimitNumber)
    ) {
      return;
    }
    onCreateRule({
      name: name.trim(),
      code: code.trim().toUpperCase(),
      underlying_code: symbol,
      instrument_type: instrumentType,
      metric,
      operator,
      threshold: thresholdNumber,
      severity,
      cooldown_seconds: cooldownNumber,
      daily_trigger_limit: dailyLimitNumber,
      session,
      enabled: true,
    });
    setName("");
    setThreshold("");
  }

  return (
    <div className="monitor-alert-workspace">
      <section className="monitor-rule-builder monitor-panel" aria-labelledby={formTitleId}>
        <header className="monitor-panel-heading">
          <div>
            <p className="section-code">RULES / PERSISTED</p>
            <h2 id={formTitleId}>{t("monitor.ruleBuilder")}</h2>
            <p>{t("monitor.ruleBuilderIntro")}</p>
          </div>
          <span>{rules.length} RULES</span>
        </header>
        <form onSubmit={submit}>
          <label className="monitor-field wide">
            <span>{t("monitor.ruleName")}</span>
            <input
              value={name}
              maxLength={120}
              required
              placeholder={t("monitor.ruleNamePlaceholder")}
              onChange={(event) => setName(event.currentTarget.value)}
            />
          </label>
          <label className="monitor-field">
            <span>{t("monitor.instrumentType")}</span>
            <select
              value={instrumentType}
              onChange={(event) => {
                const next = event.currentTarget.value as InstrumentType;
                setInstrumentType(next);
                const nextMetrics = next === "stock" ? STOCK_METRICS : OPTION_METRICS;
                setMetric(nextMetrics[0]);
                setCode(next === "stock" ? symbol : "");
              }}
            >
              <option value="stock">{t("monitor.stock")}</option>
              <option value="option">{t("monitor.option")}</option>
            </select>
          </label>
          <label className="monitor-field">
            <span>{t("monitor.ruleCode")}</span>
            <input
              value={code}
              required
              pattern="[A-Za-z]{2,8}\\.[A-Za-z0-9.-]{1,24}"
              placeholder={instrumentType === "stock" ? symbol : "US.AAPL260731C200000"}
              onChange={(event) => setCode(event.currentTarget.value)}
            />
          </label>
          <label className="monitor-field">
            <span>{t("monitor.metric")}</span>
            <select
              value={metric}
              onChange={(event) => setMetric(event.currentTarget.value as RuleMetric)}
            >
              {metrics.map((item) => (
                <option key={item} value={item}>
                  {metricLabel(item, locale)}
                </option>
              ))}
            </select>
          </label>
          <label className="monitor-field">
            <span>{t("monitor.operator")}</span>
            <select
              value={operator}
              onChange={(event) => setOperator(event.currentTarget.value as RuleOperator)}
            >
              <option value="above">{t("monitor.operatorAbove")}</option>
              <option value="below">{t("monitor.operatorBelow")}</option>
              <option value="crosses_above">{t("monitor.operatorCrossAbove")}</option>
              <option value="crosses_below">{t("monitor.operatorCrossBelow")}</option>
            </select>
          </label>
          <label className="monitor-field">
            <span>{t("monitor.threshold")}</span>
            <input
              type="number"
              step="any"
              value={threshold}
              required
              onChange={(event) => setThreshold(event.currentTarget.value)}
            />
          </label>
          <label className="monitor-field">
            <span>{t("monitor.severity")}</span>
            <select
              value={severity}
              onChange={(event) => setSeverity(event.currentTarget.value as RuleSeverity)}
            >
              <option value="info">{t("monitor.severityInfo")}</option>
              <option value="warning">{t("monitor.severityWarning")}</option>
              <option value="critical">{t("monitor.severityCritical")}</option>
            </select>
          </label>
          <details className="monitor-rule-advanced">
            <summary>{t("monitor.advancedRule")}</summary>
            <div>
              <label className="monitor-field">
                <span>{t("monitor.cooldown")}</span>
                <input
                  type="number"
                  min="0"
                  max="86400"
                  value={cooldown}
                  required
                  onChange={(event) => setCooldown(event.currentTarget.value)}
                />
              </label>
              <label className="monitor-field">
                <span>{t("monitor.dailyLimit")}</span>
                <input
                  type="number"
                  min="1"
                  max="1000"
                  value={dailyLimit}
                  required
                  onChange={(event) => setDailyLimit(event.currentTarget.value)}
                />
              </label>
              <label className="monitor-field">
                <span>{t("monitor.session")}</span>
                <select
                  value={session}
                  onChange={(event) =>
                    setSession(event.currentTarget.value as typeof session)}
                >
                  <option value="regular">{t("monitor.sessionRegular")}</option>
                  <option value="extended">{t("monitor.sessionExtended")}</option>
                  <option value="all">{t("monitor.sessionAll")}</option>
                </select>
              </label>
            </div>
          </details>
          <button className="monitor-primary-button" type="submit" disabled={creatingRule}>
            <span>{creatingRule ? t("monitor.creatingRule") : t("monitor.createRule")}</span>
            <strong>＋</strong>
          </button>
        </form>
        <p className="monitor-safety-note">{t("monitor.ruleSafety")}</p>
      </section>

      <section className="monitor-rule-ledger monitor-panel" aria-labelledby="monitorRulesTitle">
        <header className="monitor-panel-heading">
          <div>
            <p className="section-code">ACTIVE LOGIC</p>
            <h2 id="monitorRulesTitle">{t("monitor.rules")}</h2>
          </div>
        </header>
        {loading && rules.length === 0 ? (
          <p className="monitor-inline-empty">{t("monitor.rulesLoading")}</p>
        ) : rules.length === 0 ? (
          <p className="monitor-inline-empty">{t("monitor.rulesEmpty")}</p>
        ) : (
          <ul>
            {rules.map((rule) => (
              <li key={rule.id} data-enabled={rule.enabled}>
                <div>
                  <span className={`monitor-severity ${rule.severity}`}>
                    {rule.severity}
                  </span>
                  <strong>{rule.name}</strong>
                  <small>{rule.code}</small>
                </div>
                <p>
                  {metricLabel(rule.metric, locale)}
                  {" · "}
                  {operatorLabel(rule.operator, t)}
                  {" · "}
                  <strong>{formatGreek(rule.threshold, locale, 4)}</strong>
                </p>
                <footer>
                  <span>
                    {t("monitor.ruleCadence", {
                      cooldown: rule.cooldown_seconds,
                      limit: rule.daily_trigger_limit,
                    })}
                  </span>
                  <div>
                    <button
                      type="button"
                      aria-pressed={rule.enabled}
                      disabled={busyRuleId === rule.id}
                      onClick={() => onToggleRule(rule)}
                    >
                      {rule.enabled ? t("monitor.enabled") : t("monitor.disabled")}
                    </button>
                    <button
                      type="button"
                      className="negative"
                      disabled={busyRuleId === rule.id}
                      aria-label={t("monitor.deleteRule", { name: rule.name })}
                      onClick={() => onDeleteRule(rule)}
                    >
                      ×
                    </button>
                  </div>
                </footer>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="monitor-alert-ledger monitor-panel" aria-labelledby="monitorAlertsTitle">
        <header className="monitor-panel-heading">
          <div>
            <p className="section-code">ALERT LEDGER</p>
            <h2 id="monitorAlertsTitle">{t("monitor.alerts")}</h2>
          </div>
          <label className="monitor-alert-filter">
            <input
              type="checkbox"
              checked={unacknowledgedOnly}
              onChange={(event) =>
                onUnacknowledgedOnlyChange(event.currentTarget.checked)}
            />
            <span>{t("monitor.unacknowledgedOnly")}</span>
          </label>
        </header>
        {loading && alerts.length === 0 ? (
          <p className="monitor-inline-empty">{t("monitor.alertsLoading")}</p>
        ) : alerts.length === 0 ? (
          <MonitorStatePanel state="empty" compact detail={t("monitor.alertsEmpty")} />
        ) : (
          <ol>
            {alerts.map((alert) => (
              <li
                key={alert.id}
                data-acknowledged={Boolean(alert.acknowledged_at)}
                data-severity={alert.severity}
              >
                <div className="monitor-alert-index" aria-hidden="true">
                  {alert.severity === "critical" ? "!" : "•"}
                </div>
                <div>
                  <header>
                    <span className={`monitor-severity ${alert.severity}`}>
                      {alert.severity}
                    </span>
                    <strong>{alert.rule_name}</strong>
                    <time>{formatQuoteTimestamp(alert.provider_time)}</time>
                  </header>
                  <p>
                    {alert.code}
                    {" · "}
                    {metricLabel(alert.metric, locale)}
                    {" "}
                    {operatorLabel(alert.operator, t)}
                    {" "}
                    {formatGreek(alert.threshold, locale, 4)}
                  </p>
                  <footer>
                    <span>
                      {t("monitor.alertObserved", {
                        value: formatGreek(alert.value, locale, 4),
                      })}
                    </span>
                    {alert.acknowledged_at ? (
                      <span>
                        {t("monitor.acknowledgedAt", {
                          time: formatQuoteTimestamp(alert.acknowledged_at),
                        })}
                      </span>
                    ) : (
                      <button
                        type="button"
                        disabled={busyAlertId === alert.id}
                        onClick={() => onAcknowledge(alert)}
                      >
                        {t("monitor.acknowledge")}
                      </button>
                    )}
                  </footer>
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}

function metricLabel(metric: RuleMetric, locale: "zh-CN" | "en-US"): string {
  const english = metric
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
  if (locale === "en-US") return english;
  const labels: Partial<Record<RuleMetric, string>> = {
    last_price: "最新价",
    change_rate: "涨跌幅",
    change_rate_5m: "5 分钟涨跌幅",
    volume: "成交量",
    mid_price: "中间价",
    bid_ask_spread: "买卖价差",
    bid_ask_spread_pct: "买卖价差率",
    ma20: "MA20",
    ma60: "MA60",
    ma20_ma60_spread_pct: "MA20 / MA60 偏离",
    rsi14: "RSI14",
    option_implied_volatility: "期权隐含波动率",
    historical_volatility: "历史波动率",
    iv_hv_premium: "IV / HV 溢价",
    option_open_interest: "未平仓量",
    volume_open_interest_ratio: "成交量 / OI",
    option_delta: "Delta",
    option_gamma: "Gamma",
    option_vega: "Vega",
    option_theta: "Theta",
    option_rho: "Rho",
    days_to_expiry: "剩余到期日",
    strike_distance_pct: "行权价距离",
    expiry_gamma_risk: "临近到期 Gamma 风险",
    expiry_theta_risk: "临近到期 Theta 风险",
    call_put_volume_ratio: "Call / Put 成交量比",
    call_put_open_interest_ratio: "Call / Put OI 比",
  };
  return labels[metric] ?? english;
}

function operatorLabel(
  operator: RuleOperator,
  t: ReturnType<typeof useI18n>["t"],
): string {
  const labels = {
    above: t("monitor.operatorAbove"),
    below: t("monitor.operatorBelow"),
    crosses_above: t("monitor.operatorCrossAbove"),
    crosses_below: t("monitor.operatorCrossBelow"),
  };
  return labels[operator];
}
