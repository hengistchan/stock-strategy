import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { SymbolSearchField } from "./SymbolSearchField";

afterEach(() => vi.restoreAllMocks());

describe("SymbolSearchField", () => {
  it("searches by name and submits the selected OpenD code", async () => {
    vi.spyOn(api, "symbols").mockResolvedValue({
      query: "苹果",
      symbols: [{ code: "US.AAPL", name: "苹果", market: "US" }],
    });
    const submitted = vi.fn();

    render(
      <form onSubmit={(event) => {
        event.preventDefault();
        submitted(new FormData(event.currentTarget).get("symbol"));
      }}>
        <SymbolSearchField defaultCode="" />
        <button type="submit">submit</button>
      </form>,
    );

    const input = screen.getByRole("combobox", { name: "标的" });
    fireEvent.focus(input);
    fireEvent.change(input, {
      target: { value: "苹果" },
    });
    expect(await screen.findByRole("option", { name: /US\.AAPL.*苹果/ })).toBeVisible();
    fireEvent.click(screen.getByRole("option", { name: /US\.AAPL.*苹果/ }));

    expect(screen.getByRole("combobox", { name: "标的" })).toHaveValue("US.AAPL · 苹果");
    fireEvent.click(screen.getByRole("button", { name: "submit" }));
    expect(submitted).toHaveBeenCalledWith("US.AAPL");
  });

  it("supports arrow-key selection and direct Futu codes", async () => {
    vi.spyOn(api, "symbols").mockResolvedValue({
      query: "腾讯",
      symbols: [
        { code: "HK.00700", name: "腾讯控股", market: "HK" },
        { code: "US.TME", name: "腾讯音乐", market: "US" },
      ],
    });

    render(<SymbolSearchField defaultCode="" />);
    const input = screen.getByRole("combobox", { name: "标的" });
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "腾讯" } });
    await screen.findAllByRole("option");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(input).toHaveValue("US.TME · 腾讯音乐");

    fireEvent.change(input, { target: { value: "hk.00700" } });
    await waitFor(() => expect(document.querySelector('input[name="symbol"]')).toHaveValue("HK.00700"));
  });
});
