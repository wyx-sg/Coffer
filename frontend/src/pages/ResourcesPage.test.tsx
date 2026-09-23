// frontend/src/pages/ResourcesPage.test.tsx
//
// The MCP-servers surface. It scopes its query to kind=mcp_server SERVER-SIDE
// rather than fetching every resource and filtering client-side off the shared
// kind registry — the latter silently broadened as `memory`/`knowledge_base`
// registered their own UIs, leaking those stores into this list. We mock the
// data hook + the two heavy MCP children so the test asserts ResourcesPage's
// own branching (skeleton / error / empty-welcome / populated) and, crucially,
// that it requests only mcp_server resources.

import { afterEach, describe, expect, test, vi } from "vitest";
import { acceptance } from "@/test/acceptance";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ResourcesPage } from "./ResourcesPage";
import { ApiError } from "@/lib/api/errors";
import type { ResourceOut } from "@/lib/api/resources";

vi.mock("@/lib/hooks/useResources", () => ({ useResources: vi.fn() }));
vi.mock("@/components/mcp/AddMcpServerDialog", () => ({
  AddMcpServerDialog: () => <button>add mcp server</button>,
}));
vi.mock("@/components/mcp/McpServersTable", () => ({
  McpServersTable: ({
    resources,
    isLoading,
  }: {
    resources: ResourceOut[];
    isLoading?: boolean;
  }) => (
    <div data-testid="mcp-table" data-loading={isLoading ? "true" : "false"}>
      {resources.map((r) => (
        <span key={r.uid}>{r.name}</span>
      ))}
    </div>
  ),
}));

const { useResources } = await import("@/lib/hooks/useResources");
const useResourcesMock = vi.mocked(useResources);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

/** A row carries both halves: the uid it is keyed and addressed by, and the
 *  name the reader sees. */
function resource(uid: string, name: string, kind: string): ResourceOut {
  return { uid, name, kind, config: {} } as unknown as ResourceOut;
}

function stubQuery(opts: { data?: ResourceOut[]; isPending?: boolean; error?: unknown }) {
  useResourcesMock.mockReturnValue({
    data: opts.data,
    isPending: opts.isPending ?? false,
    error: opts.error ?? null,
  } as unknown as ReturnType<typeof useResources>);
}

describe("ResourcesPage", () => {
  afterEach(() => vi.clearAllMocks());

  test("scopes the query to mcp_server (does not list every kind)", () => {
    // The regression guard: kind-filtering is delegated to the backend, so a
    // newly-registered kind (memory, knowledge_base) can never leak in.
    stubQuery({ data: [] });
    render(wrap(<ResourcesPage />));
    expect(useResourcesMock).toHaveBeenCalledWith("mcp_server");
  });

  test("keeps the header up and hands the table isLoading while the query is pending", () => {
    stubQuery({ isPending: true });
    render(wrap(<ResourcesPage />));
    // No bare "Loading…" card: the title stays mounted over a loading table.
    expect(screen.getByRole("heading", { name: /mcp servers/i })).toBeInTheDocument();
    expect(screen.getByTestId("mcp-table")).toHaveAttribute("data-loading", "true");
    expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
  });

  test("shows the error card with the translated message when the query errors", () => {
    stubQuery({ error: new ApiError("BOOM", "kaboom") });
    render(wrap(<ResourcesPage />));
    expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
    expect(screen.getByText(/kaboom/i)).toBeInTheDocument();
  });

  acceptance("web-ui", "a server error never reads as an unexpected error", () => {
    stubQuery({ error: new ApiError("INTERNAL_ERROR", "internal error") });
    const { container } = render(wrap(<ResourcesPage />));
    expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
    // A readable message that says where to look, not a shrug.
    expect(screen.getByText(/activity/i)).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/unexpected error/i);
    expect(container.textContent).not.toContain("INTERNAL_ERROR");
  });

  test("shows the welcome panel (and no table) when there are no servers", () => {
    stubQuery({ data: [] });
    render(wrap(<ResourcesPage />));
    expect(screen.queryByTestId("mcp-table")).not.toBeInTheDocument();
  });

  test("renders the table (with the Add action) for the returned servers", () => {
    stubQuery({
      data: [
        resource("u-srv-a", "srv-a", "mcp_server"),
        resource("u-srv-b", "srv-b", "mcp_server"),
      ],
    });
    render(wrap(<ResourcesPage />));
    expect(screen.getByTestId("mcp-table")).toBeInTheDocument();
    expect(screen.getByText("srv-a")).toBeInTheDocument();
    expect(screen.getByText("srv-b")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /add mcp server/i })).toBeInTheDocument();
  });
});
