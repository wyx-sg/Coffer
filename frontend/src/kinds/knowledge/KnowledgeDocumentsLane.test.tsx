// frontend/src/kinds/knowledge/KnowledgeDocumentsLane.test.tsx
//
// Exercises the DOCUMENTS lane of the knowledge detail surface: the
// CLIENT-SIDE filter box (matches filenames as you type — no request, no
// button), the document tree fetched in one request, and the tree →
// READ-ONLY preview flow (select a doc on the left; the right pane renders the
// Markdown with FileActions + reconvert / delete, no in-app editing). The
// header actions that drive this lane — Upload, and Check sources / Settings
// behind the overflow menu — live on the page, so the whole page is rendered.
// The `./api` module is mocked so the component renders without a backend.

import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ApiError } from "@/lib/api/errors";
import { KnowledgeDetailPage } from "./KnowledgeDetailPage";
import type { KnowledgeConfigOut, ScopeMetrics, ScopeOut } from "./types";

vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  listDocuments: vi.fn(),
  getDocument: vi.fn(),
  getScope: vi.fn(),
  getScopeMetrics: vi.fn(),
  ingestDocument: vi.fn(),
  deleteDocument: vi.fn(),
  reconvertDocument: vi.fn(),
  reindexScope: vi.fn(),
  checkSources: vi.fn(),
  updateFromSource: vi.fn(),
  updateScopeConfig: vi.fn(),
  tidyScope: vi.fn(),
  listEntries: vi.fn(),
  getEntry: vi.fn(),
}));
const api = await import("./api");

const DOC = {
  id: "d1",
  kind: "knowledge",
  resource_name: "designs",
  title: "Deploys",
  source_mode: "converted" as const,
  content_sha256: "abc",
  project_id: "00000000000000000000000000",
  chunk_count: 3,
  metadata: {},
  created_at: "2026-05-29T00:00:00Z",
  updated_at: "2026-05-29T00:00:00Z",
};

const CONFIG: KnowledgeConfigOut = {
  retrieval_modes: ["keyword", "grep"],
  default_mode: "keyword",
  max_entry_chars: 8192,
  chunk_size: 1000,
  chunk_overlap: 100,
  max_document_bytes: 1048576,
  auto_update_sources: false,
};

// A NAMED collection: the scope a person creates deliberately, the one the
// former knowledge_base kind used to be.
const SCOPE: ScopeOut = {
  ref: "knowledge:designs",
  kind: "knowledge",
  name: "designs",
  scope: "named",
  project_id: "designs",
  description: null,
  config: CONFIG,
  enabled: true,
  entry_count: 0,
  document_count: 1,
  created_at: "2026-05-29T00:00:00Z",
  updated_at: "2026-05-29T00:00:00Z",
};

// Notes and documents are separate lanes with separate counts — the fixture
// keeps them distinct so no assertion can pass by summing them.
const metrics = (over: Partial<ScopeMetrics> = {}): ScopeMetrics => ({
  entry_count: 0,
  document_count: 1,
  chunk_count: 3,
  documents_degraded: 0,
  indexed_modes: ["keyword", "grep"],
  disk_bytes: 264,
  ...over,
});

function seedBaseQueries() {
  vi.mocked(api.listDocuments).mockResolvedValue({ documents: [DOC], total: 1 });
  vi.mocked(api.getScopeMetrics).mockResolvedValue(metrics());
  vi.mocked(api.getScope).mockResolvedValue(SCOPE);
  // The Notes lane mounts on its own tab; stub its read so the page mounts.
  vi.mocked(api.listEntries).mockResolvedValue({ entries: [], total: 0 });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/knowledge/designs"]}>
        <Routes>
          <Route path="/knowledge/:scope" element={<KnowledgeDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** The documents lane's tree; Documents is the default tab. */
async function documentsTree() {
  await screen.findByRole("tab", { name: "Documents" });
  return await screen.findByRole("complementary");
}

/** Open the header's overflow (⋯) menu, where Settings / Check sources / Reindex live. */
async function openOverflow() {
  fireEvent.click(await screen.findByRole("button", { name: /more actions/i }));
  return await screen.findByRole("menu");
}

afterEach(() => vi.clearAllMocks());

describe("Knowledge documents lane", () => {
  test("renders a back link and the document tree", async () => {
    seedBaseQueries();
    renderPage();
    expect(await screen.findByRole("button", { name: /back to knowledge/i })).toBeVisible();
    const tree = await documentsTree();
    expect(await within(tree).findByText("Deploys")).toBeVisible();
    // No degraded badge when documents_degraded is 0.
    expect(screen.queryByText(/pending vector embed/i)).toBeNull();
  });

  test("shows a degraded-embed notice when documents_degraded > 0", async () => {
    seedBaseQueries();
    vi.mocked(api.getScopeMetrics).mockResolvedValue(metrics({ documents_degraded: 2 }));
    renderPage();
    expect(await screen.findByText(/pending vector embed/i)).toBeVisible();
  });

  test("the filter box narrows the tree client-side, with no request", async () => {
    seedBaseQueries();
    vi.mocked(api.listDocuments).mockResolvedValue({
      documents: [
        { ...DOC, id: "d1", title: "Deploys" },
        { ...DOC, id: "d2", title: "Runbook" },
      ],
      total: 2,
    });
    renderPage();

    const tree = await documentsTree();
    await within(tree).findByText("Deploys");
    expect(within(tree).getByText("Runbook")).toBeInTheDocument();

    const listCallsBefore = vi.mocked(api.listDocuments).mock.calls.length;
    fireEvent.change(screen.getByPlaceholderText(/filter by name/i), {
      target: { value: "run" },
    });

    expect(within(tree).queryByText("Deploys")).not.toBeInTheDocument();
    expect(within(tree).getByText("Runbook")).toBeInTheDocument();
    // Purely local: nothing is refetched and no retrieval button exists.
    expect(vi.mocked(api.listDocuments).mock.calls).toHaveLength(listCallsBefore);
    expect(screen.queryByRole("button", { name: /^search$/i })).not.toBeInTheDocument();
  });

  test("a filter matching nothing shows the no-matches label and an empty tree", async () => {
    seedBaseQueries();
    renderPage();
    const tree = await documentsTree();
    await within(tree).findByText("Deploys");

    fireEvent.change(screen.getByPlaceholderText(/filter by name/i), {
      target: { value: "zzz" },
    });

    expect(within(tree).getByText(/no matches/i)).toBeInTheDocument();
    expect(within(tree).queryByText("Deploys")).not.toBeInTheDocument();
  });

  test("selecting a document renders its markdown READ-ONLY with file affordances", async () => {
    seedBaseQueries();
    vi.mocked(api.getDocument).mockResolvedValue({
      ...DOC,
      markdown: "# Deploys\n\nbody",
      path: "/abs/knowledge/designs/docs/deploys.md",
      folder_path: "/abs/knowledge/designs/docs",
    });
    renderPage();

    const tree = await documentsTree();
    fireEvent.click(await within(tree).findByText("Deploys"));
    // Viewing renders the Markdown: the body text is shown (the raw "# " is gone).
    expect(await screen.findByText("body")).toBeVisible();

    // There is no in-app editing — no Edit/Save controls.
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^save$/i })).not.toBeInTheDocument();
    // The read-only viewer offers real open/reveal affordances (daemon-backed on web).
    expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reveal/i })).toBeInTheDocument();
  });

  test("deleting a selected document calls delete after confirmation", async () => {
    seedBaseQueries();
    vi.mocked(api.getDocument).mockResolvedValue({ ...DOC, markdown: "body" });
    vi.mocked(api.deleteDocument).mockResolvedValue(undefined);
    renderPage();

    const tree = await documentsTree();
    fireEvent.click(await within(tree).findByText("Deploys"));
    // The viewer's delete button opens a styled confirmation dialog (no native
    // window.confirm); the delete only fires after confirming inside it.
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));
    await waitFor(() => expect(api.deleteDocument).toHaveBeenCalledWith("designs", "d1"));
  });

  test("does not delete when the confirm is cancelled", async () => {
    seedBaseQueries();
    vi.mocked(api.getDocument).mockResolvedValue({ ...DOC, markdown: "body" });
    renderPage();

    const tree = await documentsTree();
    fireEvent.click(await within(tree).findByText("Deploys"));
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^cancel$/i }));
    expect(api.deleteDocument).not.toHaveBeenCalled();
  });

  test("renders all documents in one scrollable list (no in-UI pager)", async () => {
    // The list is fetched in ONE request at the API max page size and rendered
    // as a single scrollable list — no page-based pager.
    seedBaseQueries();
    const docs = Array.from({ length: 120 }, (_, i) => ({
      ...DOC,
      id: `d${i}`,
      title: `doc-${i}`,
    }));
    vi.mocked(api.listDocuments).mockResolvedValue({ documents: docs, total: 120 });
    vi.mocked(api.getScopeMetrics).mockResolvedValue(metrics({ document_count: 120 }));

    renderPage();
    const tree = await documentsTree();
    // The whole list renders (first AND last row) from a single fetch.
    expect(await within(tree).findByText("doc-0")).toBeVisible();
    expect(within(tree).getByText("doc-119")).toBeInTheDocument();
    // Fetched once at the API max (limit 200, offset 0); no pager rendered.
    await waitFor(() => expect(api.listDocuments).toHaveBeenCalledWith("designs", 200, 0));
    expect(within(tree).queryByRole("button", { name: /next/i })).toBeNull();
  });

  test("a duplicate upload surfaces an inline error", async () => {
    seedBaseQueries();
    vi.mocked(api.ingestDocument).mockRejectedValue(new ApiError("INGEST_REJECTED", "duplicate"));
    renderPage();
    await documentsTree();
    const file = new File(["x"], "a.md", { type: "text/markdown" });
    const inputs = document.querySelectorAll('input[type="file"]');
    fireEvent.change(inputs[inputs.length - 1], { target: { files: [file] } });
    expect(await screen.findByText(/duplicate/i)).toBeVisible();
  });

  test("Check sources calls the API and opens the report dialog", async () => {
    seedBaseQueries();
    vi.mocked(api.checkSources).mockResolvedValue({
      sources: [
        { document_id: "d1", title: "Deploys", source_path: "/abs/deploys.md", status: "changed" },
      ],
    });
    renderPage();
    // Check sources lives behind the header's overflow menu now.
    await documentsTree();
    const menu = await openOverflow();
    fireEvent.click(within(menu).getByRole("menuitem", { name: /check sources/i }));
    await waitFor(() => expect(api.checkSources).toHaveBeenCalledWith("designs"));
    // The report dialog opens with the changed row + its Update action.
    expect(await screen.findByText(/source files/i)).toBeVisible();
    expect(screen.getByRole("button", { name: /update from source/i })).toBeVisible();
  });

  test("updating a changed source re-runs the check so the report isn't stale", async () => {
    seedBaseQueries();
    // First scan reports a changed source; after the update, a re-scan reports
    // it unchanged — the load-bearing refresh that keeps the dialog accurate.
    vi.mocked(api.checkSources)
      .mockResolvedValueOnce({
        sources: [
          {
            document_id: "d1",
            title: "Deploys",
            source_path: "/abs/deploys.md",
            status: "changed",
          },
        ],
      })
      .mockResolvedValueOnce({
        sources: [
          {
            document_id: "d1",
            title: "Deploys",
            source_path: "/abs/deploys.md",
            status: "unchanged",
          },
        ],
      });
    vi.mocked(api.updateFromSource).mockResolvedValue(DOC);
    renderPage();

    await documentsTree();
    const menu = await openOverflow();
    fireEvent.click(within(menu).getByRole("menuitem", { name: /check sources/i }));
    const updateBtn = await screen.findByRole("button", { name: /update from source/i });
    fireEvent.click(updateBtn);

    await waitFor(() => expect(api.updateFromSource).toHaveBeenCalledWith("designs", "d1"));
    // The hook re-runs check-sources on update success → the report refreshes.
    await waitFor(() => expect(api.checkSources).toHaveBeenCalledTimes(2));
  });

  test("clicking a row title still loads it in the viewer (the e2e-critical path)", async () => {
    seedBaseQueries();
    vi.mocked(api.getDocument).mockResolvedValue({
      ...DOC,
      markdown: "# Deploys\n\nbody",
      path: "/abs/knowledge/designs/docs/deploys.md",
      folder_path: "/abs/knowledge/designs/docs",
    });
    renderPage();

    const tree = await documentsTree();
    // The title is a clickable element selectable by its TEXT (not the checkbox).
    fireEvent.click(await within(tree).findByText("Deploys"));
    expect(await screen.findByText("body")).toBeVisible();
    await waitFor(() => expect(api.getDocument).toHaveBeenCalledWith("designs", "d1"));
  });

  test("the settings PATCH sends auto_update_sources (guards the reset gotcha)", async () => {
    seedBaseQueries();
    vi.mocked(api.updateScopeConfig).mockResolvedValue(SCOPE);
    renderPage();

    await documentsTree();
    const menu = await openOverflow();
    fireEvent.click(within(menu).getByRole("menuitem", { name: /^settings$/i }));
    const dialog = await screen.findByRole("dialog");
    // Flip the auto-update switch on, then save.
    fireEvent.click(within(dialog).getByLabelText(/auto-update from source/i));
    fireEvent.click(within(dialog).getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(api.updateScopeConfig).toHaveBeenCalled());
    const sentPatch = vi.mocked(api.updateScopeConfig).mock.calls[0][1];
    expect(sentPatch).toHaveProperty("auto_update_sources", true);
    // Embedding is installation-wide now: a per-scope patch must never carry it.
    expect(Object.keys(sentPatch).some((k) => k.startsWith("embedding"))).toBe(false);
  });
});
