import { useState, type FormEvent } from "react";
import type {
  AppConfig,
  ExperimentObjective,
  ExperimentRequest,
  ParameterValue,
  StrategyParameterDefinition,
} from "../api/types";

const OBJECTIVES: Array<{ value: ExperimentObjective; label: string }> = [
  { value: "sharpe_ratio", label: "Sharpe 最高" },
  { value: "total_return_pct", label: "策略收益最高" },
  { value: "max_drawdown_pct", label: "最大回撤最小" },
];

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
        <h2>参数矩阵</h2>
        <p>每组参数使用同一份 OpenD 行情和撮合规则，按目标指标自动排名。</p>
      </div>

      <label className="field">
        <span>实验名称</span>
        <input name="name" defaultValue="MA 参数矩阵" maxLength={80} required />
      </label>
      <label className="field">
        <span>策略脚本</span>
        <select value={selectedStrategy} onChange={(event) => onStrategyChange(event.target.value)}>
          {(config?.strategies ?? []).map((strategy) => (
            <option key={strategy.path} value={strategy.path}>{strategy.name} · {strategy.path}</option>
          ))}
        </select>
      </label>

      <div className="field-pair">
        <label className="field"><span>标的代码</span><input name="symbol" defaultValue="US.AAPL" required /></label>
        <label className="field"><span>排名目标</span><select name="objective" defaultValue="sharpe_ratio">{OBJECTIVES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
      </div>
      <div className="field-pair">
        <label className="field"><span>开始日期</span><input type="date" name="start" defaultValue="2024-01-01" required /></label>
        <label className="field"><span>结束日期</span><input type="date" name="end" defaultValue="2025-12-31" required /></label>
      </div>
      <div className="field-pair">
        <label className="field"><span>K 线周期</span><select name="ktype" defaultValue="K_DAY">{(config?.kline_types ?? ["K_DAY"]).map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label className="field"><span>交易时段</span><select name="session" defaultValue="ALL">{(config?.session_types ?? ["ALL"]).map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
      </div>

      <section className="grid-editor" aria-labelledby="gridEditorTitle">
        <div className="grid-editor-heading">
          <h3 id="gridEditorTitle">候选值</h3>
          <span className={combinationCount > 36 ? "negative" : ""}>{combinationCount} 组组合</span>
        </div>
        {parameterDefinitions.length === 0 ? (
          <p className="quiet-state">策略需要声明 STRATEGY_PARAMETERS 才能创建实验。</p>
        ) : null}
        {parameterDefinitions.map((definition) => (
          <label className="grid-value-field" key={definition.name}>
            <span><strong>{definition.label}</strong><small>{definition.name} · {definition.type}</small></span>
            <input
              aria-label={`${definition.label}候选值`}
              value={gridText[definition.name] ?? ""}
              onChange={(event) => setGridText((current) => ({ ...current, [definition.name]: event.target.value }))}
              placeholder={String(definition.default)}
              required
            />
            <small>逗号分隔；范围 {formatRange(definition)}</small>
          </label>
        ))}
      </section>

      <details className="execution-sheet">
        <summary>实验执行选项</summary>
        <div className="execution-grid">
          <label className="field"><span>初始资金</span><input type="number" name="initial_cash" defaultValue="100000" min="1" /></label>
          <label className="check-field"><input type="checkbox" name="refresh_cache" /><span>首组重新拉取 OpenD 行情</span></label>
        </div>
      </details>

      <button className="experiment-run-button" type="submit" disabled={disabled}>
        <span>{running ? "参数实验运行中" : `运行 ${combinationCount} 组参数`}</span>
        <span aria-hidden="true">→</span>
      </button>
      <p className="experiment-safety">最多 36 组，顺序执行；首组之后自动复用行情缓存。</p>
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

function formatRange(definition: StrategyParameterDefinition): string {
  if (definition.choices) return definition.choices.join(" / ");
  if (definition.min !== undefined || definition.max !== undefined) {
    return `${definition.min ?? "−∞"} — ${definition.max ?? "+∞"}`;
  }
  return "自由值";
}
