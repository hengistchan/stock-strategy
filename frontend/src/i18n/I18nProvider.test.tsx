import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { I18nProvider } from "./I18nProvider";
import { useI18n } from "./I18nContext";
import { LOCALE_STORAGE_KEY, translate } from "./core";

function LanguageProbe() {
  const { locale, setLocale, t } = useI18n();
  return (
    <div>
      <span>{locale}</span>
      <strong>{t("header.backtest")}</strong>
      <button type="button" onClick={() => setLocale(locale === "zh-CN" ? "en-US" : "zh-CN")}>
        switch
      </button>
    </div>
  );
}

describe("I18nProvider", () => {
  const store = new Map<string, string>();

  beforeEach(() => {
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        clear: () => store.clear(),
        getItem: (key: string) => store.get(key) ?? null,
        removeItem: (key: string) => store.delete(key),
        setItem: (key: string, value: string) => store.set(key, value),
      },
    });
    window.localStorage.clear();
    document.documentElement.lang = "zh-CN";
  });

  it("interpolates translated values", () => {
    expect(translate("en-US", "experiment.run", { count: 8 })).toBe(
      "Run 8 parameter sets",
    );
  });

  it("restores, switches, and persists the locale", async () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
    render(<I18nProvider><LanguageProbe /></I18nProvider>);

    expect(screen.getByText("Backtests")).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("en-US");

    fireEvent.click(screen.getByRole("button", { name: "switch" }));

    expect(screen.getByText("回测实验")).toBeInTheDocument();
    await waitFor(() => expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("zh-CN"));
    expect(document.documentElement.lang).toBe("zh-CN");
  });
});
