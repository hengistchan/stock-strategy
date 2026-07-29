import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { MonitorAlert, MonitorRule } from "../../api/types";
import { I18nProvider } from "../../i18n/I18nProvider";
import { AlertWorkspace } from "./AlertWorkspace";

const rule: MonitorRule = {
  id: "rule-1",
  name: "AAPL price",
  code: "US.AAPL",
  underlying_code: "US.AAPL",
  instrument_type: "stock",
  metric: "last_price",
  operator: "crosses_above",
  threshold: 220,
  severity: "warning",
  cooldown_seconds: 300,
  daily_trigger_limit: 10,
  session: "regular",
  enabled: true,
  created_at: "2026-07-28T00:00:00Z",
  updated_at: "2026-07-28T00:00:00Z",
};

const alert: MonitorAlert = {
  id: "alert-1",
  dedupe_key: "rule-1:one",
  rule_id: "rule-1",
  rule_name: "AAPL price",
  code: "US.AAPL",
  underlying_code: "US.AAPL",
  triggered_at: "2026-07-28T02:00:00Z",
  acknowledged_at: null,
  severity: "warning",
  metric: "last_price",
  operator: "crosses_above",
  threshold: 220,
  value: 221,
  source: "opend",
  provider_time: "2026-07-28 10:00:00",
  received_at: "2026-07-28T02:00:01Z",
  snapshot: {},
};

function workspace(
  overrides: Partial<React.ComponentProps<typeof AlertWorkspace>> = {},
) {
  return (
    <I18nProvider>
      <AlertWorkspace
        symbol="US.AAPL"
        rules={[rule]}
        alerts={[alert]}
        loading={false}
        unacknowledgedOnly={false}
        busyRuleId={null}
        busyAlertId={null}
        creatingRule={false}
        onUnacknowledgedOnlyChange={vi.fn()}
        onCreateRule={vi.fn()}
        onToggleRule={vi.fn()}
        onDeleteRule={vi.fn()}
        onAcknowledge={vi.fn()}
        {...overrides}
      />
    </I18nProvider>
  );
}

describe("AlertWorkspace", () => {
  it("creates a backend-compatible stock rule payload and exposes rule/alert actions", () => {
    const onCreateRule = vi.fn();
    const onToggleRule = vi.fn();
    const onDeleteRule = vi.fn();
    const onAcknowledge = vi.fn();
    const onFilter = vi.fn();
    render(
      workspace({
        onCreateRule,
        onToggleRule,
        onDeleteRule,
        onAcknowledge,
        onUnacknowledgedOnlyChange: onFilter,
      }),
    );

    const metricSelect = screen.getByRole("combobox", { name: /指标|Metric/ });
    expect(within(metricSelect).getByRole("option", { name: /中间价|Mid Price/ })).toBeInTheDocument();
    expect(within(metricSelect).getByRole("option", { name: /买卖价差率|Bid Ask Spread Pct/ })).toBeInTheDocument();
    expect(within(metricSelect).queryByRole("option", { name: /历史波动率|Historical Volatility/ })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/规则名称|Rule name/), {
      target: { value: "AAPL breakout" },
    });
    fireEvent.change(screen.getByLabelText(/阈值|Threshold/), {
      target: { value: "220" },
    });
    fireEvent.click(screen.getByRole("button", { name: /创建监控规则|Create monitoring rule/ }));

    expect(onCreateRule).toHaveBeenCalledWith({
      name: "AAPL breakout",
      code: "US.AAPL",
      underlying_code: "US.AAPL",
      instrument_type: "stock",
      metric: "last_price",
      operator: "crosses_above",
      threshold: 220,
      severity: "warning",
      cooldown_seconds: 300,
      daily_trigger_limit: 10,
      session: "regular",
      enabled: true,
    });

    fireEvent.click(screen.getByRole("button", { name: /已启用|Enabled/ }));
    expect(onToggleRule).toHaveBeenCalledWith(rule);
    fireEvent.click(screen.getByRole("button", { name: /删除规则 AAPL price|Delete rule AAPL price/ }));
    expect(onDeleteRule).toHaveBeenCalledWith(rule);
    fireEvent.click(screen.getByRole("button", { name: /确认告警|Acknowledge/ }));
    expect(onAcknowledge).toHaveBeenCalledWith(alert);
    fireEvent.click(screen.getByRole("checkbox", { name: /仅未确认|Unacknowledged only/ }));
    expect(onFilter).toHaveBeenCalledWith(true);
  });

  it("scopes an option contract rule to the current underlying", () => {
    const onCreateRule = vi.fn();
    render(workspace({ onCreateRule, rules: [], alerts: [] }));

    fireEvent.change(screen.getByLabelText(/监控对象|Instrument/), {
      target: { value: "option" },
    });
    fireEvent.change(screen.getByLabelText(/规则名称|Rule name/), {
      target: { value: "AAPL call IV" },
    });
    fireEvent.change(screen.getByLabelText(/Futu 代码|Futu code/), {
      target: { value: "US.AAPL260731C100000" },
    });
    fireEvent.change(screen.getByLabelText(/指标|Metric/), {
      target: { value: "option_implied_volatility" },
    });
    fireEvent.change(screen.getByLabelText(/阈值|Threshold/), {
      target: { value: "30" },
    });
    fireEvent.click(
      screen.getByRole("button", {
        name: /创建监控规则|Create monitoring rule/,
      }),
    );

    expect(onCreateRule).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "AAPL call IV",
        code: "US.AAPL260731C100000",
        underlying_code: "US.AAPL",
        instrument_type: "option",
        metric: "option_implied_volatility",
        threshold: 30,
      }),
    );
  });

  it("resets the stock rule code when a keyed workspace changes symbols", () => {
    const common = {
      rules: [] as MonitorRule[],
      alerts: [] as MonitorAlert[],
      loading: false,
      unacknowledgedOnly: false,
      busyRuleId: null,
      busyAlertId: null,
      creatingRule: false,
      onUnacknowledgedOnlyChange: vi.fn(),
      onCreateRule: vi.fn(),
      onToggleRule: vi.fn(),
      onDeleteRule: vi.fn(),
      onAcknowledge: vi.fn(),
    };
    const { rerender } = render(
      <I18nProvider>
        <AlertWorkspace key="US.AAPL" symbol="US.AAPL" {...common} />
      </I18nProvider>,
    );
    expect(screen.getByLabelText(/Futu 代码|Futu code/)).toHaveValue("US.AAPL");

    rerender(
      <I18nProvider>
        <AlertWorkspace key="US.MSFT" symbol="US.MSFT" {...common} />
      </I18nProvider>,
    );
    expect(screen.getByLabelText(/Futu 代码|Futu code/)).toHaveValue("US.MSFT");
  });
});
