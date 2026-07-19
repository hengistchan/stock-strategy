import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { queryKeys } from "../api/queryKeys";
import type { SymbolNameMap } from "../lib/symbols";

export function useSymbolNames(codes: string[], enabled = true): SymbolNameMap {
  const normalized = [...new Set(codes.map((code) => code.trim().toUpperCase()).filter(Boolean))].sort();
  const query = useQuery({
    queryKey: queryKeys.symbolNames(normalized),
    queryFn: () => api.resolveSymbols(normalized),
    enabled: enabled && normalized.length > 0,
    staleTime: 5 * 60 * 1_000,
    retry: 1,
  });
  return Object.fromEntries(
    (query.data?.symbols ?? []).map((symbol) => [symbol.code, symbol.name]),
  );
}
