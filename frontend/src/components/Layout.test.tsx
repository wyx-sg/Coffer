// src/components/Layout.test.tsx — the shell's rail: skip link, collapse,
// narrow-viewport icon rail, and the collapsed language popover.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import { Layout } from "./Layout";

vi.mock("./DaemonOfflineBanner", () => ({ DaemonOfflineBanner: () => null }));
// Both floating banners are tested where they live; here they would only put a
// live /sync/status fetch behind every shell assertion.
vi.mock("./SyncAttentionBanner", () => ({ SyncAttentionBanner: () => null }));

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

function renderShell(path = "/agents/codex") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<Layout />}>
            <Route path="*" element={<div>page body</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => localStorage.removeItem("coffer.nav.collapsed"));
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
    expect(screen.getByRole("link", { name: "Chat" })).not.toHaveAttribute("aria-current");
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
