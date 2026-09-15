// frontend/src/pages/ResourceDetailPage.test.tsx
//
// ResourceDetailPage dispatches on the `:kind` route param: `mcp_server`
// renders the MCP server detail page, anything else shows an "unknown kind"
// card rather than a blank page.

import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { ResourceDetailPage } from "./ResourceDetailPage";

vi.mock("./McpServerDetailPage", () => ({
  McpServerDetailPage: () => <div data-testid="mcp-detail">mcp detail</div>,
}));

function wrap(route: string) {
  return (
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/mcp-servers/:kind/:name" element={<ResourceDetailPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("ResourceDetailPage", () => {
  test("renders the MCP server detail page for the mcp_server kind", () => {
    render(wrap("/mcp-servers/mcp_server/foo"));
    expect(screen.getByTestId("mcp-detail")).toBeInTheDocument();
  });

  test("shows the unknown-kind card for any other kind", () => {
    render(wrap("/mcp-servers/totally_unknown/baz"));
    expect(screen.getByText(/totally_unknown/)).toBeInTheDocument();
    expect(screen.queryByTestId("mcp-detail")).not.toBeInTheDocument();
  });
});
