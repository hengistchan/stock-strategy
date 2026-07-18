import type { StrategyParameterDefinition } from "../api/types";
import type { Locale } from "../i18n/core";

export interface ParameterCopy {
  label: string;
  description: string;
}

export function localizeParameter(
  definition: StrategyParameterDefinition,
  locale: Locale,
): ParameterCopy {
  return {
    label: definition.label_i18n?.[locale] ?? definition.label,
    description: definition.description_i18n?.[locale] ?? definition.description,
  };
}
