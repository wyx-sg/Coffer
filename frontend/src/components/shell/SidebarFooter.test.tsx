// src/components/shell/SidebarFooter.test.tsx — the footer's one Settings row with the daemon's state on it, and the update card.
//
// Spec web-ui "Show the daemon's state in the shell footer".
import { afterEach, beforeEach, describe, expect, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";

import i18n from "@/i18n";
import { TooltipProvider } from "@/components/ui/tooltip";
import { acceptance } from "@/test/acceptance";
import { SidebarFooter } from "./SidebarFooter";

const get = vi.fn();
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: () => ({ GET: get }),
}));

// The desktop shell's update record; a browser has none.
const shell = vi.hoisted(() => ({
  inShell: false,
  status: null as null | Record<string, unknown>,
  install: vi.fn(),
  check: vi.fn(),
}));
vi.mock("@/lib/hooks/useShellUpdates", () => ({
  useShellUpdates: () => ({
    inShell: shell.inShell,
    status: shell.status,
    actionError: null,
    check: shell.check,
    install: shell.install,
    setAutoCheck: vi.fn(),
  }),
}));

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

beforeEach(() => {
  shell.inShell = false;
  shell.status = null;
});
afterEach(() => {
  get.mockReset();
  void i18n.changeLanguage("en");
});

describe("SidebarFooter", () => {
  acceptance("web-ui", "the footer shows a running daemon", async () => {
    answer({});
    renderFooter();
    // One row: the Settings entry, the sentence as its name and tooltip.
    const row = await screen.findByRole("button", {
      name: "Settings · Daemon running on port 8000 · v1.0.0",
    });
    expect(screen.getAllByRole("button")).toHaveLength(1);
    // Quiet while all is well: the word Settings and a green dot, no state words, no version.
    expect(row).toHaveTextContent(/^Settings$/);
    expect(row.querySelector("[data-tone]")).toHaveAttribute("data-tone", "ok");
    expect(row).toHaveAttribute("data-daemon", "running");
    fireEvent.focus(row);
    const tip = await screen.findByRole("tooltip");
    expect(tip).toHaveTextContent("Daemon running on port 8000 · v1.0.0");
    fireEvent.click(row);
    expect(screen.getByTestId("where")).toHaveTextContent("/settings/general");
    expect(screen.queryByTestId("version-menu")).not.toBeInTheDocument();
  });

  acceptance("web-ui", "the footer says connecting before the first answer", () => {
    get.mockReturnValue(new Promise(() => {}));
    renderFooter();
    const row = screen.getByTestId("sidebar-settings");
    expect(row).toHaveAttribute("data-daemon", "connecting");
    expect(row.querySelector("[data-tone]")).toHaveAttribute("data-tone", "off");
    expect(row).toHaveTextContent(/^Settings$/);
    fireEvent.click(row);
    expect(screen.getByTestId("where")).toHaveTextContent("/settings/general");
  });

  acceptance("web-ui", "the footer shows an offline daemon", async () => {
    get.mockRejectedValue(new TypeError("Failed to fetch"));
    renderFooter();
    const row = await screen.findByRole("button", { name: "Settings · Daemon offline" });
    // The state in words, in its tone, replaces the quiet dot's silence.
    expect(row).toHaveTextContent("Daemon offline");
    expect(row.querySelector("[data-tone]")).toHaveAttribute("data-tone", "err");
    // A problem lands on the tab that deals with it.
    fireEvent.click(row);
    expect(screen.getByTestId("where")).toHaveTextContent("/settings/daemon");
  });

  acceptance("web-ui", "the footer shows a stopping daemon", async () => {
    answer({ status: "draining" });
    renderFooter();
    const row = await screen.findByRole("button", {
      name: "Settings · Daemon stopping · v1.0.0",
    });
    expect(row).toHaveTextContent("Daemon stopping");
    expect(row.querySelector("[data-tone]")).toHaveAttribute("data-tone", "warn");
    fireEvent.click(row);
    expect(screen.getByTestId("where")).toHaveTextContent("/settings/daemon");
  });

  acceptance("web-ui", "the collapsed rail keeps the daemon state", async () => {
    answer({});
    renderFooter(true);
    const gear = await screen.findByRole("button", {
      name: "Settings · Daemon running on port 8000 · v1.0.0",
    });
    // The gear alone, with the state as a small dot at its corner.
    expect(gear).not.toHaveTextContent("Settings");
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(gear.querySelector("[data-tone]")).toHaveAttribute("data-tone", "ok");
    fireEvent.click(gear);
    expect(screen.getByTestId("where")).toHaveTextContent("/settings/general");
  });

  acceptance(
    "web-ui",
    "a found update shows a dismissible card in the desktop shell only",
    async () => {
      answer({});
      shell.status = {
        phase: "available",
        available: { version: "1.1.0", notes: null, date: null },
      };
      const browser = renderFooter();
      expect(screen.queryByTestId("update-card")).not.toBeInTheDocument();
      browser.unmount();

      shell.inShell = true;
      renderFooter();
      const card = screen.getByTestId("update-card");
      expect(card).toHaveTextContent("v1.1.0");
      fireEvent.click(within(card).getByRole("button", { name: "Restart" }));
      expect(shell.install).toHaveBeenCalledOnce();
      fireEvent.click(within(card).getByRole("button", { name: "Dismiss" }));
      expect(screen.queryByTestId("update-card")).not.toBeInTheDocument();
    },
  );
});
