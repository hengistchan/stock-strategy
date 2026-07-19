import { useEffect, useId, useRef, useState, type ChangeEvent, type KeyboardEvent } from "react";
import { api } from "../api/client";
import type { SymbolMatch } from "../api/types";
import { useI18n } from "../i18n/I18nContext";

const FUTU_SYMBOL = /^[A-Za-z]{2,3}\.[A-Za-z0-9.-]+$/;

interface SymbolSearchFieldProps {
  className?: string;
  defaultCode?: string;
  searchEnabled?: boolean;
}

export function SymbolSearchField({
  className = "",
  defaultCode = "US.AAPL",
  searchEnabled = true,
}: SymbolSearchFieldProps) {
  const { t } = useI18n();
  const inputId = useId();
  const listId = `${inputId}-symbols`;
  const inputRef = useRef<HTMLInputElement>(null);
  const [inputValue, setInputValue] = useState(defaultCode);
  const [selected, setSelected] = useState<SymbolMatch | null>(null);
  const [results, setResults] = useState<SymbolMatch[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const query = inputValue.trim();
    if (!searchEnabled || !query || (selected && inputValue === formatSymbol(selected))) {
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
        const exact = response.symbols.find(
          (item) => item.code.toUpperCase() === query.toUpperCase(),
        );
        if (exact && FUTU_SYMBOL.test(query)) {
          setSelected(exact);
          setInputValue(formatSymbol(exact));
        }
      } catch {
        if (!current) return;
        setResults([]);
        setFailed(true);
      } finally {
        if (current) setLoading(false);
      }
    }, 180);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [inputValue, searchEnabled, selected]);

  const directCode = FUTU_SYMBOL.test(inputValue.trim())
    ? inputValue.trim().toUpperCase()
    : "";
  const submittedCode = selected?.code ?? directCode;
  const showPanel = open && inputValue.trim().length > 0;

  function choose(symbol: SymbolMatch) {
    setSelected(symbol);
    setInputValue(formatSymbol(symbol));
    setOpen(false);
    setResults([]);
    inputRef.current?.setCustomValidity("");
  }

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    event.currentTarget.setCustomValidity("");
    setInputValue(event.currentTarget.value);
    setSelected(null);
    setLoading(true);
    setOpen(true);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!showPanel || results.length === 0) {
      if (event.key === "Escape") setOpen(false);
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((current) => (current + 1) % results.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) => (current - 1 + results.length) % results.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      choose(results[activeIndex]);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div className={`field symbol-search-field ${className}`.trim()}>
      <label className="field-label" htmlFor={inputId}>{t("form.symbol")}</label>
      <div className="symbol-search-control">
        <input
          ref={inputRef}
          id={inputId}
          role="combobox"
          autoComplete="off"
          aria-autocomplete="list"
          aria-controls={listId}
          aria-expanded={showPanel}
          aria-activedescendant={showPanel && results.length > 0 ? `${listId}-${activeIndex}` : undefined}
          value={inputValue}
          placeholder={t("form.symbolPlaceholder")}
          required
          pattern={selected ? undefined : "[A-Za-z]{2,3}\\.[A-Za-z0-9.-]+"}
          onChange={handleChange}
          onFocus={() => {
            if (results.length > 0) setOpen(true);
          }}
          onBlur={() => window.setTimeout(() => setOpen(false), 0)}
          onInvalid={(event) => event.currentTarget.setCustomValidity(t("form.symbolSelectRequired"))}
          onKeyDown={handleKeyDown}
        />
        <input type="hidden" name="symbol" value={submittedCode} />
        <span className="symbol-search-mark" aria-hidden="true">⌕</span>
        {showPanel ? (
          <div className="symbol-search-panel" id={listId} role="listbox" aria-label={t("form.symbolResults")}>
            {loading ? <p className="symbol-search-state">{t("form.symbolSearching")}</p> : null}
            {!loading && failed ? <p className="symbol-search-state negative">{t("form.symbolSearchError")}</p> : null}
            {!loading && !failed && results.length === 0 ? <p className="symbol-search-state">{t("form.symbolNoResults")}</p> : null}
            {!loading && !failed ? results.map((symbol, index) => (
              <button
                id={`${listId}-${index}`}
                key={symbol.code}
                type="button"
                role="option"
                aria-selected={index === activeIndex}
                className="symbol-search-option"
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
            )) : null}
          </div>
        ) : null}
      </div>
      <small>{searchEnabled ? t("form.symbolHelp") : t("form.symbolSearchOffline")}</small>
    </div>
  );
}

function formatSymbol(symbol: SymbolMatch): string {
  return `${symbol.code} · ${symbol.name}`;
}
