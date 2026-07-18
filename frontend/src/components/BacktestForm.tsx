import type { FormEvent } from "react";
import type { AppConfig, BacktestRequest, StrategyCompatibility, StrategyParameterDefinition } from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import { readParameterValues } from "../lib/parameters";
import { StrategyParameterFields } from "./StrategyParameterFields";

interface BacktestFormProps {
  config?: AppConfig;
  selectedStrategy: string;
  onStrategyChange: (path: string) => void;
  onSubmit: (request: BacktestRequest) => void;
  running: boolean;
  opendConnected: boolean;
  parameterDefinitions?: StrategyParameterDefinition[];
  compatibility?: StrategyCompatibility;
}

export function BacktestForm({
  config,
  selectedStrategy,
  onStrategyChange,
  onSubmit,
  running,
  opendConnected,
  parameterDefinitions = [],
  compatibility,
}: BacktestFormProps) {
  const { t } = useI18n();
  const sessionLabels: Record<string, string> = {
    ALL: t("form.sessionAll"),
    RTH: t("form.sessionRth"),
    ETH: t("form.sessionEth"),
  };
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    onSubmit({
      strategy: String(data.get("strategy")),
      symbol: String(data.get("symbol")).trim().toUpperCase(),
      start: String(data.get("start")),
      end: String(data.get("end")),
      ktype: String(data.get("ktype")),
      autype: String(data.get("autype")),
      session: String(data.get("session")),
      initial_cash: Number(data.get("initial_cash")),
      commission_bps: Number(data.get("commission_bps")),
      min_commission: Number(data.get("min_commission")),
      slippage_bps: Number(data.get("slippage_bps")),
      warmup_bars: Number(data.get("warmup_bars")),
      allow_short: data.get("allow_short") === "on",
      liquidate_on_end: data.get("liquidate_on_end") === "on",
      parameters: readParameterValues(data, parameterDefinitions),
      refresh_cache: data.get("refresh_cache") === "on",
    });
  }

  const groupedStrategies = new Map<string, NonNullable<AppConfig["strategies"]>>();
  (config?.strategies ?? []).forEach((strategy) => {
    const group = groupedStrategies.get(strategy.group) ?? [];
    group.push(strategy);
    groupedStrategies.set(strategy.group, group);
  });

  return (
    <form className="backtest-form" onSubmit={handleSubmit}>
      <label className="field field-wide">
        <span>{t("form.strategy")}</span>
        <select
          name="strategy"
          required
          value={selectedStrategy}
          onChange={(event) => onStrategyChange(event.target.value)}
        >
          {[...groupedStrategies].map(([group, strategies]) => (
            <optgroup key={group} label={group === "示例策略" ? t("strategy.groupExamples") : group === "我的策略" ? t("strategy.groupMine") : group}>
              {strategies.map((strategy) => (
                <option key={strategy.path} value={strategy.path}>
                  {strategy.name} · {strategy.path}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </label>

      <StrategyParameterFields definitions={parameterDefinitions} />

      {compatibility && !compatibility.supported ? (
        <aside className="strategy-compatibility" role="alert">
          <strong>{t("form.compatibilityBlocked")}</strong>
          {compatibility.unsupported_names.length > 0 ? (
            <p>{t("form.unsupportedNames", { names: compatibility.unsupported_names.join(" · ") })}</p>
          ) : null}
          {compatibility.bar_types.length > 1 ? (
            <p>{t("form.multipleBarTypes", { types: compatibility.bar_types.join(" · ") })}</p>
          ) : null}
          <small>{t("form.compatibilityHelp")}</small>
        </aside>
      ) : null}

      <label className="field field-wide">
        <span>{t("form.symbol")}</span>
        <input name="symbol" defaultValue="US.AAPL" placeholder="US.AAPL" required />
        <small>{t("form.symbolHelp")}</small>
      </label>

      <div className="field-pair">
        <label className="field">
          <span>{t("form.start")}</span>
          <input type="date" name="start" defaultValue="2024-01-01" required />
        </label>
        <label className="field">
          <span>{t("form.end")}</span>
          <input type="date" name="end" defaultValue="2025-12-31" required />
        </label>
      </div>

      <div className="field-pair">
        <label className="field">
          <span>{t("form.ktype")}</span>
          <select
            key={`ktype-${selectedStrategy}`}
            name="ktype"
            defaultValue={compatibility?.bar_types.length === 1 ? compatibility.bar_types[0] : "K_DAY"}
          >
            {(config?.kline_types ?? ["K_DAY"]).map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>{t("form.autype")}</span>
          <select name="autype" defaultValue="QFQ">
            <option value="QFQ">{t("form.autypeQfq")}</option>
            <option value="HFQ">{t("form.autypeHfq")}</option>
            <option value="NONE">{t("form.autypeNone")}</option>
          </select>
        </label>
      </div>

      <label className="field field-wide session-field">
        <span>{t("form.session")}</span>
        <select name="session" defaultValue="ALL">
          {(config?.session_types ?? ["ALL", "RTH", "ETH"]).map((value) => (
            <option key={value} value={value}>
              {sessionLabels[value] ?? value}
            </option>
          ))}
        </select>
        <small>{t("form.sessionHelp")}</small>
      </label>

      <details className="execution-sheet">
        <summary>{t("form.execution")}</summary>
        <div className="execution-grid">
          <label className="field"><span>{t("form.initialCash")}</span><input type="number" name="initial_cash" defaultValue="100000" min="1" /></label>
          <label className="field" title={t("form.warmupHelp")}><span>{t("form.warmup")}</span><input type="number" name="warmup_bars" defaultValue="0" min="0" /></label>
          <label className="field"><span>{t("form.commission")}</span><input type="number" name="commission_bps" defaultValue="3" min="0" step="0.1" /></label>
          <label className="field"><span>{t("form.minCommission")}</span><input type="number" name="min_commission" defaultValue="1" min="0" step="0.1" /></label>
          <label className="field"><span>{t("form.slippage")}</span><input type="number" name="slippage_bps" defaultValue="5" min="0" step="0.1" /></label>
          <label className="check-field"><input type="checkbox" name="allow_short" /><span>{t("form.allowShort")}</span></label>
          <label className="check-field"><input type="checkbox" name="liquidate_on_end" /><span>{t("form.liquidate")}</span></label>
          <label className="check-field"><input type="checkbox" name="refresh_cache" /><span>{t("form.refreshCache")}</span></label>
        </div>
      </details>

      <div className="run-action">
        <button type="submit" disabled={running || !opendConnected || !selectedStrategy || compatibility?.supported === false}>
          <span>{running ? t("form.running") : t("form.run")}</span>
          <span aria-hidden="true">↗</span>
        </button>
        <p>{t("form.safety")}</p>
      </div>
    </form>
  );
}
