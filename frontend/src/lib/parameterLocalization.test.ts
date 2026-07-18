import { describe, expect, it } from "vitest";
import type { StrategyParameterDefinition } from "../api/types";
import { localizeParameter } from "./parameterLocalization";

const definition: StrategyParameterDefinition = {
  name: "fast_period",
  label: "短均线周期",
  label_i18n: { "en-US": "Fast moving-average period" },
  description: "用于产生快速趋势信号的移动平均周期。",
  description_i18n: {
    "en-US": "Moving-average period used for the fast trend signal.",
  },
  type: "int",
  default: 20,
  min: 2,
  max: 120,
  candidates: [10, 20],
};

describe("localizeParameter", () => {
  it("uses strategy-provided English parameter copy", () => {
    expect(localizeParameter(definition, "en-US")).toEqual({
      label: "Fast moving-average period",
      description: "Moving-average period used for the fast trend signal.",
    });
  });

  it("falls back to the strategy's base copy", () => {
    expect(localizeParameter(definition, "zh-CN")).toEqual({
      label: "短均线周期",
      description: "用于产生快速趋势信号的移动平均周期。",
    });
  });
});
