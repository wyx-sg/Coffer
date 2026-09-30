// frontend/src/components/mcp/invocationsTabs.test.tsx
// A server's Invocations tab mounts InvocationsTable scoped to its uid. (What
// the table then reads, and how Activity's MCP calls tab reads the same log
// unscoped, is pinned in InvocationsTable.test.tsx.)
import { expect, test, vi } from "vitest";
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { McpServerDetailTabs } from "./McpServerDetailTabs";

const mounted = vi.fn();
vi.mock("./InvocationsTable", () => ({
  InvocationsTable: (props: { serverUid?: string; enabled?: boolean }) => {
    mounted(props);
    return <div>invocation table</div>;
  },
}));
vi.mock("./CapabilityList", () => ({ CapabilityList: () => null }));
vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn(() => ({ GET: vi.fn() })) }));

function renderAt(path: string, ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

test("a server's Invocations tab mounts the invocation table scoped to its uid", () => {
  renderAt(
    "/mcp-servers/srv/invocations",
    <Routes>
      <Route
        path="/mcp-servers/:name/:tab?"
        element={
          <McpServerDetailTabs
            serverUid="u-1"
            basePath="/mcp-servers/srv"
            capabilities={undefined}
            overview={null}
            tools={null}
          />
        }
      />
    </Routes>,
  );
  expect(mounted).toHaveBeenCalled();
  expect(mounted.mock.lastCall![0]).toEqual({ serverUid: "u-1" });
});
