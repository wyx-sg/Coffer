// frontend/src/components/knowledge/KnowledgeTable.test.tsx
//
// The collections list. It had drifted from the other tables in three ways the
// user could see: no status control in that column, a delete that was a bare
// icon with no label, and a count header narrow enough to wrap one character
// per line. All three are asserted here — and the count is now two counts,
// because a collection is two lanes and one total would hide a collection
// curation has not reached yet.
//
// The load-bearing assertion added since: this kind offers NO PER-AGENT REACH.
// Every enabled collection is served to every agent, so the control must not
// put an agent list in front of anyone — the server refuses a scope write for
// `knowledge`, and a UI that asks anyway is a UI that asks for a 422. What it
// must keep is the enable/disable choice, because THAT gate is real: a disabled
// collection appears in no agent's delivered skill.
//
// `enabled` is not on /knowledge/collections, so the table merges it in from
// `GET /resources?kind=knowledge` — one request for the table, never one per
// row, which is what useKindReach is stubbed to stand in for.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";

import { KnowledgeTable } from "./KnowledgeTable";
import type { CollectionOut } from "@/lib/api/knowledgeTypes";

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
        // A scope left over from when the kind was scoped. The table must not
        // report it: with no scope declared, `enabled` is the whole answer.
        ["personal", { enabled: false, scope: { agents: ["claude"], machines: null } }],
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
const disableMutate = vi.fn();
vi.mock("@/lib/hooks/useResourceMutations", () => ({
  useEnableResource: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useDisableResource: vi.fn(() => ({ mutate: disableMutate, isPending: false })),
  useDeleteResource: vi.fn(() => ({ mutate: deleteMutate, isPending: false })),
}));
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
  { name: "shopee", description: "internal notes", source_count: 23, topic_count: 9 },
  { name: "personal", description: null, source_count: 4, topic_count: 0 },
];

const rowFor = (name: string) => screen.getByText(name).closest("tr") as HTMLElement;

/** The row's ONE status button — its text is whether the collection is served.
 *  (It used to be three buttons per row; it is one whose label is the answer,
 *  opening a panel where the states are the choices.) */
const reachIn = (name: string) =>
  within(within(rowFor(name)).getByTestId("scope-control")).getByRole("button");

describe("KnowledgeTable", () => {
  afterEach(() => vi.clearAllMocks());

  test("a row shows the collection, its lane counts and its description", () => {
    render(<KnowledgeTable items={ITEMS} />, { wrapper: wrap(null) });
    expect(screen.getByText("shopee")).toBeInTheDocument();
    expect(screen.getByText("23")).toBeInTheDocument();
    expect(screen.getByText("9")).toBeInTheDocument();
    expect(screen.getByText("internal notes")).toBeInTheDocument();
  });

  test("the status column reports the enable gate, and nothing about agents", () => {
    render(<KnowledgeTable items={ITEMS} />, { wrapper: wrap(null) });
    expect(screen.getAllByTestId("scope-control")).toHaveLength(ITEMS.length);

    // One button per row, and its label is the whole answer this kind has:
    // served, or not. Not "Every agent" — that name only means something
    // beside a narrower one, and there is no narrower one here.
    expect(reachIn("shopee")).toHaveTextContent(/^enabled$/i);
    // Even though this row still carries a stored scope naming one agent.
    expect(reachIn("personal")).toHaveTextContent(/^disabled$/i);
  });

  test("no per-agent reach is offered for a collection", () => {
    // Every enabled collection is served to every agent (the `knowledge` kind
    // declares no scope and the server refuses a scope write), so the panel
    // must not offer an agent list at all.
    render(<KnowledgeTable items={ITEMS} />, { wrapper: wrap(null) });
    fireEvent.click(reachIn("shopee"));

    expect(screen.queryByRole("radio", { name: /only selected agents/i })).toBeNull();
    expect(screen.queryByRole("radio", { name: /every agent/i })).toBeNull();
    expect(screen.queryByRole("checkbox", { name: /claude/i })).toBeNull();
    // Two choices, both of them about the gate that is real.
    expect(screen.getByRole("radio", { name: /^enabled$/i })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /^disabled$/i })).toBeInTheDocument();
  });

  test("the enable gate still writes — it is the one control this column has", () => {
    render(<KnowledgeTable items={ITEMS} />, { wrapper: wrap(null) });
    fireEvent.click(reachIn("shopee"));
    fireEvent.click(screen.getByRole("radio", { name: /^disabled$/i }));

    expect(disableMutate).toHaveBeenCalledWith({ kind: "knowledge", name: "shopee" });
  });

  test("the column and its filter are headed Status, not Reach", () => {
    // Renaming the header is the honest half of withdrawing reach: the column
    // reports one thing now. (Which two options the filter offers is pinned in
    // `lib/reachFilter.test.ts` — a Radix Select's list is not in the DOM
    // until it opens.)
    render(<KnowledgeTable items={ITEMS} />, { wrapper: wrap(null) });
    expect(screen.getByRole("columnheader", { name: /^status$/i })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: /^reach$/i })).toBeNull();
    expect(screen.getByRole("combobox", { name: /^status$/i })).toBeInTheDocument();
  });

  test("each lane is counted in its own column", () => {
    // Two counts, not one total: a collection with sources and no topics is one
    // curation has not reached yet, and a single number would hide exactly that.
    render(<KnowledgeTable items={ITEMS} />, { wrapper: wrap(null) });

    expect(within(rowFor("shopee")).getByText("23")).toBeInTheDocument();
    expect(within(rowFor("shopee")).getByText("9")).toBeInTheDocument();
    expect(within(rowFor("personal")).getByText("0")).toBeInTheDocument();
  });

  test("the count headers cannot wrap — they were breaking one character per line", () => {
    render(<KnowledgeTable items={ITEMS} />, { wrapper: wrap(null) });
    for (const name of [/^sources$/i, /^topics$/i]) {
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

  test("selecting rows reveals the bulk status control and a bulk delete", () => {
    render(<KnowledgeTable items={ITEMS} />, { wrapper: wrap(null) });
    expect(screen.queryByTestId("bulk-reach-control")).toBeNull();

    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    // The same one-button control the rows carry; it names the action rather
    // than a state, because a mixed selection has no single answer. For this
    // kind the action is "set status" and not "set reach": a collection has no
    // per-agent reach, so the panel behind the button offers only on and off.
    const bar = within(screen.getByTestId("bulk-reach-control"));
    expect(bar.getByRole("button")).toHaveTextContent(/set status/i);
    expect(bar.getByRole("button")).not.toHaveTextContent(/reach/i);
    expect(screen.getByRole("button", { name: /^delete$/i })).toBeInTheDocument();
  });
});
