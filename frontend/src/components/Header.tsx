import type { HealthResponse } from "../api/types";

export type WorkspaceMode = "backtest" | "iterate" | "strategies";

interface HeaderProps {
  health?: HealthResponse;
  mode: WorkspaceMode;
  onModeChange: (mode: WorkspaceMode) => void;
}

export function Header({ health, mode, onModeChange }: HeaderProps) {
  const connected = health?.opend.connected === true;
  return (
    <header className="app-header">
      <div className="brand-lockup">
        <div className="brand-index" aria-hidden="true">SL/02</div>
        <div>
          <p className="eyebrow">OpenD quantitative workbench</p>
          <h1>Strategy Lab</h1>
        </div>
      </div>

      <nav className="workspace-tabs" aria-label="工作区">
        <button
          type="button"
          aria-current={mode === "backtest" ? "page" : undefined}
          onClick={() => onModeChange("backtest")}
        >
          回测实验
          <small>RUN &amp; REVIEW</small>
        </button>
        <button
          type="button"
          aria-current={mode === "iterate" ? "page" : undefined}
          onClick={() => onModeChange("iterate")}
        >
          参数实验
          <small>SEARCH &amp; COMPARE</small>
        </button>
        <button
          type="button"
          aria-current={mode === "strategies" ? "page" : undefined}
          onClick={() => onModeChange("strategies")}
        >
          策略文件
          <small>EDIT &amp; SAVE</small>
        </button>
      </nav>

      <div className="connection-badge" data-state={connected ? "connected" : "offline"}>
        <span className="status-dot" aria-hidden="true" />
        <span>{connected ? "OpenD 已连接" : "OpenD 未连接"}</span>
        <small>{health ? `${health.opend.host}:${health.opend.port}` : "正在检查服务"}</small>
      </div>
    </header>
  );
}
