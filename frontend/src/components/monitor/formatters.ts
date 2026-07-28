import type { Locale } from "../../i18n/core";

export const MONITOR_MISSING_VALUE = "—";

const MISSING_TEXT = new Set(["", "N/A", "NA", "NAN", "NULL", "NONE", "--", "—"]);

export function formatOptionIv(
  value: unknown,
  locale: Locale = "zh-CN",
  digits = 2,
): string {
  const number = finiteNumber(value);
  return number === null || number < 0
    ? MONITOR_MISSING_VALUE
    : `${formatNumber(number, locale, digits)}%`;
}

export function formatGreek(
  value: unknown,
  locale: Locale = "zh-CN",
  digits = 4,
): string {
  const number = finiteNumber(value);
  return number === null
    ? MONITOR_MISSING_VALUE
    : formatNumber(number, locale, digits);
}

export function formatMonitorPrice(
  value: unknown,
  locale: Locale = "zh-CN",
): string {
  const number = finiteNumber(value);
  if (number === null || number < 0) return MONITOR_MISSING_VALUE;
  return formatNumber(number, locale, Math.abs(number) < 1 ? 4 : 2);
}

export function formatMonitorInteger(
  value: unknown,
  locale: Locale = "zh-CN",
): string {
  const number = finiteNumber(value);
  if (number === null || number < 0) return MONITOR_MISSING_VALUE;
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(number);
}

export function formatMonitorRatio(
  value: unknown,
  locale: Locale = "zh-CN",
  digits = 2,
): string {
  const number = finiteNumber(value);
  return number === null || number < 0
    ? MONITOR_MISSING_VALUE
    : `${formatNumber(number, locale, digits)}×`;
}

/**
 * OpenD source_time is an exchange wall-clock value without a timezone.
 * Preserve that clock instead of passing it through Date and silently shifting it.
 */
export function formatQuoteTimestamp(value: unknown): string {
  const normalized = text(value);
  if (!normalized) return MONITOR_MISSING_VALUE;
  const match =
    /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)?)?$/.exec(
      normalized,
    );
  if (!match) return MONITOR_MISSING_VALUE;
  const [, year, month, day, hour, minute, second] = match;
  if (!validDateParts(year, month, day, hour, minute, second)) {
    return MONITOR_MISSING_VALUE;
  }
  return hour === undefined
    ? `${year}-${month}-${day}`
    : `${year}-${month}-${day} ${hour}:${minute}:${second ?? "00"}`;
}

function formatNumber(number: number, locale: Locale, digits: number): string {
  const safeDigits = Math.max(0, Math.min(8, Math.trunc(digits)));
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: safeDigits,
    maximumFractionDigits: safeDigits,
  }).format(number);
}

function validDateParts(
  year: string,
  month: string,
  day: string,
  hour?: string,
  minute?: string,
  second?: string,
): boolean {
  const yearNumber = Number(year);
  const monthNumber = Number(month);
  const dayNumber = Number(day);
  const date = new Date(Date.UTC(yearNumber, monthNumber - 1, dayNumber));
  if (
    date.getUTCFullYear() !== yearNumber
    || date.getUTCMonth() !== monthNumber - 1
    || date.getUTCDate() !== dayNumber
  ) {
    return false;
  }
  if (hour === undefined) return true;
  const hourNumber = Number(hour);
  const minuteNumber = Number(minute);
  const secondNumber = Number(second ?? "0");
  return (
    hourNumber >= 0
    && hourNumber <= 23
    && minuteNumber >= 0
    && minuteNumber <= 59
    && secondNumber >= 0
    && secondNumber <= 59
  );
}

function text(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const normalized = value.trim();
  return MISSING_TEXT.has(normalized.toUpperCase()) ? null : normalized;
}

function finiteNumber(value: unknown): number | null {
  if (typeof value === "boolean" || value === null || value === undefined) return null;
  if (typeof value === "string" && MISSING_TEXT.has(value.trim().toUpperCase())) {
    return null;
  }
  if (typeof value !== "number" && typeof value !== "string") return null;
  const normalized = Number(value);
  return Number.isFinite(normalized) ? normalized : null;
}
