// src/components/shell/SidebarFooter.test.tsx — the footer's daemon state, the version menu, the update card and the Settings row.
//
// These cover change revise-web-ui-ia's footer scenarios (spec web-ui "Show
// the daemon's state in the shell footer"); they carry plain tests until the
// change is archived, when its task 7.7 gives them their markers.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";

import i18n from "@/i18n";
import { TooltipProvider } from "@/components/ui/tooltip";
import { acceptance } from "@/test/acceptance";
import { SidebarFooter } from "./SidebarFooter";

const get = vi.fn();
vi.mock("@/lib/api/client", () => ({ getApiClient: () => ({ GET: get }) }));

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

/** Open the version menu from the footer row, and open its head (Settings › Daemon). */
function openDaemonTab(row: HTMLElement) {
  fireEvent.click(row);
  const menu = screen.getByTestId("version-menu");
  fireEvent.click(within(menu).getAllByRole("button")[0]);
}

describe("SidebarFooter", () => {
  // revise-web-ui-ia: web-ui "the footer shows a running daemon"
  test("a running daemon reads as running on its port, and its menu opens Settings → Daemon", async () => {
    answer({});
    renderFooter();
    const state = await screen.findByRole("button", {
      name: "Daemon running on port 8000 · v1.0.0",
    });
    expect(state).toHaveTextContent("Daemon running");
    expect(state).toHaveTextContent("v1.0.0");
    fireEvent.click(state);
    const menu = screen.getByTestId("version-menu");
    expect(menu).toHaveTextContent("Coffer v1.0.0");
    expect(menu).toHaveTextContent("Daemon on127.0.0.1:8000");
    fireEvent.click(within(menu).getAllByRole("button")[0]);
    expect(screen.getByTestId("where")).toHaveTextContent("/settings/daemon");
  });

  // revise-web-ui-ia: web-ui "the footer says connecting before the first answer"
  test("before the first answer it reads as connecting", () => {
    get.mockReturnValue(new Promise(() => {}));
    renderFooter();
    expect(screen.getByTestId("sidebar-daemon")).toHaveTextContent("Connecting to the daemon…");
    expect(screen.getByTestId("sidebar-daemon")).toHaveAttribute("data-daemon", "connecting");
  });

  // revise-web-ui-ia: web-ui "the footer shows an offline daemon"
  test("an unreachable daemon reads as offline and still opens Settings → Daemon", async () => {
    get.mockRejectedValue(new TypeError("Failed to fetch"));
    renderFooter();
    const state = await screen.findByRole("button", { name: "Daemon offline" });
    openDaemonTab(state);
    expect(screen.getByTestId("where")).toHaveTextContent("/settings/daemon");
  });

  // revise-web-ui-ia: web-ui "the footer shows a stopping daemon"
  test("a draining daemon reads as stopping", async () => {
    answer({ status: "draining" });
    renderFooter();
    expect(
      await screen.findByRole("button", { name: "Daemon stopping · v1.0.0" }),
    ).toBeInTheDocument();
  });

  // revise-web-ui-ia: web-ui "the collapsed rail keeps the daemon state"
  test("the collapsed rail keeps the state as an icon with the same words", async () => {
    answer({});
    renderFooter(true);
    const state = await screen.findByRole("button", {
      name: "Daemon running on port 8000 · v1.0.0",
    });
    expect(state).not.toHaveTextContent("Daemon running");
    // revise-web-ui-ia: web-ui "the collapsed rail keeps Settings as a gear with a tooltip"
    const gear = screen.getByRole("button", { name: "Settings" });
    expect(gear).not.toHaveTextContent("Settings");
    fireEvent.click(gear);
    expect(screen.getByTestId("where")).toHaveTextContent("/settings/general");
  });

  test("the version menu switches the language at once and names each locale in its own language", async () => {
    answer({});
    renderFooter();
    fireEvent.click(await screen.findByRole("button", { name: /Daemon running/ }));
    const languages = within(screen.getByTestId("version-menu")).getByRole("radiogroup", {
      name: "Language",
    });
    const zh = within(languages).getByRole("radio", { name: /简体中文/ });
    expect(zh).toHaveAttribute("lang", "zh-Hans");
    await act(async () => {
      fireEvent.click(zh);
    });
    expect(i18n.language).toBe("zh");
    expect(zh).toHaveAttribute("aria-checked", "true");
  });

  test("the version menu links the documentation and sends Check for updates to Settings › About", async () => {
    answer({});
    renderFooter();
    fireEvent.click(await screen.findByRole("button", { name: /Daemon running/ }));
    const menu = within(screen.getByTestId("version-menu"));
    expect(menu.getByRole("link", { name: "Documentation" })).toHaveAttribute(
      "href",
      "https://wyx-sg.github.io/Coffer/",
    );
    fireEvent.click(menu.getByRole("button", { name: "Check for updates" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/settings/about");
    // A browser has no shell to ask; About says so.
    expect(shell.check).not.toHaveBeenCalled();
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
