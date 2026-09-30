// frontend/src/components/mcp/invocationsTabs.test.tsx
// The server's tabs: the path names the open one, and each tab carries its
// count (none for a kind the server has none of). What the Invocations tab
// reads is pinned in InvocationsTable.test.tsx.
import { expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { McpServerDetailTabs } from "./McpServerDetailTabs";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/mcp-servers/:name/:tab?"
          element={
            <McpServerDetailTabs
              basePath="/mcp-servers/srv"
              counts={{ tools: 26, resources: 0, prompts: 3 }}
              overview={<p>overview pane</p>}
              tools={<p>tools pane</p>}
              resources={<p>resources pane</p>}
              prompts={<p>prompts pane</p>}
              invocations={<p>invocations pane</p>}
            />
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

test("the Invocations tab in the path shows the invocations pane", () => {
  renderAt("/mcp-servers/srv/invocations");
  expect(screen.getByText("invocations pane")).toBeInTheDocument();
  expect(screen.queryByText("overview pane")).not.toBeInTheDocument();
});

test("each tab carries its count, and none for a kind the server has none of", () => {
  renderAt("/mcp-servers/srv");
  expect(screen.getByRole("tab", { name: "Tools" })).toHaveTextContent("Tools· 26");
  expect(screen.getByRole("tab", { name: "Resources" })).toHaveTextContent(/^Resources$/);
  expect(screen.getByRole("tab", { name: "Prompts" })).toHaveTextContent("· 3");
  expect(screen.getByText("overview pane")).toBeInTheDocument();
});
