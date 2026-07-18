import { createContext, useContext } from "react";
import type { TranslationKey } from "./translations";
import { translate, type Locale, type TranslationValues } from "./core";

export interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: TranslationKey, values?: TranslationValues) => string;
}

export const I18nContext = createContext<I18nContextValue>({
  locale: "zh-CN",
  setLocale: () => undefined,
  t: (key, values) => translate("zh-CN", key, values),
});

export function useI18n(): I18nContextValue {
  return useContext(I18nContext);
}
