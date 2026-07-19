import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { Header } from "./Header";

describe("Header", () => {
  afterEach(() => vi.unstubAllGlobals());

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

  it("loads detailed readiness checks when the OpenD status is opened", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      headers: { get: () => "application/json" },
      json: async () => ({
        ready: false,
        host: "127.0.0.1",
        port: 11111,
        checks: [
          { id: "python", status: "pass", detail: "Python 3.12.1", hint: null },
          { id: "opend", status: "fail", detail: "OpenD is unreachable", hint: "Start OpenD" },
        ],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <Header
          health={{ status: "ok", opend: { connected: false, host: "127.0.0.1", port: 11111 } }}
        />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: /OpenD 未连接/ }));

    await waitFor(() => expect(screen.getByText("Python 3.12.1")).toBeInTheDocument());
    expect(screen.getByRole("region", { name: "系统诊断" })).toHaveTextContent("OpenD is unreachable");
    expect(screen.getByText("需要处理以下问题")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/diagnostics", expect.any(Object));
  });
});
