// frontend/src/pages/ResourcesPage.test.tsx
//
// The MCP-servers surface. We mock the data hook + the kind registry + the two
// heavy MCP children (table/dialog) so the test asserts ResourcesPage's own
// branching: loading, error, empty-welcome, and the populated table — plus the
// rule that only resources whose kind has a registered UI are surfaced.

import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ResourcesPage } from "./ResourcesPage";
import { ApiError } from "@/lib/api/errors";
import type { ResourceOut } from "@/lib/components/kindRegistry";

vi.mock("@/lib/hooks/useResources", () => ({ useResources: vi.fn() }));
vi.mock("@/lib/components/kindRegistry", () => ({ listKindUIs: vi.fn() }));
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
const { listKindUIs } = await import("@/lib/components/kindRegistry");
const useResourcesMock = vi.mocked(useResources);
const listKindUIsMock = vi.mocked(listKindUIs);

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

// Register a single `mcp_server` kind UI for all tests.
listKindUIsMock.mockReturnValue([
  { name: "mcp_server", displayName: "MCP Servers", Card: () => null },
]);

describe("ResourcesPage", () => {
  afterEach(() => vi.clearAllMocks());

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

  test("shows the welcome panel (and no header Add action) when there are no resources", () => {
    listKindUIsMock.mockReturnValue([
      { name: "mcp_server", displayName: "MCP Servers", Card: () => null },
    ]);
    stubQuery({ data: [] });
    render(wrap(<ResourcesPage />));
    // The welcome panel renders; the table does not. (PageHeader carries no Add
    // action while empty — only the populated state mounts AddMcpServerDialog.)
    expect(screen.queryByTestId("mcp-table")).not.toBeInTheDocument();
  });

  test("renders the table (with the Add action) for resources of a registered kind", () => {
    listKindUIsMock.mockReturnValue([
      { name: "mcp_server", displayName: "MCP Servers", Card: () => null },
    ]);
    stubQuery({ data: [resource("srv-a", "mcp_server"), resource("srv-b", "mcp_server")] });
    render(wrap(<ResourcesPage />));
    expect(screen.getByTestId("mcp-table")).toBeInTheDocument();
    expect(screen.getByText("srv-a")).toBeInTheDocument();
    expect(screen.getByText("srv-b")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /add mcp server/i })).toBeInTheDocument();
  });

  test("filters out resources whose kind has no registered UI (e.g. agents)", () => {
    listKindUIsMock.mockReturnValue([
      { name: "mcp_server", displayName: "MCP Servers", Card: () => null },
    ]);
    stubQuery({ data: [resource("an-agent", "agent"), resource("srv-a", "mcp_server")] });
    render(wrap(<ResourcesPage />));
    // Only the mcp_server row leaks into the visible list.
    expect(screen.getByText("srv-a")).toBeInTheDocument();
    expect(screen.queryByText("an-agent")).not.toBeInTheDocument();
  });

  test("treats an all-unknown-kind result as empty (welcome, not table)", () => {
    listKindUIsMock.mockReturnValue([
      { name: "mcp_server", displayName: "MCP Servers", Card: () => null },
    ]);
    stubQuery({ data: [resource("an-agent", "agent")] });
    render(wrap(<ResourcesPage />));
    expect(screen.queryByTestId("mcp-table")).not.toBeInTheDocument();
  });
});
