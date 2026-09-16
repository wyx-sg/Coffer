// frontend/src/components/memory/MemoryPartitionsTable.test.tsx
//
// The partitions list: each row carries the repository it is keyed on, its note
// count and the same ScopeControl the mcp-servers/skills lists render per row
// (spec memory FR-037/FR-013) — ONE button whose label states the partition's
// reach, opening a panel where the states are the choices. ScopeControl's own
// hooks are mocked, mirroring `components/mcp/McpServersTable.test.tsx` — this
// suite only exercises the table.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";

import { TooltipProvider } from "@/components/ui/tooltip";
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
      <TooltipProvider>
        <MemoryRouter>{children ?? ui}</MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

const ROWS: MemoryPartitionRow[] = [
  {
    name: "global",
    repository_path: "",
    repository_key: "",
    note_count: 12,
    unresolvable: false,
    enabled: true,
    scope: null,
  },
  {
    name: "coffer",
    repository_path: "/Users/dev/coffer",
    // A repository with an `origin` is keyed on the remote, so a worktree and a
    // second clone are one partition — the row names the repository, not the
    // working directory some session happened to run in.
    repository_key: "remote:github.com/wyx-sg/coffer",
    note_count: 34,
    unresolvable: false,
    enabled: true,
    scope: { agents: ["claude_code"] },
  },
];

/** A partition whose repository has been deleted from disk (FR-016). */
const GONE: MemoryPartitionRow = {
  name: "old-api",
  repository_path: "/Users/dev/old-api",
  repository_key: "path:/Users/dev/old-api",
  note_count: 3,
  unresolvable: true,
  enabled: true,
  scope: null,
};

describe("MemoryPartitionsTable", () => {
  afterEach(() => vi.clearAllMocks());

  test("partitions render with their repository and note counts", () => {
    render(<MemoryPartitionsTable rows={ROWS} />, { wrapper: wrap(null) });
    expect(screen.getByText("global")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("coffer")).toBeInTheDocument();
    expect(screen.getByText("34")).toBeInTheDocument();
    expect(screen.getByText("/Users/dev/coffer")).toBeInTheDocument();
  });

  test("a partition whose repository is gone stays listed and says so", () => {
    // FR-016: an orphaned partition is delivered to nobody, and deleting it is
    // the developer's call — so it must be VISIBLE and marked, never filtered
    // out of the list where nobody would ever meet it again.
    render(<MemoryPartitionsTable rows={[...ROWS, GONE]} />, { wrapper: wrap(null) });

    const goneRow = within(screen.getByText("old-api").closest("tr") as HTMLElement);
    expect(goneRow.getByText("/Users/dev/old-api")).toBeInTheDocument();
    expect(goneRow.getByTestId("partition-unresolvable-badge")).toHaveTextContent(
      /repository missing/i,
    );
  });

  test("a partition whose repository is still there carries no such mark", () => {
    render(<MemoryPartitionsTable rows={ROWS} />, { wrapper: wrap(null) });
    expect(screen.queryByTestId("partition-unresolvable-badge")).toBeNull();
  });

  test("the reach control appears per partition", () => {
    render(<MemoryPartitionsTable rows={ROWS} />, { wrapper: wrap(null) });
    const controls = screen.getAllByTestId("scope-control");
    expect(controls).toHaveLength(ROWS.length);
    // The scoped partition's button reports the scope it is in: a count of the
    // agents it reaches. WHICH agents those are lives in the panel the button
    // opens, not in the row.
    const cofferRow = within(screen.getByText("coffer").closest("tr") as HTMLElement);
    expect(within(cofferRow.getByTestId("scope-control")).getByRole("button")).toHaveTextContent(
      /^1 agent$/i,
    );
    // …and the unscoped one says so in the same one place.
    const globalRow = within(screen.getByText("global").closest("tr") as HTMLElement);
    expect(within(globalRow.getByTestId("scope-control")).getByRole("button")).toHaveTextContent(
      /^every agent$/i,
    );
  });

  test("selecting rows reveals the same reach control over the whole selection", () => {
    render(<MemoryPartitionsTable rows={ROWS} />, { wrapper: wrap(null) });
    expect(screen.queryByTestId("bulk-reach-control")).toBeNull();

    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    const bar = within(screen.getByTestId("bulk-reach-control"));
    // The same one-button control the rows carry; it names the action rather
    // than a state, because a mixed selection has no single reach to report.
    const trigger = bar.getByRole("button");
    expect(trigger).toHaveTextContent(/set reach/i);
    fireEvent.click(trigger);
    expect(screen.getByRole("radio", { name: /every agent/i })).toBeInTheDocument();
    // No bulk delete: a partition is aggregated from the agents' own memories,
    // never user-created, so there is nothing here to remove.
    expect(screen.queryByRole("button", { name: /^delete$/i })).toBeNull();
  });
});
