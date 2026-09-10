// frontend/src/kinds/knowledge/KnowledgeDetailPage.test.tsx
//
// Exercises the knowledge-scope detail surface after the two-lane redesign:
// a Tabs shell with EXACTLY two tabs — Documents and Notes — over a header
// that carries Upload + Tidy and hides Settings / Check sources / Reindex
// behind the overflow menu. The Notes lane is a list → a READ-ONLY preview
// (select a note on the left; the right pane renders the Markdown with
// FileActions + delete, no in-app editing) narrowed by a CLIENT-SIDE filter
// box that matches filenames as you type — no request, no button. The
// Documents lane has its own test file. The `./api` module is mocked so the
// component renders without a backend.

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
  addEntry: vi.fn(),
  deleteEntry: vi.fn(),
  clearEntries: vi.fn(),
  tidyScope: vi.fn(),
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
  path: "/abs/knowledge/global/notes/tabs-f1.md",
  folder_path: "/abs/knowledge/global/notes",
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

/** Open the Notes tab and return its tree (the lane's <aside>). */
async function openNotes() {
  await selectTab("Notes");
  const panel = await screen.findByRole("tabpanel");
  return within(panel).getByRole("complementary");
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
// a test can never pass by summing notes and documents into one number.
const metrics = (entries: number, degraded = 0) => ({
  entry_count: entries,
  document_count: 0,
  chunk_count: 0,
  documents_degraded: degraded,
  indexed_modes: ["grep", "keyword"] as ("grep" | "keyword")[],
  disk_bytes: 50,
});

function stubLists() {
  vi.mocked(api.listEntries).mockResolvedValue({ entries: [ENTRY], total: 1 });
  vi.mocked(api.getEntry).mockResolvedValue(ENTRY);
  vi.mocked(api.getScopeMetrics).mockResolvedValue(metrics(1));
  // The page always mounts the documents hook (the header's Upload / Tidy /
  // overflow actions drive it), so its list read is stubbed even though the
  // Documents lane has its own test file.
  vi.mocked(api.listDocuments).mockResolvedValue({ documents: [], total: 0 });
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

describe("KnowledgeDetailPage — the two-lane shell", () => {
  test("has exactly two tabs, Documents and Notes", async () => {
    stubLists();
    renderPage();
    expect(await screen.findByRole("tab", { name: "Documents" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Notes" })).toBeInTheDocument();
    expect(screen.getAllByRole("tab")).toHaveLength(2);
  });

  test("the retired lanes have no tab left", async () => {
    stubLists();
    renderPage();
    await screen.findByRole("tab", { name: "Documents" });
    for (const gone of ["Rules", "Handoff", "Changelog", "Entries"]) {
      expect(screen.queryByRole("tab", { name: gone })).not.toBeInTheDocument();
    }
  });

  test("Notes tab lists notes in the tree and renders the selected one", async () => {
    stubLists();
    renderPage();
    const tree = await openNotes();
    fireEvent.click(await within(tree).findByText("tabs"));
    expect(await screen.findByText("uses tabs over spaces")).toBeInTheDocument();
  });
});

describe("KnowledgeDetailPage — the client-side filter", () => {
  const spaces = {
    ...ENTRY,
    id: "f2",
    title: "spaces",
    text: "spaces are fine",
    path: "/abs/knowledge/global/notes/spaces-f2.md",
  };

  test("typing narrows the note list without any server request", async () => {
    stubLists();
    vi.mocked(api.listEntries).mockResolvedValue({ entries: [ENTRY, spaces], total: 2 });
    vi.mocked(api.getScopeMetrics).mockResolvedValue(metrics(2));

    renderPage();
    const tree = await openNotes();
    await within(tree).findByText("tabs");
    expect(within(tree).getByText("spaces")).toBeInTheDocument();

    const listCallsBefore = vi.mocked(api.listEntries).mock.calls.length;
    fireEvent.change(screen.getAllByPlaceholderText(/filter by name/i)[0], {
      target: { value: "spa" },
    });

    expect(within(tree).queryByText("tabs")).not.toBeInTheDocument();
    expect(within(tree).getByText("spaces")).toBeInTheDocument();
    // Purely local: no refetch, and there is no retrieval mutation to call.
    expect(vi.mocked(api.listEntries).mock.calls).toHaveLength(listCallsBefore);
    expect(api.getEntry).not.toHaveBeenCalled();
  });

  test("the filter matches the on-disk filename as well as the title", async () => {
    stubLists();
    vi.mocked(api.listEntries).mockResolvedValue({ entries: [ENTRY, spaces], total: 2 });

    renderPage();
    const tree = await openNotes();
    await within(tree).findByText("tabs");
    // "tabs-f1.md" is the basename of the first note only.
    fireEvent.change(screen.getAllByPlaceholderText(/filter by name/i)[0], {
      target: { value: "f1.md" },
    });
    expect(within(tree).getByText("tabs")).toBeInTheDocument();
    expect(within(tree).queryByText("spaces")).not.toBeInTheDocument();
  });

  test("clearing the filter restores the full note list", async () => {
    stubLists();
    vi.mocked(api.listEntries).mockResolvedValue({ entries: [ENTRY, spaces], total: 2 });

    renderPage();
    const tree = await openNotes();
    await within(tree).findByText("spaces");
    const box = screen.getAllByPlaceholderText(/filter by name/i)[0];
    fireEvent.change(box, { target: { value: "tabs" } });
    expect(within(tree).queryByText("spaces")).not.toBeInTheDocument();

    fireEvent.change(box, { target: { value: "" } });
    expect(within(tree).getByText("spaces")).toBeInTheDocument();
  });

  test("a filter matching nothing shows the no-matches label and an empty tree", async () => {
    stubLists();
    renderPage();
    const tree = await openNotes();
    await within(tree).findByText("tabs");

    fireEvent.change(screen.getAllByPlaceholderText(/filter by name/i)[0], {
      target: { value: "zzz" },
    });
    expect(within(tree).getByText(/no matches/i)).toBeInTheDocument();
    expect(within(tree).queryByText("tabs")).not.toBeInTheDocument();
  });

  test("there is no retrieval button next to the filter box", async () => {
    stubLists();
    renderPage();
    await openNotes();
    expect(screen.queryByRole("button", { name: /^recall$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^search$/i })).not.toBeInTheDocument();
  });
});

describe("KnowledgeDetailPage — the header", () => {
  test("Tidy triggers the manual tidy pass", async () => {
    stubLists();
    vi.mocked(api.tidyScope).mockResolvedValue({ status: "ok" });

    renderPage();
    const btn = await screen.findByRole("button", { name: /^tidy$/i });
    await waitFor(() => expect(btn).toBeEnabled());
    fireEvent.click(btn);
    await waitFor(() => expect(api.tidyScope).toHaveBeenCalledWith("global"));
  });

  test("Settings / Check sources / Reindex live behind the overflow menu", async () => {
    stubLists();
    renderPage();
    await screen.findByRole("button", { name: /^upload$/i });
    // Not on the header itself…
    expect(screen.queryByRole("button", { name: /^settings$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /check sources/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^reindex$/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /more actions/i }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByRole("menuitem", { name: /^settings$/i })).toBeInTheDocument();
    expect(within(menu).getByRole("menuitem", { name: /check sources/i })).toBeInTheDocument();
    expect(within(menu).getByRole("menuitem", { name: /^reindex$/i })).toBeInTheDocument();
  });

  test("shows no metrics badges — only the degraded warning, and only when there is one", async () => {
    stubLists();
    renderPage();
    await screen.findByRole("button", { name: /^upload$/i });
    // Chunk counts, byte sizes, index modes and the two lane counts are gone.
    expect(screen.queryByText(/chunk/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/\d+ B$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/pending vector embed/i)).not.toBeInTheDocument();
  });

  test("renders the degraded-documents warning when the count is above zero", async () => {
    stubLists();
    vi.mocked(api.getScopeMetrics).mockResolvedValue(metrics(1, 3));
    renderPage();
    expect(await screen.findByText(/pending vector embed/i)).toBeInTheDocument();
  });

  test("surfaces a localized error when the metrics query fails", async () => {
    stubLists();
    vi.mocked(api.getScopeMetrics).mockRejectedValue(new ApiError("RESOURCE_NOT_FOUND", "nope"));

    renderPage();
    // Both the page header and the documents lane surface the failure.
    const alerts = await screen.findAllByRole("alert");
    expect(alerts.some((a) => /resource not found/i.test(a.textContent ?? ""))).toBe(true);
  });
});

describe("KnowledgeDetailPage — the Notes lane", () => {
  test("a selected note renders READ-ONLY: no Edit/Save controls", async () => {
    stubLists();
    renderPage();
    const tree = await openNotes();
    fireEvent.click(await within(tree).findByText("tabs"));
    expect(await screen.findByText("uses tabs over spaces")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^save$/i })).not.toBeInTheDocument();
  });

  // Knowledge spec scenario (kept verbatim across the memory→knowledge merge): the
  // human-facing viewer is read-only and routes edits to the user's own editor
  // — it surfaces open/reveal affordances (daemon-backed), not an in-app editor.
  acceptance("knowledge", "read-only viewer offers open/reveal affordances", async () => {
    stubLists();
    renderPage();
    const tree = await openNotes();
    fireEvent.click(await within(tree).findByText("tabs"));
    await screen.findByText("uses tabs over spaces");
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reveal/i })).toBeInTheDocument();
  });

  test("deleting a selected note calls delete after confirming in the dialog", async () => {
    stubLists();
    vi.mocked(api.deleteEntry).mockResolvedValue(undefined);

    renderPage();
    const tree = await openNotes();
    fireEvent.click(await within(tree).findByText("tabs"));
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    const dialog = await screen.findByRole("dialog");
    expect(api.deleteEntry).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));
    await waitFor(() => expect(api.deleteEntry).toHaveBeenCalledWith("global", "f1"));
  });

  test("does NOT delete a note when the confirm dialog is cancelled", async () => {
    stubLists();
    vi.mocked(api.deleteEntry).mockResolvedValue(undefined);

    renderPage();
    const tree = await openNotes();
    fireEvent.click(await within(tree).findByText("tabs"));
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /cancel/i }));
    expect(api.deleteEntry).not.toHaveBeenCalled();
  });

  test("renders every note in one scrollable list (no in-UI pager)", async () => {
    // The list is fetched in ONE request at the API max page size and rendered
    // as a single scrollable list — no page-based pager.
    stubLists();
    const entries = Array.from({ length: 120 }, (_, i) => ({
      ...ENTRY,
      id: `f${i}`,
      title: `note-${i}`,
    }));
    vi.mocked(api.listEntries).mockResolvedValue({ entries, total: 120 });
    vi.mocked(api.getScopeMetrics).mockResolvedValue(metrics(120));

    renderPage();
    const tree = await openNotes();
    expect(await within(tree).findByText("note-0")).toBeVisible();
    expect(within(tree).getByText("note-119")).toBeInTheDocument();
    await waitFor(() => expect(api.listEntries).toHaveBeenCalledWith("global", 200, 0));
    expect(within(tree).queryByRole("button", { name: /next/i })).toBeNull();
  });

  test("clear-all calls clearEntries after confirming in the dialog", async () => {
    stubLists();
    vi.mocked(api.clearEntries).mockResolvedValue(1);

    renderPage();
    await openNotes();
    const btn = await screen.findByRole("button", { name: /clear all/i });
    await waitFor(() => expect(btn).toBeEnabled());
    fireEvent.click(btn);
    const dialog = await screen.findByRole("dialog");
    expect(api.clearEntries).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: /clear all/i }));
    await waitFor(() => expect(api.clearEntries).toHaveBeenCalledWith("global"));
  });
});
