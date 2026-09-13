// frontend/src/components/memory/MemoryPartitionsTable.test.tsx
//
// The partitions list: each row carries its fact count and the same
// three-state ScopeControl the mcp-servers/skills lists render per row
// (spec memory FR-062/FR-014). ScopeControl's own hooks are mocked, mirroring
// `kinds/mcp/McpServersTable.test.tsx` — this suite only exercises the table.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";

import { MemoryPartitionsTable, type MemoryPartitionRow } from "./MemoryPartitionsTable";

vi.mock("@/lib/hooks/useScope", () => ({
  useResourceScope: vi.fn(() => ({ data: undefined })),
  useUpdateResourceScope: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: vi.fn(() => ({ data: [{ name: "claude_code" }] })),
}));
vi.mock("@/lib/hooks/useResourceMutations", () => {
  const stub = () => ({ mutate: vi.fn(), isPending: false });
  return { useEnableResource: vi.fn(stub), useDisableResource: vi.fn(stub) };
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children ?? ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

const ROWS: MemoryPartitionRow[] = [
  { name: "global", project_root: "", fact_count: 12, enabled: true, scope: null },
  {
    name: "coffer",
    project_root: "/Users/dev/coffer",
    fact_count: 34,
    enabled: true,
    scope: { agents: ["claude_code"], machines: null },
  },
];

describe("MemoryPartitionsTable", () => {
  afterEach(() => vi.clearAllMocks());

  test("partitions render with their fact counts", () => {
    render(<MemoryPartitionsTable rows={ROWS} />, { wrapper: wrap(null) });
    expect(screen.getByText("global")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("coffer")).toBeInTheDocument();
    expect(screen.getByText("34")).toBeInTheDocument();
    expect(screen.getByText("/Users/dev/coffer")).toBeInTheDocument();
  });

  test("the reach control appears per partition", () => {
    render(<MemoryPartitionsTable rows={ROWS} />, { wrapper: wrap(null) });
    const controls = screen.getAllByTestId("scope-control");
    expect(controls).toHaveLength(ROWS.length);
    // The scoped partition shows its selected-agents segment as active.
    const coffeeRow = within(screen.getByText("coffer").closest("tr") as HTMLElement);
    // The trigger reads "Restricted…"; which axis and which names are in the
    // popover, because scope now has two axes (spec vault-sync).
    expect(coffeeRow.getByText(/restricted/i)).toBeInTheDocument();
  });

  test("selecting rows reveals the same reach control over the whole selection", () => {
    render(<MemoryPartitionsTable rows={ROWS} />, { wrapper: wrap(null) });
    expect(screen.queryByTestId("bulk-reach-control")).toBeNull();

    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    const bar = within(screen.getByTestId("bulk-reach-control"));
    expect(bar.getByRole("button", { name: /everywhere/i })).toBeInTheDocument();
    // No bulk delete: a partition is aggregated from the agents' own memories,
    // never user-created, so there is nothing here to remove.
    expect(screen.queryByRole("button", { name: /^delete$/i })).toBeNull();
  });
});
