import { useState, type FormEvent } from "react";
import type {
  AppConfig,
  ExperimentObjective,
  ExperimentRequest,
  ParameterValue,
  StrategyParameterDefinition,
} from "../api/types";
import { useI18n } from "../i18n/I18nContext";

interface ExperimentFormProps {
  config?: AppConfig;
  selectedStrategy: string;
  parameterDefinitions: StrategyParameterDefinition[];
  onStrategyChange: (path: string) => void;
  onSubmit: (request: ExperimentRequest) => void;
  running: boolean;
  opendConnected: boolean;
}

export function ExperimentForm({
  config,
  selectedStrategy,
  parameterDefinitions,
  onStrategyChange,
  onSubmit,
  running,
  opendConnected,
}: ExperimentFormProps) {
  const { t } = useI18n();
  const objectives: Array<{ value: ExperimentObjective; label: string }> = [
    { value: "sharpe_ratio", label: t("experiment.objectiveSharpe") },
    { value: "total_return_pct", label: t("experiment.objectiveReturn") },
    { value: "max_drawdown_pct", label: t("experiment.objectiveDrawdown") },
  ];
  const [gridText, setGridText] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      parameterDefinitions.map((definition) => [
        definition.name,
        definition.candidates.join(", "),
      ]),
    ),
  );
  const combinationCount = parameterDefinitions.reduce(
    (count, definition) => count * parseGridValues(gridText[definition.name] ?? "", definition).length,
    1,
  );

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const parameterGrid = Object.fromEntries(
      parameterDefinitions.map((definition) => [
        definition.name,
        parseGridValues(gridText[definition.name] ?? "", definition),
      ]),
    );
    const defaults = Object.fromEntries(
      parameterDefinitions.map((definition) => [definition.name, definition.default]),
    );
    onSubmit({
      name: String(data.get("name")).trim(),
      objective: String(data.get("objective")) as ExperimentObjective,
      parameter_grid: parameterGrid,
      base: {
        strategy: selectedStrategy,
        symbol: String(data.get("symbol")).trim().toUpperCase(),
        start: String(data.get("start")),
        end: String(data.get("end")),
        ktype: String(data.get("ktype")),
        autype: "QFQ",
        session: String(data.get("session")),
        initial_cash: Number(data.get("initial_cash")),
        commission_bps: 3,
        min_commission: 1,
        slippage_bps: 5,
        warmup_bars: 0,
        allow_short: false,
        liquidate_on_end: false,
        parameters: defaults,
        refresh_cache: data.get("refresh_cache") === "on",
      },
    });
  }

  const disabled =
    running
    || !opendConnected
    || !selectedStrategy
    || parameterDefinitions.length === 0
    || combinationCount < 1
    || combinationCount > 36;

  return (
    <form className="experiment-form" onSubmit={handleSubmit}>
      <div className="experiment-form-intro">
        <span className="section-code">SEARCH SPACE</span>
        <h2>{t("experiment.matrix")}</h2>
        <p>{t("experiment.intro")}</p>
      </div>

      <label className="field">
        <span>{t("experiment.name")}</span>
        <input name="name" defaultValue={t("experiment.defaultName")} maxLength={80} required />
      </label>
      <label className="field">
        <span>{t("form.strategy")}</span>
        <select value={selectedStrategy} onChange={(event) => onStrategyChange(event.target.value)}>
          {(config?.strategies ?? []).map((strategy) => (
            <option key={strategy.path} value={strategy.path}>{strategy.name} · {strategy.path}</option>
          ))}
        </select>
      </label>

      <div className="field-pair">
        <label className="field"><span>{t("form.symbol")}</span><input name="symbol" defaultValue="US.AAPL" required /></label>
        <label className="field"><span>{t("experiment.objective")}</span><select name="objective" defaultValue="sharpe_ratio">{objectives.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
      </div>
      <div className="field-pair">
        <label className="field"><span>{t("form.start")}</span><input type="date" name="start" defaultValue="2024-01-01" required /></label>
        <label className="field"><span>{t("form.end")}</span><input type="date" name="end" defaultValue="2025-12-31" required /></label>
      </div>
      <div className="field-pair">
        <label className="field"><span>{t("form.ktype")}</span><select name="ktype" defaultValue="K_DAY">{(config?.kline_types ?? ["K_DAY"]).map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label className="field"><span>{t("form.session")}</span><select name="session" defaultValue="ALL">{(config?.session_types ?? ["ALL"]).map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
      </div>

      <section className="grid-editor" aria-labelledby="gridEditorTitle">
        <div className="grid-editor-heading">
          <h3 id="gridEditorTitle">{t("experiment.candidates")}</h3>
          <span className={combinationCount > 36 ? "negative" : ""}>{t("experiment.combinations", { count: combinationCount })}</span>
        </div>
        {parameterDefinitions.length === 0 ? (
          <p className="quiet-state">{t("experiment.parametersRequired")}</p>
        ) : null}
        {parameterDefinitions.map((definition) => (
          <label className="grid-value-field" key={definition.name}>
            <span><strong>{definition.label}</strong><small>{definition.name} · {definition.type}</small></span>
            <input
              aria-label={t("experiment.candidateLabel", { label: definition.label })}
              value={gridText[definition.name] ?? ""}
              onChange={(event) => setGridText((current) => ({ ...current, [definition.name]: event.target.value }))}
              placeholder={String(definition.default)}
              required
            />
            <small>{t("experiment.range", { range: formatRange(definition, t("experiment.freeValue")) })}</small>
          </label>
        ))}
      </section>

      <details className="execution-sheet">
        <summary>{t("experiment.options")}</summary>
        <div className="execution-grid">
          <label className="field"><span>{t("form.initialCash")}</span><input type="number" name="initial_cash" defaultValue="100000" min="1" /></label>
          <label className="check-field"><input type="checkbox" name="refresh_cache" /><span>{t("experiment.refreshCache")}</span></label>
        </div>
      </details>

      <button className="experiment-run-button" type="submit" disabled={disabled}>
        <span>{running ? t("experiment.running") : t("experiment.run", { count: combinationCount })}</span>
        <span aria-hidden="true">→</span>
      </button>
      <p className="experiment-safety">{t("experiment.safety")}</p>
    </form>
  );
}

function parseGridValues(
  text: string,
  definition: StrategyParameterDefinition,
): ParameterValue[] {
  const parts = text.split(",").map((value) => value.trim()).filter(Boolean);
  return parts.map((value) => {
    if (definition.type === "bool") return value.toLowerCase() === "true";
    if (definition.type === "int") return Number.parseInt(value, 10);
    if (definition.type === "float") return Number.parseFloat(value);
    return value;
  }).filter((value, index, values) => values.indexOf(value) === index);
}

function formatRange(definition: StrategyParameterDefinition, freeValue: string): string {
  if (definition.choices) return definition.choices.join(" / ");
  if (definition.min !== undefined || definition.max !== undefined) {
    return `${definition.min ?? "−∞"} — ${definition.max ?? "+∞"}`;
  }
  return freeValue;
}
