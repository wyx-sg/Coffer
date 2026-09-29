// frontend/src/components/memory/MemoryPartitionsTable.test.tsx
//
// The partitions list: each row carries the repository it is keyed on and its
// note count (spec memory "Present partitions as a table and a file tree").
// It carries no status control, no status filter and no bulk bar: every
// partition is served to every agent (spec memory "Serve every partition to
// every agent"), so there is nothing to switch.
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { PartitionOut } from "@/lib/api/memoryTypes";
import { acceptance } from "@/test/acceptance";
import { MemoryPartitionsTable } from "./MemoryPartitionsTable";

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
const ROWS: PartitionOut[] = [
  {
    uid: "mp-4410",
    name: "global",
    title: null,
    repository_path: "",
    repository_key: "",
    note_count: 12,
    unresolvable: false,
  },
  {
    uid: "mp-be27",
    name: "coffer",
    title: null,
    repository_path: "/Users/dev/coffer",
    // A repository with an `origin` is keyed on the remote, so a worktree and a
    // second clone are one partition — the row names the repository, not the
    // working directory some session happened to run in.
    repository_key: "remote:github.com/wyx-sg/coffer",
    note_count: 34,
    unresolvable: false,
  },
];

/** A partition whose repository has been deleted from disk (see "Report
 *  unresolvable partitions"). */
const GONE: PartitionOut = {
  uid: "mp-0d5c",
  name: "old-api",
  title: null,
  repository_path: "/Users/dev/old-api",
  repository_key: "path:/Users/dev/old-api",
  note_count: 3,
  unresolvable: true,
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
    // "Report unresolvable partitions": an orphaned partition is delivered to nobody, and deleting
    // it is the developer's call — so it must be VISIBLE and marked, never filtered
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

  acceptance("web-ui", "a kind that cannot be disabled shows no status control", () => {
    render(<MemoryPartitionsTable rows={ROWS} />, { wrapper: wrap(null) });
    expect(screen.queryByTestId("scope-control")).toBeNull();
    expect(screen.queryByRole("columnheader", { name: /^status$/i })).toBeNull();
    expect(screen.queryByRole("columnheader", { name: /^reach$/i })).toBeNull();
    expect(screen.queryByRole("combobox", { name: /^status$/i })).toBeNull();
    // No selection either: with no bulk action there is nothing to select for.
    expect(screen.queryByRole("checkbox")).toBeNull();
  });
});
