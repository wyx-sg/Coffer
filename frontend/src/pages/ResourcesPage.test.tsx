// frontend/src/pages/ResourcesPage.test.tsx
//
// The MCP-servers surface. It scopes its query to kind=mcp_server SERVER-SIDE
// rather than fetching every resource and filtering client-side off the shared
// kind registry — the latter silently broadened as `memory`/`knowledge_base`
// registered their own UIs, leaking those stores into this list. We mock the
// data hook + the two heavy MCP children so the test asserts ResourcesPage's
// own branching (loading / error / empty-welcome / populated) and, crucially,
// that it requests only mcp_server resources.

import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ResourcesPage } from "./ResourcesPage";
import { ApiError } from "@/lib/api/errors";
import type { ResourceOut } from "@/lib/components/kindRegistry";

vi.mock("@/lib/hooks/useResources", () => ({ useResources: vi.fn() }));
vi.mock("@/kinds/mcp/AddMcpServerDialog", () => ({
  AddMcpServerDialog: () => <button>add mcp server</button>,
}));
vi.mock("@/kinds/mcp/McpServersTable", () => ({
  McpServersTable: ({ resources }: { resources: ResourceOut[] }) => (
    <div data-testid="mcp-table">
      {resources.map((r) => (
        <span key={r.name}>{r.name}</span>
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

function resource(name: string, kind: string): ResourceOut {
  return { name, kind, config: {} } as unknown as ResourceOut;
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

  test("shows the loading card while the query is pending", () => {
    stubQuery({ isPending: true });
    render(wrap(<ResourcesPage />));
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
    expect(screen.queryByTestId("mcp-table")).not.toBeInTheDocument();
  });

  test("shows the error card with the translated message when the query errors", () => {
    stubQuery({ error: new ApiError("BOOM", "kaboom") });
    render(wrap(<ResourcesPage />));
    expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
    expect(screen.getByText(/kaboom/i)).toBeInTheDocument();
  });

  test("shows the welcome panel (and no table) when there are no servers", () => {
    stubQuery({ data: [] });
    render(wrap(<ResourcesPage />));
    expect(screen.queryByTestId("mcp-table")).not.toBeInTheDocument();
  });

  test("renders the table (with the Add action) for the returned servers", () => {
    stubQuery({ data: [resource("srv-a", "mcp_server"), resource("srv-b", "mcp_server")] });
    render(wrap(<ResourcesPage />));
    expect(screen.getByTestId("mcp-table")).toBeInTheDocument();
    expect(screen.getByText("srv-a")).toBeInTheDocument();
    expect(screen.getByText("srv-b")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /add mcp server/i })).toBeInTheDocument();
  });
});
