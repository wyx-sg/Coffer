// frontend/src/kinds/knowledge/KnowledgeDetailPage.test.tsx
//
// Exercises the merged knowledge-scope detail surface: the metrics header and
// the Tabs shell — Entries / Documents / Rules / Handoff plus the consolidation
// Changelog view. Entries is the default tab: the entry list → a READ-ONLY
// preview (select an entry on the left; the right pane renders the Markdown
// with FileActions + delete, no in-app editing), with its own recall box ("one
// query → one answer"; no mode toggle / fallback) filtering it. Switching tabs
// lazily renders each lane. The Documents lane has its own test file. The
// `./api` module is mocked so the component renders without a backend.

import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ApiError } from "@/lib/api/errors";
import { acceptance } from "@/test/acceptance";
import { KnowledgeDetailPage } from "./KnowledgeDetailPage";
import type { KnowledgeConfigOut } from "./types";

vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  listEntries: vi.fn(),
  getEntry: vi.fn(),
  getScope: vi.fn(),
  getScopeMetrics: vi.fn(),
  getKnowledgeRules: vi.fn(),
  getKnowledgeHandoff: vi.fn(),
  getConsolidationLog: vi.fn(),
  addEntry: vi.fn(),
  deleteEntry: vi.fn(),
  clearEntries: vi.fn(),
  recall: vi.fn(),
  listDocuments: vi.fn(),
  getDocument: vi.fn(),
}));
const api = await import("./api");

const ENTRY = {
  id: "f1",
  scope_name: "global",
  scope: "global" as const,
  title: "tabs",
  description: "indentation",
  text: "uses tabs over spaces",
  actor: "user" as const,
  path: "/abs/knowledge/global/knowledge/tabs-f1.md",
  folder_path: "/abs/knowledge/global/knowledge",
  created_at: "2026-05-29T00:00:00Z",
  updated_at: "2026-05-29T00:00:00Z",
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/knowledge/global"]}>
        <Routes>
          <Route path="/knowledge/:scope" element={<KnowledgeDetailPage />} />
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

const CONFIG: KnowledgeConfigOut = {
  retrieval_modes: ["grep", "keyword"],
  default_mode: "keyword",
  max_entry_chars: 8192,
  chunk_size: 512,
  chunk_overlap: 64,
  max_document_bytes: 26214400,
  auto_update_sources: false,
};

// Both lanes report their own count; the metrics fixture keeps them distinct so
// a test can never pass by summing entries and documents into one number.
const metrics = (entries: number) => ({
  entry_count: entries,
  document_count: 0,
  chunk_count: 0,
  documents_degraded: 0,
  indexed_modes: ["grep", "keyword"] as ("grep" | "keyword")[],
  disk_bytes: 50,
});

function stubLists() {
  vi.mocked(api.listEntries).mockResolvedValue({ entries: [ENTRY], total: 1 });
  vi.mocked(api.getEntry).mockResolvedValue(ENTRY);
  vi.mocked(api.getScopeMetrics).mockResolvedValue(metrics(1));
  // The page always mounts the documents hook (the header's Upload / Reindex /
  // Check-sources actions drive it), so its list read is stubbed even though
  // the Documents lane has its own test file.
  vi.mocked(api.listDocuments).mockResolvedValue({ documents: [], total: 0 });
  // Lane reads default to empty/null so the lanes render without a backend.
  vi.mocked(api.getKnowledgeRules).mockResolvedValue({ text: null });
  vi.mocked(api.getKnowledgeHandoff).mockResolvedValue({ scenes: [] });
  vi.mocked(api.getConsolidationLog).mockResolvedValue({
    text: null,
    path: "/p/consolidation-log.md",
    folder_path: "/p",
  });
  vi.mocked(api.getScope).mockResolvedValue({
    ref: "knowledge:global",
    kind: "knowledge",
    name: "global",
    scope: "global",
    project_id: "0".repeat(26),
    project_root: null,
    description: null,
    config: CONFIG,
    enabled: true,
    created_at: "2026-05-29T00:00:00Z",
    updated_at: "2026-05-29T00:00:00Z",
  });
}

afterEach(() => vi.clearAllMocks());

describe("KnowledgeDetailPage", () => {
  test("Entries tab lists entries in the tree and renders the selected one", async () => {
    stubLists();
    renderPage();
    const tree = screen.getByRole("complementary");
    fireEvent.click(await within(tree).findByText("tabs"));
    expect(await screen.findByText("uses tabs over spaces")).toBeInTheDocument();
  });

  test("renders every lane tab plus the changelog view", async () => {
    stubLists();
    renderPage();
    expect(await screen.findByRole("tab", { name: "Entries" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Documents" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Rules" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Handoff" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Changelog" })).toBeInTheDocument();
  });

  test("switching to the Rules tab shows the rules lane (empty-state)", async () => {
    stubLists();
    renderPage();
    await selectTab("Rules");
    expect(await screen.findByText(/no rules yet/i)).toBeInTheDocument();
    await waitFor(() => expect(api.getKnowledgeRules).toHaveBeenCalledWith("global"));
  });

  test("switching to the Handoff tab shows the branch list", async () => {
    stubLists();
    vi.mocked(api.getKnowledgeHandoff).mockResolvedValue({
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
    vi.mocked(api.getConsolidationLog).mockResolvedValue({
      text: "merged 3 entries",
      path: "/p/consolidation-log.md",
      folder_path: "/p",
    });
    renderPage();
    await selectTab("Changelog");
    // The log is one row in the shared file-tree lane; select it to preview.
    // The row is the only button in the panel (vs. the list-header label text).
    const panel = await screen.findByRole("tabpanel");
    fireEvent.click(within(panel).getByRole("button", { name: /^Changelog$/ }));
    expect(await screen.findByText("merged 3 entries")).toBeInTheDocument();
  });

  test("recall (one query → one answer; no mode in the call) renders hits", async () => {
    stubLists();
    vi.mocked(api.recall).mockResolvedValue({
      hits: [{ id: "f1", text: "uses tabs over spaces", score: 0.9, source: "global", time: "t" }],
    });

    renderPage();
    const input = await screen.findByPlaceholderText(/recall entries/i);
    fireEvent.change(input, { target: { value: "tabs" } });
    fireEvent.click(screen.getByRole("button", { name: /^recall$/i }));

    await waitFor(() => expect(api.recall).toHaveBeenCalledWith("global", "tabs", { topK: 5 }));
  });

  test("recall filters the Entries tree to the hit entry and highlights the query", async () => {
    const spaces = { ...ENTRY, id: "f2", title: "spaces", text: "spaces are fine" };
    stubLists();
    vi.mocked(api.listEntries).mockResolvedValue({ entries: [ENTRY, spaces], total: 2 });
    vi.mocked(api.getScopeMetrics).mockResolvedValue(metrics(2));
    vi.mocked(api.recall).mockResolvedValue({
      hits: [{ id: "f1", text: "uses tabs", score: 0.9, source: "global:/x.md", time: "t" }],
    });
    vi.mocked(api.getEntry).mockResolvedValue(ENTRY);

    renderPage();
    const tree = screen.getByRole("complementary");
    await within(tree).findByText("tabs");
    expect(within(tree).getByText("spaces")).toBeInTheDocument();

    fireEvent.change(await screen.findByPlaceholderText(/recall entries/i), {
      target: { value: "tabs" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^recall$/i }));

    await waitFor(() => expect(api.getEntry).toHaveBeenCalledWith("global", "f1"));
    await waitFor(() => expect(within(tree).queryByText("spaces")).not.toBeInTheDocument());
    expect(within(tree).getByText("tabs")).toBeInTheDocument();
    expect(await screen.findByPlaceholderText(/find/i)).toHaveValue("tabs");
  });

  test("clearing the recall box restores the full entry list", async () => {
    const spaces = { ...ENTRY, id: "f2", title: "spaces", text: "spaces are fine" };
    stubLists();
    vi.mocked(api.listEntries).mockResolvedValue({ entries: [ENTRY, spaces], total: 2 });
    vi.mocked(api.getScopeMetrics).mockResolvedValue(metrics(2));
    vi.mocked(api.recall).mockResolvedValue({
      hits: [{ id: "f1", text: "uses tabs", score: 0.9, source: "global:/x.md", time: "t" }],
    });
    vi.mocked(api.getEntry).mockResolvedValue(ENTRY);

    renderPage();
    const tree = screen.getByRole("complementary");
    await within(tree).findByText("spaces");
    fireEvent.change(await screen.findByPlaceholderText(/recall entries/i), {
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

    fireEvent.change(await screen.findByPlaceholderText(/recall entries/i), {
      target: { value: "zzz" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^recall$/i }));

    expect(await within(tree).findByText(/no matches/i)).toBeInTheDocument();
    expect(within(tree).queryByText("tabs")).not.toBeInTheDocument();
  });

  test("a selected entry renders READ-ONLY: no Edit/Save controls", async () => {
    stubLists();
    renderPage();
    const tree = screen.getByRole("complementary");
    fireEvent.click(await within(tree).findByText("tabs"));
    expect(await screen.findByText("uses tabs over spaces")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^save$/i })).not.toBeInTheDocument();
  });

  // Spec 007 scenario (kept verbatim across the memory→knowledge merge): the
  // human-facing viewer is read-only and routes edits to the user's own editor
  // — it surfaces open/reveal affordances (daemon-backed), not an in-app editor.
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

  test("deleting a selected entry calls delete after confirming in the dialog", async () => {
    stubLists();
    vi.mocked(api.deleteEntry).mockResolvedValue(undefined);

    renderPage();
    const tree = screen.getByRole("complementary");
    fireEvent.click(await within(tree).findByText("tabs"));
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    const dialog = await screen.findByRole("dialog");
    expect(api.deleteEntry).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));
    await waitFor(() => expect(api.deleteEntry).toHaveBeenCalledWith("global", "f1"));
  });

  test("does NOT delete an entry when the confirm dialog is cancelled", async () => {
    stubLists();
    vi.mocked(api.deleteEntry).mockResolvedValue(undefined);

    renderPage();
    const tree = screen.getByRole("complementary");
    fireEvent.click(await within(tree).findByText("tabs"));
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /cancel/i }));
    expect(api.deleteEntry).not.toHaveBeenCalled();
  });

  test("surfaces a localized error when the metrics query fails", async () => {
    stubLists();
    vi.mocked(api.getScopeMetrics).mockRejectedValue(new ApiError("RESOURCE_NOT_FOUND", "nope"));

    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(/resource not found/i);
  });

  test("Entries tab renders every entry in one scrollable list (no in-UI pager)", async () => {
    // The list is fetched in ONE request at the API max page size and rendered
    // as a single scrollable list — no page-based pager.
    stubLists();
    const entries = Array.from({ length: 120 }, (_, i) => ({
      ...ENTRY,
      id: `f${i}`,
      title: `entry-${i}`,
    }));
    vi.mocked(api.listEntries).mockResolvedValue({ entries, total: 120 });
    vi.mocked(api.getScopeMetrics).mockResolvedValue(metrics(120));

    renderPage();
    const tree = screen.getByRole("complementary");
    expect(await within(tree).findByText("entry-0")).toBeVisible();
    expect(within(tree).getByText("entry-119")).toBeInTheDocument();
    await waitFor(() => expect(api.listEntries).toHaveBeenCalledWith("global", 200, 0));
    expect(within(tree).queryByRole("button", { name: /next/i })).toBeNull();
  });

  test("clear-all calls clearEntries after confirming in the dialog", async () => {
    stubLists();
    vi.mocked(api.clearEntries).mockResolvedValue(1);

    renderPage();
    const btn = await screen.findByRole("button", { name: /clear all/i });
    await waitFor(() => expect(btn).toBeEnabled());
    fireEvent.click(btn);
    const dialog = await screen.findByRole("dialog");
    expect(api.clearEntries).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: /clear all/i }));
    await waitFor(() => expect(api.clearEntries).toHaveBeenCalledWith("global"));
  });
});
