// src/components/Layout.test.tsx — the shell's rail: skip link, collapse,
// narrow-viewport icon rail, the collapsed language popover, the resizable
// sidebar, the palette shortcut and the Settings shortcut.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import indexHtml from "../../index.html?raw";
import { Layout } from "./Layout";

vi.mock("./DaemonOfflineBanner", () => ({ DaemonOfflineBanner: () => null }));
// The palette has its own tests; here it only has to open.
vi.mock("./palette/CommandPalette", () => ({
  CommandPalette: ({ open }: { open: boolean }) =>
    open ? <div data-testid="palette-open" /> : null,
}));
// The footer reads the daemon's status probe; an unanswered probe is enough
// here (the footer's states are tested in shell/SidebarFooter.test.tsx).
vi.mock("@/lib/api/client", () => ({
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

function renderShell(path = "/agents/codex") {
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

beforeEach(() => localStorage.clear());
afterEach(() => {
  delete (window as unknown as { matchMedia?: unknown }).matchMedia;
});

describe("Layout", () => {
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
    expect(screen.getByRole("link", { name: "Model providers" })).not.toHaveAttribute(
      "aria-current",
    );
    // Overview is the index: it marks itself only.
    expect(screen.getByRole("link", { name: "Overview" })).not.toHaveAttribute("aria-current");
  });

  test("collapsing hides labels, keeps the brand mark, and folds language into a popover", () => {
    renderShell();
    expect(screen.getByText("Coffer")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /collapse sidebar/i }));
    expect(localStorage.getItem("coffer.nav.collapsed")).toBe("1");
    expect(screen.queryByText("Coffer")).not.toBeInTheDocument();
    // Brand mark still links home.
    expect(screen.getByRole("link", { name: "Coffer" })).toHaveAttribute("href", "/");
    // Rows keep an accessible name without visible text.
    expect(screen.getByRole("link", { name: "Agents" })).toBeInTheDocument();
    // The language switcher is reachable through the globe popover.
    expect(screen.queryByRole("group", { name: /language/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^language$/i }));
    expect(screen.getByRole("group", { name: /language/i })).toBeInTheDocument();
  });

  test("below md the rail is always the icon rail with no expand toggle", () => {
    installMatchMedia(false);
    renderShell();
    expect(screen.queryByText("Coffer")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /sidebar/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Agents" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^language$/i })).toBeInTheDocument();
  });

  // revise-web-ui-ia: web-ui "the Settings row opens Settings over the current page"
  test("the Settings row opens the modal over the page and is active only while it is open", () => {
    renderShell("/mcp-servers");
    const row = screen.getByRole("button", { name: "Settings" });
    expect(row).toHaveAttribute("aria-pressed", "false");
    // Settings is a footer row, not one of the navigation entries.
    const nav = screen.getByRole("navigation", { name: /primary/i });
    expect(nav.textContent).not.toMatch(/Settings/);

    fireEvent.click(row);
    expect(screen.getByTestId("where")).toHaveTextContent("/settings/general");
    expect(screen.getByTestId("settings-modal")).toBeInTheDocument();
    // The page underneath stays rendered.
    expect(screen.getByText("page body")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Settings" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  // revise-web-ui-ia: web-ui "the keyboard shortcut opens Settings"
  test("⌘, / Ctrl+, opens Settings on General, but not while typing", () => {
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

  // revise-web-ui-ia: web-ui "a divider moves from the keyboard"
  test("the sidebar is resized from its divider, within 200–300px, and remembered", () => {
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
    fireEvent.click(screen.getByRole("button", { name: /collapse sidebar/i }));
    expect(screen.queryByRole("separator", { name: "Resize the sidebar" })).not.toBeInTheDocument();
    // The collapsed rail keeps Settings as a gear with an accessible name.
    expect(screen.getByRole("button", { name: "Settings" })).toBeInTheDocument();
  });
});

acceptance("web-ui", "the collapsed sidebar stays collapsed after a reload", () => {
  const first = renderShell();
  expect(screen.getByText("Coffer")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /collapse sidebar/i }));
  first.unmount();

  // A fresh mount reads the remembered choice: it opens as the icon rail.
  const second = renderShell();
  expect(screen.queryByText("Coffer")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Agents" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /expand sidebar/i }));
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
  fireEvent.click(screen.getByRole("button", { name: /collapse sidebar/i }));
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
