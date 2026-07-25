import { useState, type FormEvent } from "react";
import type {
  AppConfig,
  ExperimentObjective,
  ExperimentRequest,
  MetricConstraint,
  ParameterValue,
  StrategyParameterDefinition,
} from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import { localizeParameter } from "../lib/parameterLocalization";
import { SymbolSearchField } from "./SymbolSearchField";

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
  const { locale, t } = useI18n();
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
  const [outOfSample, setOutOfSample] = useState(false);
  const [includeTest, setIncludeTest] = useState(false);
  const [walkForward, setWalkForward] = useState(false);
  const [walkForwardFolds, setWalkForwardFolds] = useState(3);
  const [constraints, setConstraints] = useState<MetricConstraint[]>([]);
  const [batchValidation, setBatchValidation] = useState(false);
  const [batchSymbols, setBatchSymbols] = useState("US.AAPL, US.MSFT, US.NVDA");
  const parsedBatchSymbols = parseSymbols(batchSymbols);
  const combinationCount = parameterDefinitions.reduce(
    (count, definition) => count * parseGridValues(gridText[definition.name] ?? "", definition).length,
    1,
  );

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const parameterGrid = batchValidation ? {} : Object.fromEntries(
      parameterDefinitions.map((definition) => [
        definition.name,
        parseGridValues(gridText[definition.name] ?? "", definition),
      ]),
    );
    const defaults = Object.fromEntries(
      parameterDefinitions.map((definition) => [definition.name, definition.default]),
    );
    const validation = outOfSample
      ? {
          start: String(data.get("validation_start")),
          end: String(data.get("validation_end")),
        }
      : undefined;
    const test = outOfSample && includeTest
      ? {
          start: String(data.get("test_start")),
          end: String(data.get("test_end")),
        }
      : undefined;
    onSubmit({
      name: String(data.get("name")).trim(),
      objective: String(data.get("objective")) as ExperimentObjective,
      parameter_grid: parameterGrid,
      symbols: batchValidation ? parsedBatchSymbols : [],
      validation,
      test,
      walk_forward_folds: walkForward ? walkForwardFolds : 0,
      constraints,
      base: {
        strategy: selectedStrategy,
        symbol: batchValidation
          ? parsedBatchSymbols[0] ?? ""
          : String(data.get("symbol")).trim().toUpperCase(),
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
    || (!batchValidation && parameterDefinitions.length === 0)
    || (!batchValidation && (combinationCount < 1 || combinationCount > 36))
    || (batchValidation && (parsedBatchSymbols.length < 2 || parsedBatchSymbols.length > 36))
    || (!batchValidation && walkForward && combinationCount * walkForwardFolds * 2 > 72);

  return (
    <form className="experiment-form" onSubmit={handleSubmit}>
      <div className="experiment-form-intro">
        <span className="section-code">SEARCH SPACE</span>
        <h2>{t("experiment.matrix")}</h2>
        <p>{t("experiment.intro")}</p>
      </div>

      <div className="experiment-mode-switch" role="group" aria-label={t("experiment.mode")}>
        <button type="button" aria-pressed={!batchValidation} onClick={() => setBatchValidation(false)}>
          {t("experiment.parameterMode")}
        </button>
        <button
          type="button"
          aria-pressed={batchValidation}
          onClick={() => {
            setBatchValidation(true);
            setOutOfSample(false);
            setIncludeTest(false);
            setWalkForward(false);
          }}
        >
          {t("experiment.batchMode")}
        </button>
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

      <div className="field-pair experiment-symbol-row">
        {batchValidation ? (
          <label className="field batch-symbols-field">
            <span>{t("experiment.symbolPool")}</span>
            <textarea
              aria-label={t("experiment.symbolPool")}
              value={batchSymbols}
              onChange={(event) => setBatchSymbols(event.target.value)}
              rows={3}
            />
            <small>{t("experiment.symbolPoolHelp", { count: parsedBatchSymbols.length })}</small>
          </label>
        ) : <SymbolSearchField searchEnabled={opendConnected} />}
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

      {!batchValidation ? <section className="grid-editor research-window-editor">
        <label className="check-field">
          <input
            type="checkbox"
            checked={outOfSample}
            onChange={(event) => {
              setOutOfSample(event.target.checked);
              if (event.target.checked) setWalkForward(false);
              if (!event.target.checked) setIncludeTest(false);
            }}
          />
          <span>{t("experiment.enableOutOfSample")}</span>
        </label>
        <p>{t("experiment.outOfSampleHelp")}</p>
        {outOfSample ? (
          <>
            <div className="field-pair">
              <label className="field"><span>{t("experiment.validationStart")}</span><input type="date" name="validation_start" defaultValue="2026-01-01" required /></label>
              <label className="field"><span>{t("experiment.validationEnd")}</span><input type="date" name="validation_end" defaultValue="2026-03-31" required /></label>
            </div>
            <label className="check-field">
              <input
                type="checkbox"
                checked={includeTest}
                onChange={(event) => setIncludeTest(event.target.checked)}
              />
              <span>{t("experiment.enableTestWindow")}</span>
            </label>
            {includeTest ? (
              <div className="field-pair">
                <label className="field"><span>{t("experiment.testStart")}</span><input type="date" name="test_start" defaultValue="2026-04-01" required /></label>
                <label className="field"><span>{t("experiment.testEnd")}</span><input type="date" name="test_end" defaultValue="2026-06-30" required /></label>
              </div>
            ) : null}
          </>
        ) : null}
        <label className="check-field">
          <input
            type="checkbox"
            checked={walkForward}
            onChange={(event) => {
              setWalkForward(event.target.checked);
              if (event.target.checked) {
                setOutOfSample(false);
                setIncludeTest(false);
              }
            }}
          />
          <span>{t("experiment.enableWalkForward")}</span>
        </label>
        {walkForward ? (
          <label className="field">
            <span>{t("experiment.walkForwardFolds")}</span>
            <input
              type="number"
              min="2"
              max="5"
              value={walkForwardFolds}
              onChange={(event) => setWalkForwardFolds(Number(event.target.value))}
            />
          </label>
        ) : null}
        <small>{t("experiment.plannedJobs", { count: walkForward ? combinationCount * walkForwardFolds * 2 : combinationCount * (outOfSample ? 2 : 1) + (includeTest ? 1 : 0) })}</small>
      </section> : null}

      <section className="grid-editor constraint-editor" aria-labelledby="constraintEditorTitle">
        <div className="grid-editor-heading">
          <h3 id="constraintEditorTitle">{t("experiment.constraints")}</h3>
          <button
            type="button"
            onClick={() => setConstraints((current) => [
              ...current,
              { metric: "max_drawdown_pct", op: ">=", value: -15 },
            ])}
          >
            {t("experiment.addConstraint")}
          </button>
        </div>
        {constraints.length === 0 ? <p>{t("experiment.constraintsHelp")}</p> : null}
        {constraints.map((constraint, index) => (
          <div className="constraint-row" key={`${index}-${constraint.metric}`}>
            <select
              aria-label={t("experiment.constraintMetric", { index: index + 1 })}
              value={constraint.metric}
              onChange={(event) => updateConstraint(index, {
                metric: event.target.value as MetricConstraint["metric"],
              })}
            >
              <option value="max_drawdown_pct">{t("metrics.drawdown")}</option>
              <option value="total_trades">{t("metrics.trades")}</option>
              <option value="sharpe_ratio">Sharpe</option>
              <option value="total_return_pct">{t("metrics.return")}</option>
              <option value="total_fees">{t("metrics.fees")}</option>
              <option value="exposure_pct">{t("metrics.exposure")}</option>
            </select>
            <select
              aria-label={t("experiment.constraintOperator", { index: index + 1 })}
              value={constraint.op}
              onChange={(event) => updateConstraint(index, {
                op: event.target.value as MetricConstraint["op"],
              })}
            >
              <option value=">=">≥</option>
              <option value="<=">≤</option>
            </select>
            <input
              aria-label={t("experiment.constraintValue", { index: index + 1 })}
              type="number"
              step="any"
              value={constraint.value}
              onChange={(event) => updateConstraint(index, { value: Number(event.target.value) })}
            />
            <button
              type="button"
              aria-label={t("experiment.removeConstraint", { index: index + 1 })}
              onClick={() => setConstraints((current) => current.filter((_, itemIndex) => itemIndex !== index))}
            >
              ×
            </button>
          </div>
        ))}
      </section>

      {!batchValidation ? <section className="grid-editor" aria-labelledby="gridEditorTitle">
        <div className="grid-editor-heading">
          <h3 id="gridEditorTitle">{t("experiment.candidates")}</h3>
          <span className={combinationCount > 36 ? "negative" : ""}>{t("experiment.combinations", { count: combinationCount })}</span>
        </div>
        {parameterDefinitions.length === 0 ? (
          <p className="quiet-state">{t("experiment.parametersRequired")}</p>
        ) : null}
        {parameterDefinitions.map((definition) => {
          const copy = localizeParameter(definition, locale);
          return (
            <label className="grid-value-field" key={definition.name}>
              <span><strong>{copy.label}</strong><small>{definition.name} · {definition.type}</small></span>
              <input
                aria-label={t("experiment.candidateLabel", { label: copy.label })}
                value={gridText[definition.name] ?? ""}
                onChange={(event) => setGridText((current) => ({ ...current, [definition.name]: event.target.value }))}
                placeholder={String(definition.default)}
                required
              />
              <small>{t("experiment.range", { range: formatRange(definition, t("experiment.freeValue")) })}</small>
            </label>
          );
        })}
      </section> : null}

      <details className="execution-sheet">
        <summary>{t("experiment.options")}</summary>
        <div className="execution-grid">
          <label className="field"><span>{t("form.initialCash")}</span><input type="number" name="initial_cash" defaultValue="100000" min="1" /></label>
          <label className="check-field"><input type="checkbox" name="refresh_cache" /><span>{t("experiment.refreshCache")}</span></label>
        </div>
      </details>

      <button className="experiment-run-button" type="submit" disabled={disabled}>
        <span>{running ? t("experiment.running") : batchValidation
          ? t("experiment.runSymbols", { count: parsedBatchSymbols.length })
          : t("experiment.run", { count: combinationCount })}</span>
        <span aria-hidden="true">→</span>
      </button>
      <p className="experiment-safety">{t("experiment.safety")}</p>
    </form>
  );

  function updateConstraint(index: number, patch: Partial<MetricConstraint>) {
    setConstraints((current) =>
      current.map((constraint, itemIndex) =>
        itemIndex === index ? { ...constraint, ...patch } : constraint,
      ),
    );
  }
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

function parseSymbols(text: string): string[] {
  return [...new Set(
    text
      .split(/[\s,;]+/)
      .map((value) => value.trim().toUpperCase())
      .filter(Boolean),
  )];
}
