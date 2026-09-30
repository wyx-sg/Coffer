// src/components/shell/SidebarFooter.test.tsx — the footer's daemon state and the Settings row.
//
// These cover change revise-web-ui-ia's footer scenarios (spec web-ui "Show
// the daemon's state in the shell footer"); they carry plain tests until the
// change is archived, when its task 7.7 gives them their markers.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { SidebarFooter } from "./SidebarFooter";

const get = vi.fn();
vi.mock("@/lib/api/client", () => ({ getApiClient: () => ({ GET: get }) }));

function answer(body: Record<string, unknown>) {
  get.mockResolvedValue({
    data: {
      status: "ready",
      version: "1.0.0",
      port: 8000,
      started_at: "2026-09-30T00:00:00Z",
      ...body,
    },
    error: undefined,
  });
}

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>;
}

function renderFooter(collapsed = false) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/mcp-servers"]}>
        <TooltipProvider>
          <SidebarFooter collapsed={collapsed} />
        </TooltipProvider>
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => get.mockReset());

describe("SidebarFooter", () => {
  // revise-web-ui-ia: web-ui "the footer shows a running daemon"
  test("a running daemon reads as running on its port, and opens Settings → Daemon", async () => {
    answer({});
    renderFooter();
    const state = await screen.findByRole("button", { name: "Daemon running on port 8000" });
    expect(state).toHaveTextContent("Running on port 8000");
    // The running version, written the way the design shows it.
    expect(within(state).getByTestId("sidebar-version")).toHaveTextContent("v1.0.0");
    fireEvent.click(state);
    expect(screen.getByTestId("where")).toHaveTextContent("/settings/daemon");
  });

  // revise-web-ui-ia: web-ui "the footer says connecting before the first answer"
  test("before the first answer it reads as connecting", () => {
    get.mockReturnValue(new Promise(() => {}));
    renderFooter();
    expect(screen.getByTestId("sidebar-daemon")).toHaveTextContent("Connecting to the daemon…");
    expect(screen.getByTestId("sidebar-daemon")).toHaveAttribute("data-state", "connecting");
  });

  // revise-web-ui-ia: web-ui "the footer shows an offline daemon"
  test("an unreachable daemon reads as offline and still opens Settings → Daemon", async () => {
    get.mockRejectedValue(new TypeError("Failed to fetch"));
    renderFooter();
    const state = await screen.findByRole("button", { name: "Daemon offline" });
    fireEvent.click(state);
    expect(screen.getByTestId("where")).toHaveTextContent("/settings/daemon");
  });

  // revise-web-ui-ia: web-ui "the footer shows a stopping daemon"
  test("a draining daemon reads as stopping", async () => {
    answer({ status: "draining" });
    renderFooter();
    expect(await screen.findByRole("button", { name: "Daemon stopping" })).toBeInTheDocument();
  });

  // revise-web-ui-ia: web-ui "the collapsed rail keeps the daemon state"
  test("the collapsed rail keeps the state as an icon with the same words", async () => {
    answer({});
    renderFooter(true);
    const state = await screen.findByRole("button", { name: "Daemon running on port 8000" });
    expect(state).not.toHaveTextContent("Daemon running");
    expect(screen.queryByTestId("sidebar-version")).toBeNull();
    // revise-web-ui-ia: web-ui "the collapsed rail keeps Settings as a gear with a tooltip"
    const gear = screen.getByRole("button", { name: "Settings" });
    expect(gear).not.toHaveTextContent("Settings");
    fireEvent.click(gear);
    expect(screen.getByTestId("where")).toHaveTextContent("/settings/general");
  });
});
