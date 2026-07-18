export function shortDate(value: string | null | undefined): string {
  return String(value || "—").slice(0, 10);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatNumber(value: number, digits = 2): string {
  return new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function formatCurrency(value: number): string {
  return formatNumber(value, 2);
}

export function formatSignedPercent(value: number): string {
  return `${value > 0 ? "+" : ""}${formatNumber(value, 2)}%`;
}

export function formatSignedCurrency(value: number): string {
  return `${value > 0 ? "+" : ""}${formatCurrency(value)}`;
}

export function formatPrice(value: number): string {
  const digits = Math.abs(value) < 1 ? 4 : 2;
  return formatNumber(value, digits);
}

export function formatCompactVolume(value: number): string {
  return new Intl.NumberFormat("zh-CN", {
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(value);
}

export function isIntradayKline(ktype: string): boolean {
  return [
    "K_1M",
    "K_3M",
    "K_5M",
    "K_10M",
    "K_15M",
    "K_30M",
    "K_60M",
    "K_120M",
    "K_180M",
    "K_240M",
  ].includes(ktype);
}

export function marketTimeKey(value: string): string {
  return value.replace("T", " ").slice(0, 19);
}

export function formatMarketTimestamp(value: string, ktype: string): string {
  const timestamp = marketTimeKey(value);
  if (!timestamp) return "—";
  return isIntradayKline(ktype) ? timestamp.slice(0, 16) : timestamp.slice(0, 10);
}
