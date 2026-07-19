import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { Header } from "./Header";

describe("Header", () => {
  it("keeps the OpenD state and language switch in one status cell", () => {
    const { container } = render(
      <MemoryRouter initialEntries={["/experiments"]}>
        <Header
          health={{ status: "ok", opend: { connected: true, host: "127.0.0.1", port: 11111 } }}
        />
      </MemoryRouter>,
    );

    const statusCell = container.querySelector(".system-status-cell");
    expect(statusCell).toContainElement(screen.getByText("OpenD 已连接"));
    expect(statusCell).toContainElement(screen.getByRole("button", { name: "Switch to English" }));
    expect(statusCell).toHaveTextContent("127.0.0.1:11111");
    expect(screen.getByRole("link", { name: /回测实验/ })).toHaveAttribute("href", "/backtests");
    expect(screen.getByRole("link", { name: /参数实验/ })).toHaveAttribute("aria-current", "page");
  });
});
