import type { ParameterValue, StrategyParameterDefinition } from "../api/types";

export function readParameterValues(
  data: FormData,
  definitions: StrategyParameterDefinition[],
  namePrefix = "parameter",
): Record<string, ParameterValue> {
  return Object.fromEntries(
    definitions.map((definition) => {
      const raw = data.get(`${namePrefix}:${definition.name}`);
      if (definition.type === "bool") return [definition.name, raw === "on"];
      if (definition.type === "int") return [definition.name, Number.parseInt(String(raw), 10)];
      if (definition.type === "float") return [definition.name, Number.parseFloat(String(raw))];
      return [definition.name, String(raw ?? "")];
    }),
  );
}
