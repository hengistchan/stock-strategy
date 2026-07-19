export type SymbolNameMap = Record<string, string>;

export function formatSymbolLabel(code: string, names: SymbolNameMap): string {
  const name = names[code];
  return name ? `${code} · ${name}` : code;
}
