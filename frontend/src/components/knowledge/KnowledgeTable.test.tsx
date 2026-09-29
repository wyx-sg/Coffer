// frontend/src/components/knowledge/KnowledgeTable.test.tsx
//
// The collections list. It had drifted from the other tables in ways the user
// could see: a delete that was a bare icon with no label, and a count header
// narrow enough to wrap one character per line. Both are asserted here — and
// the count is two counts,
// documents and pending material, because one total would hide a collection
// curation has not caught up with.
//
// And the list has no status column and no bulk enable / disable: every
// collection is served to every agent, so there is nothing to switch.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";

import { KnowledgeTable } from "./KnowledgeTable";
import { acceptance } from "@/test/acceptance";
import type { CollectionOut } from "@/lib/api/knowledgeTypes";

const navigateMock = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

const deleteMutate = vi.fn();
vi.mock("@/lib/hooks/useResourceMutations", () => ({
  useDeleteResource: vi.fn(() => ({ mutate: deleteMutate, isPending: false })),
}));
vi.mock("@/lib/api/resources", () => ({
  resourcesApi: { remove: vi.fn() },
}));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children ?? ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

// A collection carries both identities: the uid the row links to, and the name the cell prints — which is ALSO the
// collection's directory name, and so what the file routes take.
const ITEMS: CollectionOut[] = [
  {
    uid: "kn-8c1f",
    name: "shopee",
    description: "internal notes",
    document_count: 23,
    pending_count: 9,
  },
  { uid: "kn-3e70", name: "personal", description: null, document_count: 4, pending_count: 0 },
];

const rowFor = (name: string) => screen.getByText(name).closest("tr") as HTMLElement;

describe("KnowledgeTable", () => {
  afterEach(() => vi.clearAllMocks());

  test("a row shows the collection, its counts and its description", () => {
    render(<KnowledgeTable items={ITEMS} />, { wrapper: wrap(null) });
    expect(screen.getByText("shopee")).toBeInTheDocument();
    expect(screen.getByText("23")).toBeInTheDocument();
    expect(screen.getByText("9")).toBeInTheDocument();
    expect(screen.getByText("internal notes")).toBeInTheDocument();
  });

  acceptance("web-ui", "a kind that cannot be disabled shows no status control", () => {
    render(<KnowledgeTable items={ITEMS} />, { wrapper: wrap(null) });
    expect(screen.queryByTestId("scope-control")).toBeNull();
    expect(screen.queryByRole("columnheader", { name: /^status$/i })).toBeNull();
    expect(screen.queryByRole("columnheader", { name: /^reach$/i })).toBeNull();
    // No status filter either: there is nothing to filter on.
    expect(screen.queryByRole("combobox", { name: /^status$/i })).toBeNull();
  });

  test("documents and pending material are counted in their own columns", () => {
    // Two counts, not one total: material still in the inbox is what no agent
    // can read yet, and a single number would hide exactly that.
    render(<KnowledgeTable items={ITEMS} />, { wrapper: wrap(null) });

    expect(within(rowFor("shopee")).getByText("23")).toBeInTheDocument();
    expect(within(rowFor("shopee")).getByText("9")).toBeInTheDocument();
    expect(within(rowFor("personal")).getByText("0")).toBeInTheDocument();
  });

  test("the count headers cannot wrap — they were breaking one character per line", () => {
    render(<KnowledgeTable items={ITEMS} />, { wrapper: wrap(null) });
    for (const name of [/^documents$/i, /^pending$/i]) {
      expect(screen.getByRole("columnheader", { name }).className).toContain("whitespace-nowrap");
    }
    // The description column is the flexible one, which is what stops the
    // fixed-width columns being squeezed narrow enough to wrap at all.
    expect(screen.getByRole("columnheader", { name: /description/i }).className).toContain(
      "w-full",
    );
  });

  test("delete is a labelled button, not a bare icon, and confirms first", () => {
    render(<KnowledgeTable items={ITEMS} />, { wrapper: wrap(null) });
    const del = within(rowFor("shopee")).getByRole("button", { name: /delete: shopee/i });
    expect(del).toHaveTextContent(/delete/i);

    fireEvent.click(del);
    expect(screen.getByRole("dialog")).toHaveTextContent(/delete collection/i);
    // It must not have navigated into the collection it is about to delete.
    expect(navigateMock).not.toHaveBeenCalled();
  });

  test("selecting rows offers a bulk delete and no bulk status control", () => {
    render(<KnowledgeTable items={ITEMS} />, { wrapper: wrap(null) });
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    expect(screen.queryByTestId("bulk-reach-control")).toBeNull();
    expect(screen.getByRole("button", { name: /^delete$/i })).toBeInTheDocument();
  });
});
