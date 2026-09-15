// frontend/src/pages/ResourceDetailPage.test.tsx
//
// Tests the kind-dispatch shim: ResourceDetailPage looks `mcp_server` up in
// the kindRegistry and either renders that kind's DetailPage, redirects to
// /mcp-servers when the kind has no detail page, or shows an "unknown kind"
// state when nothing is registered. The kind is fixed — the route carries only
// the server name.

import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { ResourceDetailPage } from "./ResourceDetailPage";
import { _resetKindRegistry, registerKindUI } from "@/lib/components/kindRegistry";

function FakeCard() {
  return <div data-testid="fake-card">card</div>;
}

function FakeDetail({ name }: { name: string }) {
  return <div data-testid="fake-detail">detail: {name}</div>;
}

function wrap(route: string) {
  return (
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/mcp-servers/:name" element={<ResourceDetailPage />} />
        <Route path="/mcp-servers" element={<div data-testid="resources-page">resources</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("ResourceDetailPage", () => {
  beforeEach(() => {
    _resetKindRegistry();
  });
  afterEach(() => {
    _resetKindRegistry();
  });

  test("renders the mcp_server DetailPage with the name from the URL", () => {
    registerKindUI({
      name: "mcp_server",
      displayName: "MCP Server",
      Card: FakeCard,
      DetailPage: FakeDetail,
    });
    render(wrap("/mcp-servers/foo"));
    expect(screen.getByTestId("fake-detail")).toHaveTextContent("detail: foo");
  });

  test("redirects to /mcp-servers when the kind has no DetailPage", () => {
    registerKindUI({
      name: "mcp_server",
      displayName: "MCP Server",
      Card: FakeCard,
    });
    render(wrap("/mcp-servers/bar"));
    expect(screen.getByTestId("resources-page")).toBeInTheDocument();
  });

  test("shows the unknown-kind state when nothing is registered", () => {
    render(wrap("/mcp-servers/baz"));
    expect(screen.getByText(/mcp_server/)).toBeInTheDocument();
  });
});
