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

// revise-web-ui-ia: web-ui "the index opens Overview" — the marker moves to
// that scenario when the change is archived (its task 7.2).
acceptance("web-ui", "the index opens the Agents page", async () => {
  const get = mockApi();
  const location = renderAt("/");

  // Overview renders in place at `/`, with no redirect, and is marked current.
  expect(
    await screen.findByRole("heading", { level: 1, name: "Overview" }, { timeout: 5_000 }),
  ).toBeInTheDocument();
  expect(location.pathname).toBe("/");
  expect(screen.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
  expect(screen.queryByText(/page not found/i)).not.toBeInTheDocument();

  // /agents still opens the Agents page.
  renderAt("/agents");
  expect(await screen.findByRole("heading", { level: 1, name: "Agents" })).toBeInTheDocument();

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

test("the old Chat addresses open Conversations", async () => {
  mockApi();
  const list = renderAt("/chat");
  await waitFor(() => expect(list.pathname).toBe("/conversations"));
  const one = renderAt("/chat/conv-1");
  await waitFor(() => expect(one.pathname).toBe("/conversations/conv-1"));
});

test("the old Settings addresses land on a live tab", async () => {
  mockApi();
  for (const [from, to] of [
    ["/settings", "/settings/general"],
    ["/settings/engine", "/settings/general"],
    ["/settings/embedding", "/settings/general"],
    ["/settings/nope", "/settings/general"],
    ["/settings/llm-connections", "/model-providers"],
    ["/settings/sync", "/sync"],
  ] as const) {
    const location = renderAt(from);
    await waitFor(() => expect(location.pathname).toBe(to));
  }
});

test("every page the shell adds resolves to a page of its own", async () => {
  mockApi();
  for (const path of ["/custom-tools", "/clis", "/secrets", "/usage"]) {
    renderAt(path);
  }
  // Each page is code-split, so they arrive one by one.
  await waitFor(() => expect(screen.getAllByTestId("placeholder-page")).toHaveLength(4), {
    timeout: 5_000,
  });
  expect(screen.queryByText(/page not found/i)).not.toBeInTheDocument();
});
