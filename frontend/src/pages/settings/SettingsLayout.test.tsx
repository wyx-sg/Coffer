// frontend/src/pages/settings/SettingsLayout.test.tsx
//
// Direct-render tests for the settings tab-strip + pane-swap behaviour.
// Settings renders LLM Connections + Data + Security + About; the daemon is
// never a tab.

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
  test("renders the Data, Security, and About tabs but not App / Daemon", () => {
    render(wrap());
    expect(screen.getByRole("link", { name: /Data/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Security/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /About/ })).toBeInTheDocument();
    // The App tab was removed with the launch-at-login feature — it never appears.
    expect(screen.queryByRole("link", { name: /^App$/ })).not.toBeInTheDocument();
    // The daemon is intentionally never surfaced as a tab.
    expect(screen.queryByRole("link", { name: /^Daemon$/ })).not.toBeInTheDocument();
  });

  test("folds Models + Providers + Embedding into one LLM Connections tab", () => {
    render(wrap());
    // The Models and Providers tabs are retired (unified) and the embedding
    // config lives on the LLM Connections page (its own card), so there is no
    // separate Models / Providers / Embedding nav item.
    expect(screen.queryByRole("link", { name: /^Models$/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Providers$/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Embedding/ })).not.toBeInTheDocument();
    // The single unified tab is "LLM Connections".
    expect(screen.getByRole("link", { name: /LLM Connections/ })).toBeInTheDocument();
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
