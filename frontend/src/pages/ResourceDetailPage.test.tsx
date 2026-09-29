// frontend/src/pages/ResourceDetailPage.test.tsx
//
// The /mcp-servers/:name route renders the MCP server detail page. The kind is
// fixed by the surface rather than read off the URL, and a name is unique
// within its kind, so there is nothing left for a kind segment to disambiguate.

import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { ResourceDetailPage } from "./ResourceDetailPage";

vi.mock("./McpServerDetailPage", () => ({
  McpServerDetailPage: () => <div data-testid="mcp-detail">mcp</div>,
}));

function wrap(route: string) {
  return (
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/mcp-servers/:name/:tab?" element={<ResourceDetailPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("ResourceDetailPage", () => {
  test("renders the MCP server detail page for /mcp-servers/:name", () => {
    render(wrap("/mcp-servers/fs"));
    expect(screen.getByTestId("mcp-detail")).toBeInTheDocument();
  });
});
