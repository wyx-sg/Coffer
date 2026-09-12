// frontend/src/kinds/mcp/McpServersTable.test.tsx
//
// The MCP servers list now renders via the shared DataTable: rows navigate to
// the detail page on click, each row carries a health badge + the three-state
// ScopeControl (the server's reach, the same control the detail header mounts)
// + delete action, and a leading checkbox column drives bulk
// enable/disable/delete over the selected rows.

import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";
import { McpServersTable } from "./McpServersTable";
import { ApiError } from "@/lib/api/errors";
import type { ResourceOut } from "@/lib/components/kindRegistry";

const navigateMock = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

// The status cell is ScopeControl. useResourceScope returns nothing on purpose:
// the rows must render from the list payload's `scope`, and one test asserts
// the hook's query is switched OFF so the list costs no extra request per row.
vi.mock("@/lib/hooks/useScope", () => ({
  useResourceScope: vi.fn(() => ({ data: undefined })),
  useUpdateResourceScope: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: vi.fn(() => ({ data: [{ name: "cc" }] })),
}));

vi.mock("@/lib/hooks/useResourceMutations", () => {
  const stub = () => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    error: null,
    reset: vi.fn(),
  });
  return {
    useEnableResource: vi.fn(stub),
    useDisableResource: vi.fn(stub),
    useDeleteResource: vi.fn(stub),
  };
});

const { useDeleteResource, useEnableResource, useDisableResource } =
  await import("@/lib/hooks/useResourceMutations");
const useDeleteResourceMock = vi.mocked(useDeleteResource);
const { useResourceScope } = await import("@/lib/hooks/useScope");

vi.mock("@/lib/hooks/useMcpServerStatus", () => ({
  useMcpServerStatus: vi.fn(() => ({ data: "healthy" })),
  useMcpServerRunner: vi.fn(() => ({ data: { missingRunner: null } })),
}));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children ?? ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

const SAMPLE: ResourceOut[] = [
  {
    ref: "mcp_server:files",
    kind: "mcp_server",
    name: "files",
    enabled: true,
    scope: null,
    description: "Local filesystem access",
    config: { transport: { type: "stdio" } },
    created_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:00Z",
  },
  {
    ref: "mcp_server:web",
    kind: "mcp_server",
    name: "web",
    enabled: false,
    scope: null,
    description: "Remote fetch",
    config: { transport: { type: "http" } },
    created_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:00Z",
  },
  {
    // Enabled but scoped: the state the old on/off switch could not express.
    ref: "mcp_server:notes",
    kind: "mcp_server",
    name: "notes",
    enabled: true,
    scope: ["cc"],
    description: "Scoped to one agent",
    config: { transport: { type: "sse" } },
    created_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:00Z",
  },
];

/** The <tr> carrying the named server, as a scoped query root. */
function rowFor(name: string) {
  return within(screen.getByText(name).closest("tr") as HTMLElement);
}

// The status filter's combobox is first in DOM order (the pagination page-size
// one renders after the table).
function selectStatus(optionName: string) {
  fireEvent.click(screen.getAllByRole("combobox")[0]);
  fireEvent.click(screen.getByRole("option", { name: optionName }));
}

describe("McpServersTable", () => {
  afterEach(() => vi.clearAllMocks());

  test("renders one row per server with its name and transport", () => {
    render(<McpServersTable resources={SAMPLE} />, { wrapper: wrap(null) });
    expect(screen.getByText("files")).toBeInTheDocument();
    expect(screen.getByText("web")).toBeInTheDocument();
    expect(screen.getByText("stdio")).toBeInTheDocument();
    expect(screen.getByText("http")).toBeInTheDocument();
  });

  test("a search box is available", () => {
    render(<McpServersTable resources={SAMPLE} />, { wrapper: wrap(null) });
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });

  test("renders selection checkboxes (select-all + one per row)", () => {
    render(<McpServersTable resources={SAMPLE} />, { wrapper: wrap(null) });
    // Select-all header checkbox + one per visible row.
    expect(screen.getAllByRole("checkbox").length).toBeGreaterThanOrEqual(2);
  });

  test("the status cell is the three-state scope control, not an on/off switch", () => {
    render(<McpServersTable resources={SAMPLE} />, { wrapper: wrap(null) });

    expect(screen.queryByRole("switch")).toBeNull();
    expect(rowFor("files").getByRole("button", { name: /every agent/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(rowFor("notes").getByRole("button", { name: /selected agents/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(rowFor("web").getByRole("button", { name: /^disabled$/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  test("each row's scope comes from the list payload — no per-row scope fetch", () => {
    render(<McpServersTable resources={SAMPLE} />, { wrapper: wrap(null) });

    // Third argument is the query's `enabled` flag: false on every row.
    expect(vi.mocked(useResourceScope).mock.calls.length).toBeGreaterThan(0);
    for (const call of vi.mocked(useResourceScope).mock.calls) {
      expect(call[2]).toBe(false);
    }
  });

  test("the scope control drives enable/disable, and never navigates the row", () => {
    const enableMutate = vi.fn();
    const disableMutate = vi.fn();
    vi.mocked(useEnableResource).mockReturnValue({
      mutate: enableMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useEnableResource>);
    vi.mocked(useDisableResource).mockReturnValue({
      mutate: disableMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useDisableResource>);

    render(<McpServersTable resources={SAMPLE} />, { wrapper: wrap(null) });

    fireEvent.click(rowFor("files").getByRole("button", { name: /^disabled$/i }));
    expect(disableMutate).toHaveBeenCalledWith({ kind: "mcp_server", name: "files" });
    fireEvent.click(rowFor("web").getByRole("button", { name: /every agent/i }));
    expect(enableMutate).toHaveBeenCalledWith({ kind: "mcp_server", name: "web" });
    expect(navigateMock).not.toHaveBeenCalled();

    // …while the row itself still navigates.
    fireEvent.click(screen.getByText("Local filesystem access"));
    expect(navigateMock).toHaveBeenCalledWith("/mcp-servers/mcp_server/files");
  });

  test("the status filter narrows the rows by reach", () => {
    render(<McpServersTable resources={SAMPLE} />, { wrapper: wrap(null) });

    selectStatus("Disabled");
    expect(screen.queryByText("files")).toBeNull();
    expect(screen.getByText("web")).toBeInTheDocument();

    selectStatus("Every agent");
    expect(screen.getByText("files")).toBeInTheDocument();
    expect(screen.queryByText("notes")).toBeNull();

    selectStatus("Selected agents");
    expect(screen.getByText("notes")).toBeInTheDocument();
    expect(screen.queryByText("files")).toBeNull();
  });

  test("a failed delete surfaces the error inline and leaves the dialog open", () => {
    // The delete mutation reports an error; the confirm dialog must show it
    // (role=alert) and stay open rather than disappear silently (FE1/SW3).
    useDeleteResourceMock.mockReturnValue({
      mutate: vi.fn(),
      mutateAsync: vi.fn(),
      isPending: false,
      error: new ApiError("RESOURCE_BUSY", "server is in use"),
      reset: vi.fn(),
    } as unknown as ReturnType<typeof useDeleteResource>);

    render(<McpServersTable resources={SAMPLE} />, { wrapper: wrap(null) });
    fireEvent.click(screen.getAllByRole("button", { name: /delete files/i })[0]);

    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("alert")).toHaveTextContent("server is in use");
  });
});
