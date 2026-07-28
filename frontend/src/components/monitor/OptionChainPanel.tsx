import { useMemo, useState } from "react";
import type {
  OptionChainResponse,
  OptionExpiration,
} from "../../api/types";
import { useI18n } from "../../i18n/I18nContext";
import {
  formatMonitorInteger,
  formatMonitorPrice,
  formatMonitorRatio,
  formatOptionIv,
} from "./formatters";
import {
  buildOptionChain,
  type OptionChainContract,
  type OptionMoneyness,
} from "./optionChain";
import { classifyMonitorError } from "./monitorError";
import { MonitorStatePanel } from "./MonitorStatePanel";

interface OptionChainPanelProps {
  symbol: string;
  expirations: readonly OptionExpiration[];
  expiration: string | null;
  data?: OptionChainResponse;
  expirationsLoading: boolean;
  chainLoading: boolean;
  error: unknown;
  onExpirationChange: (expiration: string) => void;
  onOpenContract: (contractCode: string) => void;
  onRetry: () => void;
}

type MoneynessFilter = "all" | Lowercase<OptionMoneyness>;

export function OptionChainPanel({
  symbol,
  expirations,
  expiration,
  data,
  expirationsLoading,
  chainLoading,
  error,
  onExpirationChange,
  onOpenContract,
  onRetry,
}: OptionChainPanelProps) {
  const { locale, t } = useI18n();
  const [filter, setFilter] = useState<MoneynessFilter>("all");
  const model = useMemo(
    () =>
      buildOptionChain({
        contracts: data?.contracts ?? [],
        snapshots: data?.contracts ?? [],
        underlyingPrice: data?.underlying_snapshot.last_price,
      }),
    [data],
  );
  const rows =
    filter === "all"
      ? model.rows
      : model.rows.filter(
          (row) =>
            row.call?.moneyness.toLowerCase() === filter
            || row.put?.moneyness.toLowerCase() === filter,
        );

  if (error && !data) {
    return (
      <MonitorStatePanel
        state={classifyMonitorError(error)}
        compact
        detail={error instanceof Error ? error.message : null}
        onRetry={onRetry}
      />
    );
  }

  return (
    <section className="option-chain-panel monitor-panel" aria-labelledby="optionChainTitle">
      <header className="monitor-panel-heading option-chain-heading">
        <div>
          <p className="section-code">DERIVATIVES / OPEND</p>
          <h2 id="optionChainTitle">{t("monitor.optionChain")}</h2>
          <p>{t("monitor.optionChainIntro", { symbol })}</p>
        </div>
        <div className="option-chain-controls">
          <label>
            <span>{t("monitor.expiration")}</span>
            <select
              value={expiration ?? ""}
              disabled={expirationsLoading || expirations.length === 0}
              onChange={(event) => onExpirationChange(event.currentTarget.value)}
            >
              {expiration === null ? (
                <option value="">{t("monitor.selectExpiration")}</option>
              ) : null}
              {expirations.map((item) => (
                <option key={item.expiration} value={item.expiration}>
                  {item.expiration}
                  {item.days_to_expiry == null
                    ? ""
                    : ` · ${t("monitor.dteShort", { count: item.days_to_expiry })}`}
                  {item.cycle ? ` · ${item.cycle}` : ""}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>{t("monitor.moneyness")}</span>
            <select
              value={filter}
              onChange={(event) =>
                setFilter(event.currentTarget.value as MoneynessFilter)}
            >
              <option value="all">{t("monitor.filterAll")}</option>
              <option value="atm">ATM</option>
              <option value="itm">ITM</option>
              <option value="otm">OTM</option>
            </select>
          </label>
        </div>
      </header>

      <div className="option-chain-summary">
        <article>
          <small>{t("monitor.underlyingPrice")}</small>
          <strong>
            {formatMonitorPrice(data?.underlying_snapshot.last_price, locale)}
          </strong>
        </article>
        <article>
          <small>{t("monitor.atmStrike")}</small>
          <strong>{formatMonitorPrice(model.atmStrike, locale)}</strong>
        </article>
        <article>
          <small>{t("monitor.callPutVolume")}</small>
          <strong>
            {formatMonitorRatio(model.summary.callPutVolumeRatio, locale)}
          </strong>
        </article>
        <article>
          <small>{t("monitor.callPutOiDaily")}</small>
          <strong>
            {formatMonitorRatio(model.summary.callPutOpenInterestRatio, locale)}
          </strong>
        </article>
      </div>

      {expirationsLoading && expirations.length === 0 ? (
        <p className="monitor-inline-empty">{t("monitor.expirationsLoading")}</p>
      ) : expirations.length === 0 ? (
        <MonitorStatePanel state="unavailable" compact onRetry={onRetry} />
      ) : chainLoading && !data ? (
        <p className="monitor-inline-empty">{t("monitor.chainLoading")}</p>
      ) : rows.length === 0 ? (
        <p className="monitor-inline-empty">{t("monitor.chainEmpty")}</p>
      ) : (
        <div className="option-chain-table-wrap">
          <table className="option-chain-table">
            <caption>{t("monitor.chainCaption", { symbol, expiration: expiration ?? "—" })}</caption>
            <thead>
              <tr className="option-chain-side-row">
                <th colSpan={6} scope="colgroup">CALL</th>
                <th scope="col">{t("monitor.strike")}</th>
                <th colSpan={6} scope="colgroup">PUT</th>
              </tr>
              <tr>
                <th>{t("monitor.contract")}</th>
                <th>{t("monitor.last")}</th>
                <th>{t("monitor.bidAsk")}</th>
                <th>IV</th>
                <th>{t("monitor.volume")}</th>
                <th>{t("monitor.openInterestDailyShort")}</th>
                <th>{t("monitor.strike")}</th>
                <th>{t("monitor.contract")}</th>
                <th>{t("monitor.last")}</th>
                <th>{t("monitor.bidAsk")}</th>
                <th>IV</th>
                <th>{t("monitor.volume")}</th>
                <th>{t("monitor.openInterestDailyShort")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.strike} data-atm={row.isAtm}>
                  <ContractCells
                    contract={row.call}
                    locale={locale}
                    openLabel={t("monitor.openContract")}
                    onOpen={onOpenContract}
                  />
                  <th className="option-strike" scope="row">
                    <strong>{formatMonitorPrice(row.strike, locale)}</strong>
                    {row.isAtm ? <span>ATM</span> : null}
                  </th>
                  <ContractCells
                    contract={row.put}
                    locale={locale}
                    openLabel={t("monitor.openContract")}
                    onOpen={onOpenContract}
                  />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {model.rejectedContractCount > 0 || model.duplicateContractCount > 0 ? (
        <p className="option-chain-quality" role="status">
          {t("monitor.chainQuality", {
            rejected: model.rejectedContractCount,
            duplicate: model.duplicateContractCount,
          })}
        </p>
      ) : null}
      <p className="option-chain-cadence">{t("monitor.openInterestCadence")}</p>
      <footer className="option-chain-footer">
        <span>CALL</span>
        <strong>STRIKE</strong>
        <span>PUT</span>
      </footer>
    </section>
  );
}

interface ContractCellsProps {
  contract: OptionChainContract | null;
  locale: "zh-CN" | "en-US";
  openLabel: string;
  onOpen: (contractCode: string) => void;
}

function ContractCells({
  contract,
  locale,
  openLabel,
  onOpen,
}: ContractCellsProps) {
  if (!contract) {
    return (
      <>
        <td>—</td>
        <td>—</td>
        <td>—</td>
        <td>—</td>
        <td>—</td>
        <td>—</td>
      </>
    );
  }
  return (
    <>
      <td>
        <button
          type="button"
          className="option-contract-link"
          title={`${openLabel}: ${contract.code}`}
          aria-label={`${openLabel}: ${contract.code}`}
          onClick={() => onOpen(contract.code)}
        >
          {shortContractCode(contract.code)}
        </button>
        <small data-moneyness={contract.moneyness}>{contract.moneyness}</small>
      </td>
      <td>{formatMonitorPrice(contract.lastPrice, locale)}</td>
      <td>
        {formatMonitorPrice(contract.bidPrice, locale)}
        <span className="option-bid-ask-separator">/</span>
        {formatMonitorPrice(contract.askPrice, locale)}
      </td>
      <td>{formatOptionIv(contract.impliedVolatility, locale)}</td>
      <td>{formatMonitorInteger(contract.volume, locale)}</td>
      <td>{formatMonitorInteger(contract.openInterest, locale)}</td>
    </>
  );
}

function shortContractCode(code: string): string {
  const suffix = code.includes(".") ? code.split(".").at(-1) ?? code : code;
  return suffix.length > 12 ? `…${suffix.slice(-11)}` : suffix;
}
