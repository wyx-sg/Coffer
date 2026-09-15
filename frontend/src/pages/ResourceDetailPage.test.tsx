// frontend/src/pages/ResourceDetailPage.test.tsx
//
// The /mcp-servers/:name route renders the MCP server detail page; the kind is
// fixed — the route carries only the server name.

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
        <Route path="/mcp-servers/:name" element={<ResourceDetailPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("ResourceDetailPage", () => {
  test("renders the MCP server detail page for /mcp-servers/:name", () => {
    render(wrap("/mcp-servers/foo"));
    expect(screen.getByTestId("mcp-detail")).toBeInTheDocument();
  });
});
