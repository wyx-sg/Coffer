// frontend/src/router.test.tsx
// The real route table under a memory router: where the index lands, and that
// legacy bookmarks resolve to a live surface instead of "page not found".
// (A memory router rather than a data router: react-router's data-router
// navigation builds a fetch Request, and jsdom's AbortSignal is not the one
// undici's Request accepts.)
import { beforeEach, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation, useRoutes } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import { routes } from "@/router";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
const { getApiClient } = await import("@/lib/api/client");

/** Every GET answers an empty, well-formed body; the calls are recorded. */
function mockApi() {
  const get = vi.fn().mockImplementation(() =>
    Promise.resolve({
      data: {
        resources: [],
        agents: [],
        candidates: [],
        entries: [],
        status: "ready",
        version: "0.0.0",
        port: 1,
        started_at: "2026-01-01T00:00:00Z",
      },
      error: undefined,
    }),
  );
  vi.mocked(getApiClient).mockReturnValue({ GET: get } as unknown as ReturnType<
    typeof getApiClient
  >);
  return get;
}

function renderAt(path: string) {
  const location = { pathname: "" };
  function Probe() {
    location.pathname = useLocation().pathname;
    return null;
  }
  function AppRoutes() {
    return useRoutes(routes);
  }
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
        <Probe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return location;
}

beforeEach(() => {
  vi.clearAllMocks();
});

acceptance("web-ui", "the index opens the Agents page", async () => {
  const get = mockApi();
  const location = renderAt("/");

  await waitFor(() => expect(location.pathname).toBe("/agents"));
  expect(await screen.findByRole("heading", { level: 1, name: "Agents" })).toBeInTheDocument();
  expect(screen.queryByText(/page not found/i)).not.toBeInTheDocument();

  // The MCP servers surface asks the daemon for MCP servers only.
  get.mockClear();
  const mcp = renderAt("/mcp-servers");
  await waitFor(() => expect(mcp.pathname).toBe("/mcp-servers"));
  await waitFor(() =>
    expect(get).toHaveBeenCalledWith("/resources", { params: { query: { kind: "mcp_server" } } }),
  );
  const resourceQueries = get.mock.calls.filter((call) => call[0] === "/resources");
  for (const call of resourceQueries) {
    expect(call[1]).toEqual({ params: { query: { kind: "mcp_server" } } });
  }
});

acceptance("web-ui", "legacy resource paths redirect instead of 404ing", async () => {
  mockApi();
  const location = renderAt("/resources");

  await waitFor(() => expect(location.pathname).toBe("/mcp-servers"));
  expect(screen.queryByText(/page not found/i)).not.toBeInTheDocument();
});
