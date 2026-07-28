import {
  useEffect,
  useId,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import type { MonitoredInstrument, SymbolMatch } from "../../api/types";
import { useI18n } from "../../i18n/I18nContext";
import { workspacePaths } from "../../lib/workspaceRoutes";
import {
  formatMonitorPrice,
  formatQuoteTimestamp,
} from "./formatters";

interface WatchlistRailProps {
  activeSymbol: string | null;
  instruments: readonly MonitoredInstrument[];
  opendConnected: boolean | null;
  busyCode: string | null;
  adding: boolean;
  onAdd: (symbol: SymbolMatch) => void;
  onToggle: (instrument: MonitoredInstrument) => void;
  onDelete: (instrument: MonitoredInstrument) => void;
}

const FUTU_CODE = /^[A-Za-z]{2,3}\.[A-Za-z0-9.-]+$/;

export function WatchlistRail({
  activeSymbol,
  instruments,
  opendConnected,
  busyCode,
  adding,
  onAdd,
  onToggle,
  onDelete,
}: WatchlistRailProps) {
  const { locale, t } = useI18n();
  const inputId = useId();
  const listId = `${inputId}-results`;
  const inputRef = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState("");
  const [selected, setSelected] = useState<SymbolMatch | null>(null);
  const [results, setResults] = useState<SymbolMatch[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const query = value.trim();
    if (query.length === 0 || selected || opendConnected === false) {
      return;
    }
    let current = true;
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setFailed(false);
      try {
        const response = await api.symbols(query, 8);
        if (!current) return;
        setResults(response.symbols);
        setActiveIndex(0);
      } catch {
        if (!current) return;
        setFailed(true);
        setResults([]);
      } finally {
        if (current) setLoading(false);
      }
    }, 180);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [opendConnected, selected, value]);

  const showResults = open && value.trim().length > 0;

  function choose(symbol: SymbolMatch) {
    setSelected(symbol);
    setValue(`${symbol.code} · ${symbol.name}`);
    setResults([]);
    setOpen(false);
    setLoading(false);
    inputRef.current?.setCustomValidity("");
  }

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    setValue(event.currentTarget.value);
    setSelected(null);
    setOpen(true);
    setFailed(false);
    setLoading(event.currentTarget.value.trim().length > 0);
    event.currentTarget.setCustomValidity("");
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      setOpen(false);
      return;
    }
    if (!showResults || results.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => (index + 1) % results.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => (index - 1 + results.length) % results.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      choose(results[activeIndex]);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const directCode = FUTU_CODE.test(value.trim())
      ? value.trim().toUpperCase()
      : "";
    const candidate = selected ?? (
      directCode
        ? { code: directCode, name: directCode, market: directCode.split(".", 1)[0] }
        : null
    );
    if (!candidate) {
      inputRef.current?.setCustomValidity(t("monitor.watchlistInvalid"));
      inputRef.current?.reportValidity();
      return;
    }
    onAdd(candidate);
    setValue("");
    setSelected(null);
    setResults([]);
    setLoading(false);
  }

  return (
    <aside className="monitor-watchlist" aria-labelledby="monitorWatchlistTitle">
      <header className="monitor-watchlist-heading">
        <p className="section-code">WATCH / 01</p>
        <h2 id="monitorWatchlistTitle">{t("monitor.title")}</h2>
        <p>{t("monitor.intro")}</p>
      </header>

      <form className="monitor-watchlist-search" onSubmit={submit}>
        <label htmlFor={inputId}>{t("monitor.addSymbol")}</label>
        <div className="monitor-watchlist-search-control">
          <input
            ref={inputRef}
            id={inputId}
            role="combobox"
            autoComplete="off"
            aria-autocomplete="list"
            aria-controls={listId}
            aria-expanded={showResults}
            aria-activedescendant={
              showResults && results.length > 0
                ? `${listId}-${activeIndex}`
                : undefined
            }
            value={value}
            placeholder={t("monitor.searchPlaceholder")}
            disabled={opendConnected === false || adding}
            onChange={handleChange}
            onFocus={() => {
              if (value.trim()) setOpen(true);
            }}
            onBlur={() => window.setTimeout(() => setOpen(false), 0)}
            onKeyDown={handleKeyDown}
          />
          <button
            type="submit"
            disabled={opendConnected === false || adding}
            aria-label={t("monitor.addSymbol")}
          >
            {adding ? "…" : "+"}
          </button>
          {showResults ? (
            <div
              id={listId}
              className="monitor-symbol-results"
              role="listbox"
              aria-label={t("monitor.searchResults")}
            >
              {loading ? (
                <p>{t("monitor.searching")}</p>
              ) : null}
              {!loading && failed ? (
                <p className="negative">{t("monitor.searchFailed")}</p>
              ) : null}
              {!loading && !failed && results.length === 0 ? (
                <p>{t("monitor.searchEmpty")}</p>
              ) : null}
              {!loading && !failed
                ? results.map((symbol, index) => (
                    <button
                      key={symbol.code}
                      id={`${listId}-${index}`}
                      type="button"
                      role="option"
                      aria-selected={index === activeIndex}
                      onMouseDown={(event) => event.preventDefault()}
                      onMouseEnter={() => setActiveIndex(index)}
                      onClick={() => choose(symbol)}
                    >
                      <span>
                        <strong>{symbol.code}</strong>
                        <small>{symbol.market}</small>
                      </span>
                      <em>{symbol.name}</em>
                    </button>
                  ))
                : null}
            </div>
          ) : null}
        </div>
        <small>
          {opendConnected === false
            ? t("monitor.searchOffline")
            : t("monitor.searchHelp")}
        </small>
      </form>

      <div className="monitor-watchlist-label">
        <span>{t("monitor.watchlist")}</span>
        <strong>{instruments.length}</strong>
      </div>
      {instruments.length === 0 ? (
        <p className="monitor-watchlist-empty">{t("monitor.watchlistEmpty")}</p>
      ) : (
        <ul className="monitor-watchlist-list">
          {instruments.map((instrument) => {
            const active = instrument.code === activeSymbol;
            return (
              <li
                key={instrument.code}
                data-active={active}
                data-enabled={instrument.enabled}
              >
                <Link
                  to={workspacePaths.monitorSymbol(instrument.code)}
                  aria-current={active ? "page" : undefined}
                >
                  <span className="monitor-watchlist-primary">
                    <span
                      className={`monitor-status-dot ${instrument.freshness ?? "unavailable"}`}
                      aria-hidden="true"
                    />
                    <span>
                      <strong>{instrument.code}</strong>
                      <small>{instrument.name}</small>
                    </span>
                  </span>
                  <span className="monitor-watchlist-quote">
                    <strong>
                      {formatMonitorPrice(instrument.snapshot?.last_price, locale)}
                    </strong>
                    <time>
                      {formatQuoteTimestamp(instrument.snapshot?.source_time)}
                    </time>
                  </span>
                </Link>
                <div className="monitor-watchlist-actions">
                  <button
                    type="button"
                    aria-pressed={instrument.enabled}
                    aria-label={t(
                      instrument.enabled
                        ? "monitor.disableSymbol"
                        : "monitor.enableSymbol",
                      { code: instrument.code },
                    )}
                    disabled={busyCode === instrument.code}
                    onClick={() => onToggle(instrument)}
                  >
                    {instrument.enabled ? "ON" : "OFF"}
                  </button>
                  <button
                    type="button"
                    className="negative"
                    aria-label={t("monitor.removeSymbol", {
                      code: instrument.code,
                    })}
                    disabled={busyCode === instrument.code}
                    onClick={() => onDelete(instrument)}
                  >
                    ×
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
