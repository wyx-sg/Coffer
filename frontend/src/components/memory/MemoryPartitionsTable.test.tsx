// frontend/src/components/memory/MemoryPartitionsTable.test.tsx
//
// The partitions list: each row carries the repository it is keyed on, its note
// count and the status control every Resource gets (spec memory FR-037/FR-013)
// — ONE button whose label says whether the partition is served, opening a
// panel where the states are the choices. ScopeControl's own hooks are mocked,
// mirroring `components/mcp/McpServersTable.test.tsx` — this suite only
// exercises the table.
//
// The load-bearing assertion added since: this kind offers NO PER-AGENT REACH.
// Memory is aggregated from every agent's own notes and served back to every
// agent, so the panel must not put an agent list in front of anyone — the
// server refuses a scope write for `memory`, and a UI that asks anyway is a UI
// that asks for a 422. What it must keep is the enable/disable choice, because
// THAT gate is real: a disabled partition is served to nobody.
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
  useAgents: vi.fn(() => ({ data: [{ uid: "u-cc", name: "claude_code" }] })),
}));
const disableMutate = vi.fn();
vi.mock("@/lib/hooks/useResourceMutations", () => ({
  useEnableResource: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useDisableResource: vi.fn(() => ({ mutate: disableMutate, isPending: false })),
}));

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

// A partition carries three strings that are easy to confuse and are three
// different things: the `uid` every route takes, the `name` that is its folder
// and its label, and the `repository_key` a working directory resolves
// through. None of them is derived from another.
const ROWS: MemoryPartitionRow[] = [
  {
    uid: "mp-4410",
    name: "global",
    repository_path: "",
    repository_key: "",
    note_count: 12,
    unresolvable: false,
    enabled: true,
  },
  {
    uid: "mp-be27",
    name: "coffer",
    repository_path: "/Users/dev/coffer",
    // A repository with an `origin` is keyed on the remote, so a worktree and a
    // second clone are one partition — the row names the repository, not the
    // working directory some session happened to run in.
    repository_key: "remote:github.com/wyx-sg/coffer",
    note_count: 34,
    unresolvable: false,
    // Disabled, which is the one thing this column reports — and the one thing
    // that stops a partition being served.
    enabled: false,
  },
];

/** A partition whose repository has been deleted from disk (FR-016). */
const GONE: MemoryPartitionRow = {
  uid: "mp-0d5c",
  name: "old-api",
  repository_path: "/Users/dev/old-api",
  repository_key: "path:/Users/dev/old-api",
  note_count: 3,
  unresolvable: true,
  enabled: true,
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

  const controlIn = (name: string) =>
    within(
      within(screen.getByText(name).closest("tr") as HTMLElement).getByTestId("scope-control"),
    ).getByRole("button");

  test("the status control appears per partition and reports the enable gate", () => {
    render(<MemoryPartitionsTable rows={ROWS} />, { wrapper: wrap(null) });
    expect(screen.getAllByTestId("scope-control")).toHaveLength(ROWS.length);
    // The whole answer this kind has: served, or not. Not "Every agent" — that
    // name only means something beside a narrower one, and there is none here.
    expect(controlIn("global")).toHaveTextContent(/^enabled$/i);
    expect(controlIn("coffer")).toHaveTextContent(/^disabled$/i);
  });

  test("no per-agent reach is offered for a partition", () => {
    render(<MemoryPartitionsTable rows={ROWS} />, { wrapper: wrap(null) });
    fireEvent.click(controlIn("global"));

    expect(screen.queryByRole("radio", { name: /only selected/i })).toBeNull();
    expect(screen.queryByRole("radio", { name: /every agent/i })).toBeNull();
    expect(screen.queryByRole("checkbox", { name: /claude_code/i })).toBeNull();
    // Two choices, both of them about the gate that is real.
    expect(screen.getByRole("radio", { name: /^enabled$/i })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /^disabled$/i })).toBeInTheDocument();
  });

  test("the enable gate still writes — it is the one control this column has", () => {
    render(<MemoryPartitionsTable rows={ROWS} />, { wrapper: wrap(null) });
    fireEvent.click(controlIn("global"));
    fireEvent.click(screen.getByRole("radio", { name: /^disabled$/i }));

    // Picked by the name in the row; written against the uid.
    expect(disableMutate).toHaveBeenCalledWith({ kind: "memory", uid: "mp-4410" });
  });

  test("the column and its filter are headed Status, not Reach", () => {
    // (Which two options the filter offers is pinned in
    // `lib/reachFilter.test.ts` — a Radix Select's list is not in the DOM until
    // it opens.)
    render(<MemoryPartitionsTable rows={ROWS} />, { wrapper: wrap(null) });
    expect(screen.getByRole("columnheader", { name: /^status$/i })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: /^reach$/i })).toBeNull();
    expect(screen.getByRole("combobox", { name: /^status$/i })).toBeInTheDocument();
  });

  test("selecting rows reveals the same control over the whole selection", () => {
    render(<MemoryPartitionsTable rows={ROWS} />, { wrapper: wrap(null) });
    expect(screen.queryByTestId("bulk-reach-control")).toBeNull();

    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    const bar = within(screen.getByTestId("bulk-reach-control"));
    // The same one-button control the rows carry; it names the action rather
    // than a state, because a mixed selection has no single one to report.
    const trigger = bar.getByRole("button");
    fireEvent.click(trigger);
    // And the same two choices as the rows — no agent list over a selection
    // either, since no scope write would be accepted for any of them.
    expect(screen.getByRole("radio", { name: /^enabled$/i })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /^disabled$/i })).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /only selected/i })).toBeNull();
    // No bulk delete: a partition is aggregated from the agents' own memories,
    // never user-created, so there is nothing here to remove.
    expect(screen.queryByRole("button", { name: /^delete$/i })).toBeNull();
  });
});
