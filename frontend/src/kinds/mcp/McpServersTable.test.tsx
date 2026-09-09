// frontend/src/kinds/mcp/McpServersTable.test.tsx
//
// The MCP servers list now renders via the shared DataTable: rows navigate to
// the detail page on click, each row carries a health badge + enable/disable
// switch + delete action, and a leading checkbox column drives bulk
// enable/disable/delete over the selected rows.

import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";
import { McpServersTable } from "./McpServersTable";
import { ApiError } from "@/lib/api/errors";
import type { ResourceOut } from "@/lib/components/kindRegistry";

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

const { useDeleteResource } = await import("@/lib/hooks/useResourceMutations");
const useDeleteResourceMock = vi.mocked(useDeleteResource);

vi.mock("@/lib/hooks/useMcpInvocations", () => ({
  useMcpServerStatus: vi.fn(() => ({ data: "healthy" })),
  useMcpServerRunner: vi.fn(() => ({ data: { missingRunner: null, installable: false } })),
  useInstallMcpRunner: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
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
    description: "Remote fetch",
    config: { transport: { type: "http" } },
    created_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:00Z",
  },
];

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
