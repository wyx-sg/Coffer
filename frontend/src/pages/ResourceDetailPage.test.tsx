// frontend/src/pages/ResourceDetailPage.test.tsx
//
// The /mcp-servers/:uid route renders the MCP server detail page. The kind is
// fixed by the surface rather than read off the URL, and with a uid in the path
// there is nothing left for a kind segment to disambiguate.

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
        <Route path="/mcp-servers/:uid" element={<ResourceDetailPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("ResourceDetailPage", () => {
  test("renders the MCP server detail page for /mcp-servers/:uid", () => {
    render(wrap("/mcp-servers/u-filesystem"));
    expect(screen.getByTestId("mcp-detail")).toBeInTheDocument();
  });
});
