import { translations, type TranslationKey } from "./translations";

export type Locale = keyof typeof translations;
export type TranslationValues = Record<string, string | number>;

export const LOCALE_STORAGE_KEY = "strategy-lab.locale";

export function translate(locale: Locale, key: TranslationKey, values: TranslationValues = {}): string {
  const template = translations[locale][key] ?? translations["zh-CN"][key];
  return Object.entries(values).reduce(
    (result, [name, value]) => result.replaceAll(`{{${name}}}`, String(value)),
    template,
  );
}

export function detectLocale(): Locale {
  try {
    const saved = window.localStorage?.getItem(LOCALE_STORAGE_KEY);
    if (saved === "zh-CN" || saved === "en-US") return saved;
  } catch {
    // Storage can be unavailable in privacy-restricted contexts.
  }
  return window.navigator.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en-US";
}

export function persistLocale(locale: Locale): void {
  try {
    window.localStorage?.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    // The in-memory locale remains usable when persistence is blocked.
  }
}
