// frontend/src/router.test.tsx
// The real route table under a memory router: where the index lands, that
// every page resolves to a live surface, and that an unknown address is
// "page not found".
// (A memory router rather than a data router: react-router's data-router
// navigation builds a fetch Request, and jsdom's AbortSignal is not the one
// undici's Request accepts.)
import { beforeEach, expect, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation, useRoutes } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import { routes } from "@/router";
import { cli } from "@/test/cliFixtures";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: vi.fn(),
}));
const { getApiClient } = await import("@/lib/api/client");

/** Every GET answers an empty, well-formed body; the calls are recorded. */
function mockApi() {
  const get = vi.fn().mockImplementation(() =>
    Promise.resolve({
      data: {
        resources: [],
        // GET /agents/types, /providers, /fs/editors, /secrets/approvals: the
        // pages the table mounts read these through the request modules.
        types: [],
        install_handoff: null,
        providers: [],
        editors: [],
        approvals: [],
        groups: [],
        agents: [],
        candidates: [],
        entries: [],
        // GET /attention — the Overview at `/` reads it.
        items: [],
        errors: [],
        status: "ready",
        version: "0.0.0",
        port: 1,
        started_at: "2026-01-01T00:00:00Z",
        features: {},
        // GET /usage/summary — the Overview's usage tile reads it.
        totals: { input_tokens: 0, output_tokens: 0 },
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

acceptance("web-ui", "the index opens Overview", async () => {
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

test("an address the app does not answer is page not found", async () => {
  mockApi();
  // /usage is gone: Usage is a tab of Model providers (no redirect).
  for (const path of ["/chat", "/resources", "/audit", "/usage"]) {
    const location = renderAt(path);
    expect(await screen.findByText("Nothing lives at this address")).toBeInTheDocument();
    expect(location.pathname).toBe(path);
    cleanup();
  }
});

test("the Settings addresses land on a live tab", async () => {
  mockApi();
  for (const [from, to] of [
    ["/settings", "/settings/general"],
    ["/settings/nope", "/settings/general"],
  ] as const) {
    const location = renderAt(from);
    // The Settings modal is code-split; its first load can take a while.
    await waitFor(() => expect(location.pathname).toBe(to), { timeout: 5_000 });
  }
});

test("every page the shell adds resolves to a page of its own", async () => {
  mockApi();
  for (const path of ["/secrets", "/custom-tools", "/clis"]) {
    const location = renderAt(path);
    // Each page is code-split; wait until it has replaced the fallback.
    await waitFor(() => expect(location.pathname).toBe(path));
    await waitFor(() => expect(screen.getAllByRole("heading").length).toBeGreaterThan(0), {
      timeout: 5_000,
    });
    expect(screen.queryByText(/page not found/i)).not.toBeInTheDocument();
    cleanup();
  }
});

test("the CLIs page and a command's address both resolve to the CLIs page", async () => {
  const get = mockApi();
  const empty = get.getMockImplementation()!;
  get.mockImplementation((path: string) =>
    path === "/clis/{command}"
      ? Promise.resolve({ data: cli({ command: "gh" }), error: undefined })
      : empty(path),
  );
  renderAt("/clis");
  renderAt("/clis/gh");
  await waitFor(() => expect(screen.getByRole("heading", { name: "CLIs" })).toBeInTheDocument(), {
    timeout: 5_000,
  });
  // The detail pane, titled by the command it is addressed by.
  await waitFor(() => expect(screen.getByRole("heading", { name: "gh" })).toBeInTheDocument());
  expect(screen.queryByText(/page not found/i)).not.toBeInTheDocument();
});

test("the Custom tools page and a group's address both resolve to the Custom tools page", async () => {
  mockApi();
  renderAt("/custom-tools");
  renderAt("/custom-tools/billing");
  await waitFor(
    () => expect(screen.getAllByRole("heading", { name: "Custom tools" })).toHaveLength(2),
    { timeout: 5_000 },
  );
  expect(screen.queryByText(/page not found/i)).not.toBeInTheDocument();
});
