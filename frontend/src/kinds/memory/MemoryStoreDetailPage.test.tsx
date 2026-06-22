// frontend/src/kinds/memory/MemoryStoreDetailPage.test.tsx
//
// Exercises the redesigned memory store detail surface (slice 7): the metrics
// header, the recall box ("one query → one answer"; no mode toggle / fallback),
// and the five-lane Tabs shell — Knowledge / Rules / Journal / Handoff /
// Changelog. Knowledge is the default tab: the page-fetched fact list → a
// READ-ONLY preview (select a fact on the left; the right pane renders the
// Markdown with FileActions + delete, no in-app editing), with recall filtering
// it. Switching tabs lazily renders each lane. The `./api` module is mocked so
// the component renders without a backend.

import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ApiError } from "@/lib/api/errors";
import { acceptance } from "@/test/acceptance";
import { MemoryStoreDetailPage } from "./MemoryStoreDetailPage";

vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  listFacts: vi.fn(),
  getFact: vi.fn(),
  getMemoryStore: vi.fn(),
  getMemoryStoreMetrics: vi.fn(),
  getMemoryRules: vi.fn(),
  getMemoryJournal: vi.fn(),
  getMemoryHandoff: vi.fn(),
  getMemoryConsolidationLog: vi.fn(),
  addFact: vi.fn(),
  deleteFact: vi.fn(),
  clearFacts: vi.fn(),
  recall: vi.fn(),
}));
const api = await import("./api");

const FACT = {
  id: "f1",
  store_name: "global",
  scope: "global" as const,
  title: "tabs",
  description: "indentation",
  text: "uses tabs over spaces",
  actor: "user" as const,
  path: "/abs/memory/global/tabs-f1.md",
  folder_path: "/abs/memory/global",
  created_at: "2026-05-29T00:00:00Z",
  updated_at: "2026-05-29T00:00:00Z",
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/memory/global"]}>
        <Routes>
          <Route path="/memory/:name" element={<MemoryStoreDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// Radix Tabs triggers activate on focus/mousedown (automatic activation), which
// `fireEvent.click` alone doesn't dispatch in jsdom; fire mousedown + click so
// the switch registers (a real browser/e2e fires the full sequence).
async function selectTab(name: string) {
  const tab = await screen.findByRole("tab", { name });
  fireEvent.mouseDown(tab);
  fireEvent.click(tab);
  return tab;
}

function stubLists() {
  vi.mocked(api.listFacts).mockResolvedValue({ facts: [FACT], total: 1 });
  vi.mocked(api.getFact).mockResolvedValue(FACT);
  vi.mocked(api.getMemoryStoreMetrics).mockResolvedValue({ fact_count: 1, disk_bytes: 50 });
  // Lane reads default to empty/null so the lanes render without a backend.
  vi.mocked(api.getMemoryRules).mockResolvedValue({ text: null });
  vi.mocked(api.getMemoryJournal).mockResolvedValue({ files: [] });
  vi.mocked(api.getMemoryHandoff).mockResolvedValue({ scenes: [] });
  vi.mocked(api.getMemoryConsolidationLog).mockResolvedValue({
    text: null,
    path: "/p/consolidation-log.md",
    folder_path: "/p",
  });
  vi.mocked(api.getMemoryStore).mockResolvedValue({
    ref: "memory:global",
    kind: "memory",
    name: "global",
    scope: "global",
    project_id: "0".repeat(26),
    project_root: null,
    description: null,
    config: {
      retrieval_modes: ["grep", "keyword"],
      default_mode: "keyword",
      embedding_provider: null,
      embedding_model: null,
      embedding_base_url: null,
      embedding_credential_ref: null,
      embedding_dimensions: 768,
      max_fact_chars: 8192,
    },
    enabled: true,
    created_at: "2026-05-29T00:00:00Z",
    updated_at: "2026-05-29T00:00:00Z",
  });
}

afterEach(() => vi.clearAllMocks());

describe("MemoryStoreDetailPage", () => {
  test("Knowledge tab lists facts in the tree and renders the selected one", async () => {
    stubLists();
    renderPage();
    const tree = screen.getByRole("complementary");
    fireEvent.click(await within(tree).findByText("tabs"));
    expect(await screen.findByText("uses tabs over spaces")).toBeInTheDocument();
  });

  test("renders the five-lane Tabs shell", async () => {
    stubLists();
    renderPage();
    expect(await screen.findByRole("tab", { name: "Knowledge" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Rules" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Journal" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Handoff" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Changelog" })).toBeInTheDocument();
  });

  test("switching to the Rules tab shows the rules lane (empty-state)", async () => {
    stubLists();
    renderPage();
    await selectTab("Rules");
    expect(await screen.findByText(/no rules yet/i)).toBeInTheDocument();
    await waitFor(() => expect(api.getMemoryRules).toHaveBeenCalledWith("global"));
  });

  test("switching to the Journal tab shows the period list / empty-state", async () => {
    stubLists();
    vi.mocked(api.getMemoryJournal).mockResolvedValue({
      files: [{ period: "2026-06", text: "june", path: "/p/2026-06.md", folder_path: "/p" }],
    });
    renderPage();
    await selectTab("Journal");
    expect(await screen.findByText("2026-06")).toBeInTheDocument();
  });

  test("switching to the Handoff tab shows the branch list", async () => {
    stubLists();
    vi.mocked(api.getMemoryHandoff).mockResolvedValue({
      scenes: [
        {
          branch: "feat/x",
          text: "wip",
          updated_at: "2026-06-22T00:00:00Z",
          path: "/p/feat-x.md",
          folder_path: "/p",
        },
      ],
    });
    renderPage();
    await selectTab("Handoff");
    expect(await screen.findByText("feat/x")).toBeInTheDocument();
  });

  test("switching to the Changelog tab shows the consolidation log", async () => {
    stubLists();
    vi.mocked(api.getMemoryConsolidationLog).mockResolvedValue({
      text: "merged 3 facts",
      path: "/p/consolidation-log.md",
      folder_path: "/p",
    });
    renderPage();
    await selectTab("Changelog");
    // The log is one row in the shared file-tree lane; select it to preview.
    // The row is the only button in the panel (vs. the list-header label text).
    const panel = await screen.findByRole("tabpanel");
    fireEvent.click(within(panel).getByRole("button", { name: /^Changelog$/ }));
    expect(await screen.findByText("merged 3 facts")).toBeInTheDocument();
  });

  test("recall (one query → one answer; no mode in the call) renders hits", async () => {
    stubLists();
    vi.mocked(api.recall).mockResolvedValue({
      hits: [{ id: "f1", text: "uses tabs over spaces", score: 0.9, source: "global", time: "t" }],
    });

    renderPage();
    const input = await screen.findByPlaceholderText(/recall facts/i);
    fireEvent.change(input, { target: { value: "tabs" } });
    fireEvent.click(screen.getByRole("button", { name: /^recall$/i }));

    await waitFor(() => expect(api.recall).toHaveBeenCalledWith("global", "tabs", { topK: 5 }));
  });

  test("recall filters the Knowledge tree to the hit fact and highlights the query", async () => {
    const spaces = { ...FACT, id: "f2", title: "spaces", text: "spaces are fine" };
    stubLists();
    vi.mocked(api.listFacts).mockResolvedValue({ facts: [FACT, spaces], total: 2 });
    vi.mocked(api.getMemoryStoreMetrics).mockResolvedValue({ fact_count: 2, disk_bytes: 50 });
    vi.mocked(api.recall).mockResolvedValue({
      hits: [{ id: "f1", text: "uses tabs", score: 0.9, source: "global:/x.md", time: "t" }],
    });
    vi.mocked(api.getFact).mockResolvedValue(FACT);

    renderPage();
    const tree = screen.getByRole("complementary");
    await within(tree).findByText("tabs");
    expect(within(tree).getByText("spaces")).toBeInTheDocument();

    fireEvent.change(await screen.findByPlaceholderText(/recall facts/i), {
      target: { value: "tabs" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^recall$/i }));

    await waitFor(() => expect(api.getFact).toHaveBeenCalledWith("global", "f1"));
    await waitFor(() => expect(within(tree).queryByText("spaces")).not.toBeInTheDocument());
    expect(within(tree).getByText("tabs")).toBeInTheDocument();
    expect(await screen.findByPlaceholderText(/find/i)).toHaveValue("tabs");
  });

  test("clearing the recall box restores the full fact list", async () => {
    const spaces = { ...FACT, id: "f2", title: "spaces", text: "spaces are fine" };
    stubLists();
    vi.mocked(api.listFacts).mockResolvedValue({ facts: [FACT, spaces], total: 2 });
    vi.mocked(api.getMemoryStoreMetrics).mockResolvedValue({ fact_count: 2, disk_bytes: 50 });
    vi.mocked(api.recall).mockResolvedValue({
      hits: [{ id: "f1", text: "uses tabs", score: 0.9, source: "global:/x.md", time: "t" }],
    });
    vi.mocked(api.getFact).mockResolvedValue(FACT);

    renderPage();
    const tree = screen.getByRole("complementary");
    await within(tree).findByText("spaces");
    fireEvent.change(await screen.findByPlaceholderText(/recall facts/i), {
      target: { value: "tabs" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^recall$/i }));
    await waitFor(() => expect(within(tree).queryByText("spaces")).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /^clear$/i }));
    expect(await within(tree).findByText("spaces")).toBeInTheDocument();
  });

  test("a recall with no hits shows the no-matches label and an empty tree", async () => {
    stubLists();
    vi.mocked(api.recall).mockResolvedValue({ hits: [] });

    renderPage();
    const tree = screen.getByRole("complementary");
    await within(tree).findByText("tabs");

    fireEvent.change(await screen.findByPlaceholderText(/recall facts/i), {
      target: { value: "zzz" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^recall$/i }));

    expect(await within(tree).findByText(/no matches/i)).toBeInTheDocument();
    expect(within(tree).queryByText("tabs")).not.toBeInTheDocument();
  });

  test("a selected fact renders READ-ONLY: no Edit/Save controls", async () => {
    stubLists();
    renderPage();
    const tree = screen.getByRole("complementary");
    fireEvent.click(await within(tree).findByText("tabs"));
    expect(await screen.findByText("uses tabs over spaces")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^save$/i })).not.toBeInTheDocument();
  });

  // Spec 007 scenario: the human-facing memory viewer is read-only and routes
  // edits to the user's own editor — it surfaces open/reveal affordances
  // (daemon-backed on web, Tauri on desktop) instead of an in-app editor.
  acceptance("007-memory", "read-only viewer offers open/reveal affordances", async () => {
    stubLists();
    renderPage();
    const tree = screen.getByRole("complementary");
    fireEvent.click(await within(tree).findByText("tabs"));
    await screen.findByText("uses tabs over spaces");
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reveal/i })).toBeInTheDocument();
  });

  test("deleting a selected fact calls delete after confirming in the dialog", async () => {
    stubLists();
    vi.mocked(api.deleteFact).mockResolvedValue(undefined);

    renderPage();
    const tree = screen.getByRole("complementary");
    fireEvent.click(await within(tree).findByText("tabs"));
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    const dialog = await screen.findByRole("dialog");
    expect(api.deleteFact).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));
    await waitFor(() => expect(api.deleteFact).toHaveBeenCalledWith("global", "f1"));
  });

  test("does NOT delete a fact when the confirm dialog is cancelled", async () => {
    stubLists();
    vi.mocked(api.deleteFact).mockResolvedValue(undefined);

    renderPage();
    const tree = screen.getByRole("complementary");
    fireEvent.click(await within(tree).findByText("tabs"));
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /cancel/i }));
    expect(api.deleteFact).not.toHaveBeenCalled();
  });

  test("surfaces a localized error when the metrics query fails", async () => {
    stubLists();
    vi.mocked(api.getMemoryStoreMetrics).mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "nope"),
    );

    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(/resource not found/i);
  });

  test("Knowledge tab renders all facts in one scrollable list (no in-UI pager)", async () => {
    // The list is fetched in ONE request at the API max page size and rendered
    // as a single scrollable list — no page-based pager.
    stubLists();
    const facts = Array.from({ length: 120 }, (_, i) => ({
      ...FACT,
      id: `f${i}`,
      title: `fact-${i}`,
    }));
    vi.mocked(api.listFacts).mockResolvedValue({ facts, total: 120 });
    vi.mocked(api.getMemoryStoreMetrics).mockResolvedValue({ fact_count: 120, disk_bytes: 50 });

    renderPage();
    const tree = screen.getByRole("complementary");
    expect(await within(tree).findByText("fact-0")).toBeVisible();
    expect(within(tree).getByText("fact-119")).toBeInTheDocument();
    await waitFor(() => expect(api.listFacts).toHaveBeenCalledWith("global", 200, 0));
    expect(within(tree).queryByRole("button", { name: /next/i })).toBeNull();
  });

  test("clear-all calls clearFacts after confirming in the dialog", async () => {
    stubLists();
    vi.mocked(api.clearFacts).mockResolvedValue(1);

    renderPage();
    const btn = await screen.findByRole("button", { name: /clear all/i });
    await waitFor(() => expect(btn).toBeEnabled());
    fireEvent.click(btn);
    const dialog = await screen.findByRole("dialog");
    expect(api.clearFacts).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: /clear all/i }));
    await waitFor(() => expect(api.clearFacts).toHaveBeenCalledWith("global"));
  });
});
