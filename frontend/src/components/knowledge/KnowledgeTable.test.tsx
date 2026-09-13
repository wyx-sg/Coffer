// frontend/src/components/knowledge/KnowledgeTable.test.tsx
//
// The collections list. It had drifted from the other tables in three ways the
// user could see: no reach control in the status column, a delete that was a
// bare icon with no label, and a "Files" header narrow enough to wrap one
// character per line. All three are asserted here.
//
// `enabled`/`scope` are not on /knowledge/collections, so the table merges them
// in from `GET /resources?kind=knowledge` — one request for the table, never one
// per row, which is what useKindReach is stubbed to stand in for.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";

import { KnowledgeTable } from "./KnowledgeTable";
import type { CollectionOut } from "@/kinds/knowledge/types";

const navigateMock = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock("@/lib/hooks/useResources", () => ({
  useKindReach: vi.fn(
    () =>
      new Map([
        ["shopee", { enabled: true, scope: null }],
        ["personal", { enabled: true, scope: { agents: ["claude"], machines: null } }],
      ]),
  ),
}));
vi.mock("@/lib/hooks/useScope", () => ({
  useResourceScope: vi.fn(() => ({ data: undefined })),
  useUpdateResourceScope: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: vi.fn(() => ({ data: [{ name: "claude" }] })),
}));
const deleteMutate = vi.fn();
vi.mock("@/lib/hooks/useResourceMutations", () => {
  const stub = () => ({ mutate: vi.fn(), isPending: false });
  return {
    useEnableResource: vi.fn(stub),
    useDisableResource: vi.fn(stub),
    useDeleteResource: vi.fn(() => ({ mutate: deleteMutate, isPending: false })),
  };
});
vi.mock("@/lib/api/resources", () => ({
  resourcesApi: { enable: vi.fn(), disable: vi.fn(), remove: vi.fn() },
}));
vi.mock("@/lib/api/scope", () => ({ scopeApi: { get: vi.fn(), put: vi.fn() } }));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children ?? ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

const ITEMS: CollectionOut[] = [
  { name: "shopee", description: "internal notes", file_count: 23 },
  { name: "personal", description: null, file_count: 4 },
];

const rowFor = (name: string) => screen.getByText(name).closest("tr") as HTMLElement;

describe("KnowledgeTable", () => {
  afterEach(() => vi.clearAllMocks());

  test("a row shows the collection, its file count and its description", () => {
    render(<KnowledgeTable items={ITEMS} />, { wrapper: wrap(null) });
    expect(screen.getByText("shopee")).toBeInTheDocument();
    expect(screen.getByText("23")).toBeInTheDocument();
    expect(screen.getByText("internal notes")).toBeInTheDocument();
  });

  test("the status column is the same reach control every other kind's row has", () => {
    render(<KnowledgeTable items={ITEMS} />, { wrapper: wrap(null) });
    expect(screen.getAllByTestId("scope-control")).toHaveLength(ITEMS.length);

    expect(within(rowFor("shopee")).getByRole("button", { name: /everywhere/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(
      within(rowFor("personal")).getByRole("button", { name: /restricted/i }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  test("the Files header cannot wrap — it was breaking one character per line", () => {
    render(<KnowledgeTable items={ITEMS} />, { wrapper: wrap(null) });
    const header = screen.getByRole("columnheader", { name: /files/i });
    expect(header.className).toContain("whitespace-nowrap");
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

  test("selecting rows reveals the bulk reach control and a bulk delete", () => {
    render(<KnowledgeTable items={ITEMS} />, { wrapper: wrap(null) });
    expect(screen.queryByTestId("bulk-reach-control")).toBeNull();

    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    expect(screen.getByTestId("bulk-reach-control")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^delete$/i })).toBeInTheDocument();
  });
});
