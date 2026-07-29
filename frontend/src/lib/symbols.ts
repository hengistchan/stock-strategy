export type SymbolNameMap = Record<string, string>;

const FUTU_SYMBOL_PATTERN = /^[A-Z]{2,8}\.[A-Z0-9.-]{1,24}$/;

export function normalizeFutuSymbol(value: string): string | null {
  const normalized = value.trim().toUpperCase();
  return FUTU_SYMBOL_PATTERN.test(normalized) ? normalized : null;
}

export function formatSymbolLabel(code: string, names: SymbolNameMap): string {
  const name = names[code];
  return name ? `${code} · ${name}` : code;
}
