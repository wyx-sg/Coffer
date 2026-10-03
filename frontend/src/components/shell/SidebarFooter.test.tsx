// src/components/shell/SidebarFooter.test.tsx — the footer's one Settings row (no daemon state on it) and the update card.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
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
  test("the Settings row carries no daemon state and opens General", () => {
    renderFooter();
    const row = screen.getByTestId("sidebar-settings");
    expect(row).toHaveTextContent(/^Settings$/);
    expect(row).toHaveAccessibleName("Settings");
    expect(row.querySelector("[data-tone]")).toBeNull();
    fireEvent.click(row);
    expect(screen.getByTestId("where")).toHaveTextContent("/settings/general");
  });

  test("the collapsed gear's tooltip reads Settings and its shortcut; the labelled row has none", async () => {
    answer({});
    const expanded = renderFooter();
    fireEvent.focus(screen.getByTestId("sidebar-settings"));
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    expanded.unmount();
    renderFooter(true);
    fireEvent.focus(screen.getByTestId("sidebar-settings"));
    expect(await screen.findByRole("tooltip")).toHaveTextContent(/^Settings\s+\S/);
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
