// frontend/src/components/mcp/LegacyMcpServerRedirect.test.tsx
//
// An old `/mcp-servers/mcp_server/:name` link must still land on the server,
// not on "page not found".
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { LegacyMcpServerRedirect } from "./LegacyMcpServerRedirect";

describe("LegacyMcpServerRedirect", () => {
  test("drops the kind segment and keeps the name", () => {
    render(
      <MemoryRouter initialEntries={["/mcp-servers/mcp_server/files"]}>
        <Routes>
          <Route path="/mcp-servers/mcp_server/:name" element={<LegacyMcpServerRedirect />} />
          <Route path="/mcp-servers/:name" element={<div data-testid="detail">detail</div>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByTestId("detail")).toBeInTheDocument();
  });
});
