// frontend/src/pages/settings/SettingsLayout.test.tsx
//
// Direct-render tests for the settings tab-strip + pane-swap behaviour.
// The browser path renders Security + Data + About — the App tab is hidden
// when `isTauri()` returns false, and the daemon is never a tab.

import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { SettingsLayout } from "./SettingsLayout";

// Pretend we're in browser mode so the desktop-only App tab is hidden.
vi.mock("@/lib/tauri", () => ({
  isTauri: () => false,
}));

function wrap(route = "/settings/data") {
  return (
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/settings" element={<SettingsLayout />}>
          <Route path="data" element={<div data-testid="pane-data">data</div>} />
          <Route path="about" element={<div data-testid="pane-about">about</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

describe("SettingsLayout (browser mode)", () => {
  test("renders the Data, Security, and About tabs but not App / Daemon", () => {
    render(wrap());
    expect(screen.getByRole("link", { name: /Data/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Security/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /About/ })).toBeInTheDocument();
    // The desktop-only App tab is hidden in browser mode.
    expect(screen.queryByRole("link", { name: /^App$/ })).not.toBeInTheDocument();
    // The daemon is intentionally never surfaced as a tab.
    expect(screen.queryByRole("link", { name: /^Daemon$/ })).not.toBeInTheDocument();
  });

  test("folds embedding into the Models tab — no standalone Embedding tab", () => {
    render(wrap());
    // The embedding/chunking config now lives under the Models tab, so there
    // is no longer a separate Embedding nav item.
    expect(screen.queryByRole("link", { name: /Embedding & chunking/ })).not.toBeInTheDocument();
    // The Models tab label reflects the merged concerns.
    expect(screen.getByRole("link", { name: /Models & Embedding/ })).toBeInTheDocument();
  });

  test("renders the active pane and swaps content when another tab is clicked", () => {
    render(wrap("/settings/data"));
    expect(screen.getByTestId("pane-data")).toBeInTheDocument();
    expect(screen.queryByTestId("pane-about")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: /About/ }));
    expect(screen.getByTestId("pane-about")).toBeInTheDocument();
    expect(screen.queryByTestId("pane-data")).not.toBeInTheDocument();
  });

  test("renders the layout heading and subtitle", () => {
    render(wrap());
    // The h1 is always present — guards against the layout collapsing
    // to an outlet-only render.
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
  });
});

describe("SettingsLayout (desktop mode)", () => {
  test("includes the App tab when isTauri() returns true", async () => {
    vi.resetModules();
    vi.doMock("@/lib/tauri", () => ({ isTauri: () => true }));
    const { SettingsLayout: DesktopLayout } = await import("./SettingsLayout");

    render(
      <MemoryRouter initialEntries={["/settings/data"]}>
        <Routes>
          <Route path="/settings" element={<DesktopLayout />}>
            <Route path="data" element={<div>data</div>} />
            <Route path="security" element={<div>security</div>} />
            <Route path="app" element={<div>app</div>} />
            <Route path="about" element={<div>about</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    // The App tab appears in addition to Data + Security + About.
    expect(screen.getByRole("link", { name: /^App$/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Data$/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Security$/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^About$/ })).toBeInTheDocument();
  });
});
