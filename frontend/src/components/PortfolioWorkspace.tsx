import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { queryKeys } from "../api/queryKeys";
import type { PortfolioRequest } from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import {
  formatNumber,
  formatSignedCurrency,
  formatSignedPercent,
} from "../lib/format";
import { normalizeFutuSymbol } from "../lib/symbols";
import { workspacePaths } from "../lib/workspaceRoutes";
import { PerformanceChart } from "./PerformanceChart";

interface PortfolioWorkspaceProps {
  opendConnected: boolean;
  onNotice: (message: string) => void;
}

interface MonitorImportResult {
  firstCode: string;
  total: number;
  added: number;
  reenabled: number;
  existing: number;
}

export function PortfolioWorkspace({
  opendConnected,
  onNotice,
}: PortfolioWorkspaceProps) {
  const { locale, t } = useI18n();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [symbols, setSymbols] = useState("US.AAPL, US.MSFT, US.NVDA");
  const [weights, setWeights] = useState("40, 35, 25");
  const mutation = useMutation({ mutationFn: api.runPortfolio });
  const monitorMutation = useMutation({
    mutationFn: async (rawCodes: readonly string[]): Promise<MonitorImportResult> => {
      const codes = [
        ...new Set(
          rawCodes
            .map((code) => normalizeFutuSymbol(code))
            .filter((code): code is string => Boolean(code)),
        ),
      ];
      if (codes.length === 0) {
        throw new Error(t("portfolio.monitorNoSymbols"));
      }
      const watchlist = await api.watchlist();
      const existingByCode = new Map(
        watchlist.instruments.map((instrument) => [
          instrument.code.toUpperCase(),
          instrument,
        ]),
      );
      let added = 0;
      let reenabled = 0;
      let existing = 0;
      for (const code of codes) {
        const instrument = existingByCode.get(code);
        if (instrument?.enabled) {
          existing += 1;
        } else if (instrument) {
          await api.updateWatchlistItem(code, { enabled: true });
          reenabled += 1;
        } else {
          await api.addWatchlistItem({
            code,
            name: code,
            instrument_type: "stock",
            enabled: true,
          });
          added += 1;
        }
      }
      return {
        firstCode: codes[0]!,
        total: codes.length,
        added,
        reenabled,
        existing,
      };
    },
    onSuccess: (summary) => {
      onNotice(
        t("portfolio.monitorAdded", {
          total: summary.total,
          added: summary.added,
          reenabled: summary.reenabled,
          existing: summary.existing,
        }),
      );
      navigate(workspacePaths.monitorSymbol(summary.firstCode));
    },
    onError: (error) => {
      onNotice(
        error instanceof Error ? error.message : t("portfolio.monitorFailed"),
      );
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.watchlist });
    },
  });
  const result = mutation.data;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const symbolList = parseList(symbols).map((symbol) => symbol.toUpperCase());
    const weightList = parseList(weights).map(Number);
    mutation.mutate({
      weights: Object.fromEntries(
        symbolList.map((symbol, index) => [symbol, weightList[index] ?? 0]),
      ),
      start: String(form.get("start")),
      end: String(form.get("end")),
      initial_cash: Number(form.get("initial_cash")),
      commission_bps: 3,
      min_commission: 1,
      slippage_bps: 5,
      rebalance: String(form.get("rebalance")) as PortfolioRequest["rebalance"],
      ktype: "K_DAY",
      autype: "QFQ",
      session: "ALL",
    });
  }

  const symbolList = parseList(symbols);
  const weightList = parseList(weights).map(Number);
  const valid = symbolList.length >= 2
    && symbolList.length === weightList.length
    && weightList.every((weight) => Number.isFinite(weight) && weight > 0);

  return (
    <main className="portfolio-workspace">
      <aside className="portfolio-control">
        <form onSubmit={submit}>
          <div className="portfolio-intro">
            <span className="section-code">SHARED CAPITAL</span>
            <h2>{t("portfolio.title")}</h2>
            <p>{t("portfolio.intro")}</p>
          </div>
          <label className="field">
            <span>{t("portfolio.symbols")}</span>
            <textarea aria-label={t("portfolio.symbols")} value={symbols} onChange={(event) => setSymbols(event.target.value)} rows={3} />
          </label>
          <label className="field">
            <span>{t("portfolio.weights")}</span>
            <input aria-label={t("portfolio.weights")} value={weights} onChange={(event) => setWeights(event.target.value)} />
            <small>{t("portfolio.weightsHelp")}</small>
          </label>
          <div className="field-pair">
            <label className="field"><span>{t("form.start")}</span><input name="start" type="date" defaultValue="2024-01-01" required /></label>
            <label className="field"><span>{t("form.end")}</span><input name="end" type="date" defaultValue="2025-12-31" required /></label>
          </div>
          <label className="field">
            <span>{t("portfolio.rebalance")}</span>
            <select name="rebalance" defaultValue="monthly">
              <option value="buy_and_hold">{t("portfolio.buyHold")}</option>
              <option value="monthly">{t("portfolio.monthly")}</option>
              <option value="quarterly">{t("portfolio.quarterly")}</option>
            </select>
          </label>
          <label className="field">
            <span>{t("form.initialCash")}</span>
            <input name="initial_cash" type="number" min="1" defaultValue="100000" />
          </label>
          <button className="experiment-run-button" type="submit" disabled={!opendConnected || !valid || mutation.isPending}>
            <span>{mutation.isPending ? t("portfolio.running") : t("portfolio.run")}</span>
            <span aria-hidden="true">→</span>
          </button>
          <p className="experiment-safety">{t("portfolio.scope")}</p>
        </form>
      </aside>
      <section className="portfolio-results" aria-live="polite">
        {!result && !mutation.error ? (
          <div className="experiment-empty">
            <span className="section-code">PORTFOLIO OUTPUT</span>
            <h2>{t("portfolio.emptyTitle")}</h2>
            <p>{t("portfolio.emptyBody")}</p>
          </div>
        ) : null}
        {mutation.error ? <div className="editor-message negative">{mutation.error.message}</div> : null}
        {result ? (
          <>
            <header className="portfolio-result-heading">
              <div><span className="section-code">PORTFOLIO EVIDENCE</span><h2>{result.id}</h2></div>
              <div className="portfolio-result-actions">
                <span>OpenD · {result.period.start} → {result.period.end}</span>
                <button
                  type="button"
                  disabled={monitorMutation.isPending || !opendConnected}
                  onClick={() =>
                    monitorMutation.mutate(Object.keys(result.weights))}
                >
                  {monitorMutation.isPending
                    ? t("portfolio.addingToMonitor")
                    : t("portfolio.addToMonitor", {
                        count: Object.keys(result.weights).length,
                      })}
                </button>
              </div>
            </header>
            <div className="portfolio-metrics">
              <Metric label={t("metrics.return")} value={formatSignedPercent(result.metrics.total_return_pct, locale)} />
              <Metric label="Sharpe" value={formatNumber(result.metrics.sharpe_ratio, 2, locale)} />
              <Metric label={t("metrics.drawdown")} value={formatSignedPercent(result.metrics.max_drawdown_pct, locale)} />
              <Metric label={t("metrics.fees")} value={formatSignedCurrency(result.metrics.total_fees, locale)} />
            </div>
            <PerformanceChart equity={result.equity_curve} equityCount={result.equity_curve.length} trades={[]} ktype="K_DAY" />
            <section className="portfolio-ledger">
              <h3>{t("portfolio.positions")}</h3>
              <table>
                <thead><tr><th>{t("form.symbol")}</th><th>{t("trades.quantity")}</th><th>{t("portfolio.weight")}</th><th>{t("portfolio.marketValue")}</th></tr></thead>
                <tbody>{result.positions.map((position) => (
                  <tr key={position.symbol}>
                    <td>{position.symbol}</td>
                    <td>{formatNumber(position.quantity, 0, locale)}</td>
                    <td>{formatSignedPercent(result.weights[position.symbol] * 100, locale)}</td>
                    <td>{formatNumber(position.market_value, 2, locale)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </section>
          </>
        ) : null}
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <article><small>{label}</small><strong>{value}</strong></article>;
}

function parseList(value: string): string[] {
  return value.split(/[\s,;]+/).map((item) => item.trim()).filter(Boolean);
}
