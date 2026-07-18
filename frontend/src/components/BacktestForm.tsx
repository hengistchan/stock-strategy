import type { FormEvent } from "react";
import type { AppConfig, BacktestRequest, StrategyParameterDefinition } from "../api/types";
import { readParameterValues } from "../lib/parameters";
import { StrategyParameterFields } from "./StrategyParameterFields";

const SESSION_LABELS: Record<string, string> = {
  ALL: "全部时段 · ALL",
  RTH: "常规时段 · RTH",
  ETH: "扩展时段 · ETH",
};

interface BacktestFormProps {
  config?: AppConfig;
  selectedStrategy: string;
  onStrategyChange: (path: string) => void;
  onSubmit: (request: BacktestRequest) => void;
  running: boolean;
  opendConnected: boolean;
  parameterDefinitions?: StrategyParameterDefinition[];
}

export function BacktestForm({
  config,
  selectedStrategy,
  onStrategyChange,
  onSubmit,
  running,
  opendConnected,
  parameterDefinitions = [],
}: BacktestFormProps) {
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
        <span>策略脚本</span>
        <select
          name="strategy"
          required
          value={selectedStrategy}
          onChange={(event) => onStrategyChange(event.target.value)}
        >
          {[...groupedStrategies].map(([group, strategies]) => (
            <optgroup key={group} label={group}>
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

      <label className="field field-wide">
        <span>标的代码</span>
        <input name="symbol" defaultValue="US.AAPL" placeholder="US.AAPL" required />
        <small>Futu 代码格式，例如 US.AAPL、HK.00700</small>
      </label>

      <div className="field-pair">
        <label className="field">
          <span>开始日期</span>
          <input type="date" name="start" defaultValue="2024-01-01" required />
        </label>
        <label className="field">
          <span>结束日期</span>
          <input type="date" name="end" defaultValue="2025-12-31" required />
        </label>
      </div>

      <div className="field-pair">
        <label className="field">
          <span>K 线周期</span>
          <select name="ktype" defaultValue="K_DAY">
            {(config?.kline_types ?? ["K_DAY"]).map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>复权方式</span>
          <select name="autype" defaultValue="QFQ">
            <option value="QFQ">前复权 · QFQ</option>
            <option value="HFQ">后复权 · HFQ</option>
            <option value="NONE">不复权 · NONE</option>
          </select>
        </label>
      </div>

      <label className="field field-wide session-field">
        <span>交易时段</span>
        <select name="session" defaultValue="ALL">
          {(config?.session_types ?? ["ALL", "RTH", "ETH"]).map((value) => (
            <option key={value} value={value}>
              {SESSION_LABELS[value] ?? value}
            </option>
          ))}
        </select>
        <small>同时约束 OpenD 历史行情和策略指标，避免时段口径不一致。</small>
      </label>

      <details className="execution-sheet">
        <summary>撮合与资金参数</summary>
        <div className="execution-grid">
          <label className="field"><span>初始资金</span><input type="number" name="initial_cash" defaultValue="100000" min="1" /></label>
          <label className="field" title="前 N 根 K 线只用于建立历史，不触发 handle_data；0 与 Futu 默认生命周期一致"><span>信号预热 K 线</span><input type="number" name="warmup_bars" defaultValue="0" min="0" /></label>
          <label className="field"><span>佣金 · bps</span><input type="number" name="commission_bps" defaultValue="3" min="0" step="0.1" /></label>
          <label className="field"><span>最低佣金</span><input type="number" name="min_commission" defaultValue="1" min="0" step="0.1" /></label>
          <label className="field"><span>滑点 · bps</span><input type="number" name="slippage_bps" defaultValue="5" min="0" step="0.1" /></label>
          <label className="check-field"><input type="checkbox" name="allow_short" /><span>允许做空</span></label>
          <label className="check-field"><input type="checkbox" name="liquidate_on_end" /><span>末根 K 线强制平仓</span></label>
          <label className="check-field"><input type="checkbox" name="refresh_cache" /><span>重新拉取 OpenD 行情</span></label>
        </div>
      </details>

      <div className="run-action">
        <button type="submit" disabled={running || !opendConnected || !selectedStrategy}>
          <span>{running ? "OpenD 回测运行中" : "运行 OpenD 回测"}</span>
          <span aria-hidden="true">↗</span>
        </button>
        <p>只读取历史行情。策略在独立进程中执行，不连接交易账户。</p>
      </div>
    </form>
  );
}
