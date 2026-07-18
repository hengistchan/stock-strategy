import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { StrategyParameterDefinition } from "../api/types";
import { I18nContext } from "../i18n/I18nContext";
import { translate } from "../i18n/core";
import { StrategyParameterFields } from "./StrategyParameterFields";

const definitions: StrategyParameterDefinition[] = [{
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
}];

describe("StrategyParameterFields", () => {
  it("renders strategy parameter labels and descriptions in English", () => {
    render(
      <I18nContext.Provider value={{
        locale: "en-US",
        setLocale: vi.fn(),
        t: (key, values) => translate("en-US", key, values),
      }}>
        <StrategyParameterFields definitions={definitions} />
      </I18nContext.Provider>,
    );

    expect(screen.getByText("Fast moving-average period")).toBeInTheDocument();
    expect(screen.getByText("Moving-average period used for the fast trend signal.")).toBeInTheDocument();
    expect(screen.queryByText("短均线周期")).not.toBeInTheDocument();
  });
});
