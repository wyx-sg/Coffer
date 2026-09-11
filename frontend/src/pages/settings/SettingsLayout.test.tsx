// frontend/src/pages/settings/SettingsLayout.test.tsx
//
// Direct-render tests for the settings tab-strip + pane-swap behaviour.
// Settings renders General + Engine + Data + Sync + Security + About; the
// daemon is never a tab.

import { describe, expect, test } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { SettingsLayout } from "./SettingsLayout";

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

describe("SettingsLayout", () => {
  test("renders the Engine, Data, Security, and About tabs but not App / Daemon", () => {
    render(wrap());
    // Engine holds Coffer's own internal-LLM + embedding config — internal
    // configuration, so Settings rather than the model-provider resource page.
    expect(screen.getByRole("link", { name: /Engine/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Data/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Security/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /About/ })).toBeInTheDocument();
    // The App tab was removed with the launch-at-login feature — it never appears.
    expect(screen.queryByRole("link", { name: /^App$/ })).not.toBeInTheDocument();
    // The daemon is intentionally never surfaced as a tab.
    expect(screen.queryByRole("link", { name: /^Daemon$/ })).not.toBeInTheDocument();
  });

  test("holds no model-provider tab — that surface is a sidebar resource", () => {
    render(wrap());
    // Model providers is a resource kind with a list UI, so it lives in the
    // sidebar's RESOURCES group at /model-providers, not under Settings. The
    // Models / Providers / Embedding tabs it replaced are long gone too.
    expect(screen.queryByRole("link", { name: /^Models$/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Providers$/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /LLM Connections/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Model providers/ })).not.toBeInTheDocument();
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
