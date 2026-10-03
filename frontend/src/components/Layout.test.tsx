// src/components/Layout.test.tsx — the shell's rail: skip link, collapse,
// narrow-viewport icon rail, the collapsed language popover, the resizable
// sidebar, the palette shortcut and the Settings shortcut.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import indexHtml from "../../index.html?raw";
import { Layout } from "./Layout";
import { requestPalette } from "./shell/paletteRequest";

const chrome = vi.hoisted(() => ({ overlay: false }));
vi.mock("@/lib/windowChrome", () => ({ overlayTitleBar: () => chrome.overlay }));
vi.mock("./DaemonOfflineBanner", () => ({
  DaemonStatusBar: () => null,
  DaemonOfflineState: () => null,
}));
// Tested where it lives; here it would only put an approvals poll behind every
// shell assertion.
vi.mock("./secret/PendingApprovalsSheet", () => ({ PendingApprovalsSheet: () => null }));
// The palette has its own tests; here it only has to open.
vi.mock("./palette/CommandPalette", () => ({
  CommandPalette: ({ open }: { open: boolean }) =>
    open ? <div data-testid="palette-open" /> : null,
}));
// The footer reads the daemon's status probe; an unanswered probe is enough
// here (the footer's states are tested in shell/SidebarFooter.test.tsx).
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: () => ({ GET: () => new Promise(() => {}) }),
}));

function installMatchMedia(matches: boolean) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn(() => ({
      matches,
      addEventListener: () => {},
      removeEventListener: () => {},
    })),
  });
}

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>;
}

const PAGES = [{ path: "*", element: <div>page body</div> }];
const SETTINGS = [{ path: "settings/:tab", element: <div data-testid="settings-modal" /> }];

function renderShell(path: string | { pathname: string; state?: unknown } = "/agents/codex") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="*" element={<Layout pageRoutes={PAGES} settingsRoutes={SETTINGS} />} />
        </Routes>
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  chrome.overlay = false;
});
afterEach(() => {
  delete (window as unknown as { matchMedia?: unknown }).matchMedia;
});

describe("Layout", () => {
  test("the browser keeps the brand link and its own toggle, with no drag strip", () => {
    renderShell();
    expect(
      within(screen.getByTestId("sidebar")).getByRole("link", { name: /coffer/i }),
    ).toHaveAttribute("href", "/");
    expect(
      within(screen.getByTestId("sidebar")).getByRole("button", { name: /hide sidebar/i }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("window-drag-region")).toBeNull();
  });

  test("the overlay shell has one toggle, in the title strip, the same in both states", () => {
    chrome.overlay = true;
    renderShell();
    const strip = screen.getByTestId("window-drag-region");
    expect(strip).toHaveAttribute("data-tauri-drag-region");
    // The page scrolls below the strip, so no header sits under it.
    expect(screen.getByTestId("page-scroll").className).toContain("var(--titlebar-inset)");
    // No brand row: the sidebar starts under the strip, at the search.
    const side = screen.getByTestId("sidebar");
    expect(side.className).toContain("var(--titlebar-inset)");
    expect(within(side).queryByRole("link", { name: /coffer/i })).toBeNull();
    expect(within(side).queryByText("Coffer")).toBeNull();
    expect(
      within(screen.getByTestId("sidebar")).queryByRole("button", { name: /sidebar/i }),
    ).toBeNull();
    const toggle = within(strip).getByRole("button", { name: /hide sidebar/i });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(toggle).toHaveAttribute("aria-controls", "sidebar");
    fireEvent.click(toggle);
    expect(localStorage.getItem("coffer.nav.collapsed")).toBe("1");
    const again = within(screen.getByTestId("window-drag-region")).getByRole("button", {
      name: /show sidebar/i,
    });
    expect(again).toHaveAttribute("aria-expanded", "false");
    expect(
      within(screen.getByTestId("sidebar")).queryByRole("button", { name: /sidebar/i }),
    ).toBeNull();
  });

  test("Cmd/Ctrl+\\ toggles the sidebar, and the arrows only the overlay shell", () => {
    chrome.overlay = true;
    renderShell();
    expect(screen.getByTestId("title-sidebar-edge")).toBeInTheDocument();
    const press = (key: string) => {
      fireEvent.keyDown(window, { key, metaKey: true });
      fireEvent.keyDown(window, { key, ctrlKey: true });
    };
    press("\\");
    expect(localStorage.getItem("coffer.nav.collapsed")).toBe("1");
    // Collapsed, the strip runs across with no edge line.
    expect(screen.queryByTestId("title-sidebar-edge")).toBeNull();
    press("\\");
    expect(localStorage.getItem("coffer.nav.collapsed")).toBe("0");
    // The old shortcut does nothing.
    press("b");
    expect(localStorage.getItem("coffer.nav.collapsed")).toBe("0");
  });

  test("the browser has no back and forward arrows", () => {
    renderShell();
    expect(screen.queryByRole("button", { name: /^back$/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^forward$/i })).toBeNull();
  });

  test("the skip link is the first focusable element and targets main", () => {
    renderShell();
    const skip = screen.getByRole("link", { name: /skip to content/i });
    expect(skip).toHaveAttribute("href", "#main");
    expect(screen.getByRole("main")).toHaveAttribute("id", "main");
    // Nothing focusable precedes it.
    const links = screen.getAllByRole("link");
    expect(links[0]).toBe(skip);
  });

  test("a detail route keeps its list entry highlighted", () => {
    renderShell("/agents/codex");
    expect(screen.getByRole("link", { name: "Agents" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Skills" })).not.toHaveAttribute("aria-current");
    // Overview is the index: it marks itself only.
    expect(screen.getByRole("link", { name: "Overview" })).not.toHaveAttribute("aria-current");
  });

  test("collapsing hides labels, keeps the brand mark, and keeps expand at the top of the rail", () => {
    renderShell();
    expect(screen.getByText("Coffer")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /hide sidebar/i }));
    expect(localStorage.getItem("coffer.nav.collapsed")).toBe("1");
    expect(screen.queryByText("Coffer")).not.toBeInTheDocument();
    // Brand mark still links home.
    expect(screen.getByRole("link", { name: "Coffer" })).toHaveAttribute("href", "/");
    // Rows keep an accessible name without visible text.
    expect(screen.getByRole("link", { name: "Agents" })).toBeInTheDocument();
    // The expand control stays at the top, in the brand row under the mark,
    // and the footer holds no second one.
    const rail = within(screen.getByTestId("sidebar"));
    const names = rail.getAllByRole("button").map((b) => b.getAttribute("aria-label"));
    expect(names.filter((n) => n === "Show sidebar")).toHaveLength(1);
    expect(names.indexOf("Show sidebar")).toBeLessThan(
      names.findIndex((n) => n?.startsWith("Settings")),
    );
    fireEvent.click(rail.getByRole("button", { name: "Show sidebar" }));
    expect(localStorage.getItem("coffer.nav.collapsed")).toBe("0");
    // Theme and language live in the version menu, not in the sidebar.
    expect(screen.queryByRole("button", { name: /^language$/i })).not.toBeInTheDocument();
  });

  test("below md the rail is always the icon rail with no expand toggle", () => {
    installMatchMedia(false);
    renderShell();
    expect(screen.queryByText("Coffer")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /sidebar/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Agents" })).toBeInTheDocument();
  });

  test("the Settings row opens the modal over the page and is active only while it is open", () => {
    renderShell("/mcp-servers");
    const row = screen.getByRole("button", { name: /^Settings/ });
    expect(row).toHaveAttribute("aria-pressed", "false");
    // Settings is a footer row, not one of the navigation entries.
    const nav = screen.getByRole("navigation", { name: /primary/i });
    expect(nav.textContent).not.toMatch(/Settings/);

    fireEvent.click(row);
    expect(screen.getByTestId("where")).toHaveTextContent("/settings/general");
    expect(screen.getByTestId("settings-modal")).toBeInTheDocument();
    // The page underneath stays rendered.
    expect(screen.getByText("page body")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Settings/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  acceptance("web-ui", "the keyboard shortcut opens Settings", () => {
    renderShell("/activity");
    const input = document.createElement("input");
    document.body.appendChild(input);
    fireEvent.keyDown(input, { key: ",", ctrlKey: true });
    fireEvent.keyDown(input, { key: ",", metaKey: true });
    expect(screen.getByTestId("where")).toHaveTextContent("/activity");
    input.remove();

    fireEvent.keyDown(window, { key: ",", ctrlKey: true });
    fireEvent.keyDown(window, { key: ",", metaKey: true });
    expect(screen.getByTestId("where")).toHaveTextContent("/settings/general");
    expect(screen.getByTestId("settings-modal")).toBeInTheDocument();
    expect(screen.getByText("page body")).toBeInTheDocument();
  });

  test("⌘K / Ctrl+K and the sidebar search control open the palette", () => {
    renderShell();
    expect(screen.queryByTestId("palette-open")).not.toBeInTheDocument();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    // One of the two is this platform's shortcut; it toggled the palette open.
    const openedByKey = screen.queryByTestId("palette-open") !== null;
    if (!openedByKey) fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(screen.getByTestId("palette-open")).toBeInTheDocument();
  });

  test("the sidebar search control opens the palette", () => {
    renderShell();
    fireEvent.click(screen.getByTestId("sidebar-search"));
    expect(screen.getByTestId("palette-open")).toBeInTheDocument();
  });

  test("a page can ask for the palette (the 404's Search Coffer)", () => {
    renderShell();
    act(() => requestPalette());
    expect(screen.getByTestId("palette-open")).toBeInTheDocument();
  });

  acceptance("web-ui", "a divider moves from the keyboard", () => {
    const first = renderShell();
    const divider = screen.getByRole("separator", { name: "Resize the sidebar" });
    expect(divider).toHaveAttribute("aria-valuenow", "220");
    fireEvent.keyDown(divider, { key: "ArrowRight" });
    fireEvent.keyDown(divider, { key: "ArrowRight" });
    fireEvent.keyDown(divider, { key: "ArrowRight" });
    fireEvent.keyDown(divider, { key: "ArrowLeft" });
    expect(divider).toHaveAttribute("aria-valuenow", "252");
    expect(screen.getByTestId("sidebar")).toHaveStyle({ width: "252px" });
    for (let i = 0; i < 10; i++) fireEvent.keyDown(divider, { key: "ArrowRight" });
    expect(divider).toHaveAttribute("aria-valuenow", "300");
    first.unmount();

    renderShell();
    expect(screen.getByRole("separator", { name: "Resize the sidebar" })).toHaveAttribute(
      "aria-valuenow",
      "300",
    );
    // Double-click restores the default.
    fireEvent.doubleClick(screen.getByRole("separator", { name: "Resize the sidebar" }));
    expect(screen.getByTestId("sidebar")).toHaveStyle({ width: "220px" });
  });

  test("collapsing keeps the rail at its own width and drops the divider", () => {
    renderShell();
    fireEvent.click(screen.getByRole("button", { name: /hide sidebar/i }));
    expect(screen.queryByRole("separator", { name: "Resize the sidebar" })).not.toBeInTheDocument();
    // The collapsed rail keeps Settings as a gear with an accessible name.
    expect(screen.getByRole("button", { name: /^Settings/ })).toBeInTheDocument();
  });
});

acceptance("web-ui", "the collapsed sidebar stays collapsed after a reload", () => {
  const first = renderShell();
  expect(screen.getByText("Coffer")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /hide sidebar/i }));
  first.unmount();

  // A fresh mount reads the remembered choice: it opens as the icon rail.
  const second = renderShell();
  expect(screen.queryByText("Coffer")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Agents" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /show sidebar/i }));
  second.unmount();

  // Expanding is remembered the same way.
  renderShell();
  expect(screen.getByText("Coffer")).toBeInTheDocument();
});

acceptance("web-ui", "the sidebar carries the Coffer mark", () => {
  // Expanded: the mark with the wordmark, inside the home link.
  const expanded = renderShell();
  const home = screen.getByText("Coffer").closest("a");
  expect(home).toHaveAttribute("href", "/");
  expect(home?.querySelector("[data-coffer-mark]")).not.toBeNull();
  expect(home).toHaveAccessibleName("Coffer");
  fireEvent.click(screen.getByRole("button", { name: /hide sidebar/i }));
  expanded.unmount();

  // Collapsed: the mark alone, still labelled "Coffer".
  renderShell();
  const rail = screen.getByRole("link", { name: "Coffer" });
  expect(rail.querySelector("[data-coffer-mark]")).not.toBeNull();

  // The document declares the Coffer mark as its icon.
  const doc = new DOMParser().parseFromString(indexHtml, "text/html");
  const icon = doc.querySelector('link[rel="icon"]');
  expect(icon?.getAttribute("href")).toBe("/favicon.svg");
  expect(icon?.getAttribute("type")).toBe("image/svg+xml");
});
