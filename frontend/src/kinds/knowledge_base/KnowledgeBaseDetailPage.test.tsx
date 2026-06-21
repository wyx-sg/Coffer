// frontend/src/kinds/knowledge_base/KnowledgeBaseDetailPage.test.tsx
//
// Exercises the redesigned KB detail surface: the retrieval bar (one input +
// Search; "one query → one answer", no mode picker / grep / fallback), the
// page-paginated document tree with a SERVER-SIDE title filter (`q`), and the
// document tree → READ-ONLY preview flow (select a doc on the left; the right
// pane renders the Markdown with FileActions + reconvert / delete, no in-app
// editing). The `./api` module is mocked so the component renders without a
// backend.

import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ApiError } from "@/lib/api/errors";
import { KnowledgeBaseDetailPage } from "./KnowledgeBaseDetailPage";

vi.mock("./api", () => ({
  listDocuments: vi.fn(),
  getDocument: vi.fn(),
  getKnowledgeBase: vi.fn(),
  getKnowledgeBaseMetrics: vi.fn(),
  ingestDocument: vi.fn(),
  deleteDocument: vi.fn(),
  reconvertDocument: vi.fn(),
  reindexKnowledgeBase: vi.fn(),
  checkSources: vi.fn(),
  updateFromSource: vi.fn(),
  searchKnowledgeBase: vi.fn(),
  updateKnowledgeBaseConfig: vi.fn(),
}));
const api = await import("./api");

const DOC = {
  id: "d1",
  kind: "knowledge_base",
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

const KB = {
  ref: "knowledge_base:designs",
  kind: "knowledge_base",
  name: "designs",
  description: null,
  config: {
    enabled_modes: ["keyword", "grep"] as ("keyword" | "grep" | "vector")[],
    default_mode: "keyword" as const,
    chunk_size: 1000,
    chunk_overlap: 100,
    max_document_bytes: 1048576,
    embedding: null,
    auto_update_sources: false,
  },
  enabled: true,
  created_at: "2026-05-29T00:00:00Z",
  updated_at: "2026-05-29T00:00:00Z",
};

function seedBaseQueries() {
  vi.mocked(api.listDocuments).mockResolvedValue({ documents: [DOC], total: 1 });
  vi.mocked(api.getKnowledgeBaseMetrics).mockResolvedValue({
    document_count: 1,
    chunk_count: 3,
    documents_degraded: 0,
    indexed_modes: ["keyword", "grep"],
    disk_bytes: 264,
  });
  vi.mocked(api.getKnowledgeBase).mockResolvedValue(KB);
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/knowledge-bases/designs"]}>
        <Routes>
          <Route path="/knowledge-bases/:name" element={<KnowledgeBaseDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("KnowledgeBaseDetailPage", () => {
  test("renders a back link, metric badges, and the document tree", async () => {
    seedBaseQueries();
    renderPage();
    expect(await screen.findByRole("button", { name: /back to knowledge bases/i })).toBeVisible();
    const tree = screen.getByRole("complementary");
    expect(await within(tree).findByText("Deploys")).toBeVisible();
    // No degraded badge when documents_degraded is 0.
    expect(screen.queryByText(/pending vector embed/i)).toBeNull();
  });

  test("shows a degraded-embed notice when documents_degraded > 0", async () => {
    seedBaseQueries();
    vi.mocked(api.getKnowledgeBaseMetrics).mockResolvedValue({
      document_count: 1,
      chunk_count: 3,
      documents_degraded: 2,
      indexed_modes: ["keyword", "grep"],
      disk_bytes: 264,
    });
    renderPage();
    expect(await screen.findByText(/pending vector embed/i)).toBeVisible();
  });

  test("searching filters the tree to the hit doc and highlights the query in the viewer", async () => {
    seedBaseQueries();
    vi.mocked(api.listDocuments).mockResolvedValue({
      documents: [
        { ...DOC, id: "d1", title: "Deploys" },
        { ...DOC, id: "d2", title: "Runbook" },
      ],
      total: 2,
    });
    vi.mocked(api.searchKnowledgeBase).mockResolvedValue({
      passages: [
        { text: "make release", document_id: "d1", title: "Deploys", score: 0.9, position: 0 },
      ],
    });
    vi.mocked(api.getDocument).mockResolvedValue({
      ...DOC,
      id: "d1",
      title: "Deploys",
      markdown: "make a release build",
    });
    renderPage();

    const tree = screen.getByRole("complementary");
    await within(tree).findByText("Deploys");
    expect(within(tree).getByText("Runbook")).toBeInTheDocument();

    fireEvent.change(await screen.findByPlaceholderText(/search this knowledge base/i), {
      target: { value: "release" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^search$/i }));

    await waitFor(() =>
      expect(api.searchKnowledgeBase).toHaveBeenCalledWith("designs", "release", { topK: 5 }),
    );
    // The tree filters to the hit doc; the non-hit drops out.
    await waitFor(() => expect(within(tree).queryByText("Runbook")).not.toBeInTheDocument());
    expect(within(tree).getByText("Deploys")).toBeInTheDocument();
    // The top hit auto-opens with the query pre-seeded into the find widget.
    expect(await screen.findByPlaceholderText(/find/i)).toHaveValue("release");
  });

  test("a search with no hits shows the no-matches label and an empty tree", async () => {
    seedBaseQueries();
    vi.mocked(api.searchKnowledgeBase).mockResolvedValue({ passages: [] });
    renderPage();
    const tree = screen.getByRole("complementary");
    await within(tree).findByText("Deploys");

    fireEvent.change(await screen.findByPlaceholderText(/search this knowledge base/i), {
      target: { value: "zzz" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^search$/i }));

    expect(await within(tree).findByText(/no matches/i)).toBeInTheDocument();
    expect(within(tree).queryByText("Deploys")).not.toBeInTheDocument();
  });

  test("selecting a document renders its markdown READ-ONLY with file affordances", async () => {
    seedBaseQueries();
    vi.mocked(api.getDocument).mockResolvedValue({
      ...DOC,
      markdown: "# Deploys\n\nbody",
      path: "/abs/kb/designs/deploys.md",
      folder_path: "/abs/kb/designs",
    });
    renderPage();

    const tree = screen.getByRole("complementary");
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

    const tree = screen.getByRole("complementary");
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

    const tree = screen.getByRole("complementary");
    fireEvent.click(await within(tree).findByText("Deploys"));
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^cancel$/i }));
    expect(api.deleteDocument).not.toHaveBeenCalled();
  });

  test("renders all documents in one scrollable list (no in-UI pager)", async () => {
    // The list is fetched in ONE request at the API max page size and rendered
    // as a single scrollable list — no page-based pager.
    const docs = Array.from({ length: 120 }, (_, i) => ({
      ...DOC,
      id: `d${i}`,
      title: `doc-${i}`,
    }));
    vi.mocked(api.listDocuments).mockResolvedValue({ documents: docs, total: 120 });
    vi.mocked(api.getKnowledgeBaseMetrics).mockResolvedValue({
      document_count: 120,
      chunk_count: 3,
      documents_degraded: 0,
      indexed_modes: ["keyword", "grep"],
      disk_bytes: 264,
    });
    vi.mocked(api.getKnowledgeBase).mockResolvedValue(KB);

    renderPage();
    const tree = screen.getByRole("complementary");
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
    await screen.findByRole("button", { name: /back to knowledge bases/i });
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
    const checkBtn = await screen.findByRole("button", { name: /check sources/i });
    // The button is disabled until the KB resource query resolves.
    await waitFor(() => expect(checkBtn).not.toBeDisabled());
    fireEvent.click(checkBtn);
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

    const checkBtn = await screen.findByRole("button", { name: /check sources/i });
    await waitFor(() => expect(checkBtn).not.toBeDisabled());
    fireEvent.click(checkBtn);
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
      path: "/abs/kb/designs/deploys.md",
      folder_path: "/abs/kb/designs",
    });
    renderPage();

    const tree = screen.getByRole("complementary");
    // The title is a clickable element selectable by its TEXT (not the checkbox).
    fireEvent.click(await within(tree).findByText("Deploys"));
    expect(await screen.findByText("body")).toBeVisible();
    await waitFor(() => expect(api.getDocument).toHaveBeenCalledWith("designs", "d1"));
  });

  test("the settings PATCH carries auto_update_sources (guards the reset gotcha)", async () => {
    seedBaseQueries();
    vi.mocked(api.getKnowledgeBase).mockResolvedValue({
      ...KB,
      config: { ...KB.config, auto_update_sources: false },
    });
    vi.mocked(api.updateKnowledgeBaseConfig).mockResolvedValue(KB);
    renderPage();

    const settingsBtn = await screen.findByRole("button", { name: /^settings$/i });
    await waitFor(() => expect(settingsBtn).not.toBeDisabled());
    fireEvent.click(settingsBtn);
    const dialog = await screen.findByRole("dialog");
    // Flip the auto-update switch on, then save.
    fireEvent.click(within(dialog).getByLabelText(/auto-update from source/i));
    fireEvent.click(within(dialog).getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(api.updateKnowledgeBaseConfig).toHaveBeenCalled());
    const sentConfig = vi.mocked(api.updateKnowledgeBaseConfig).mock.calls[0][1];
    expect(sentConfig).toHaveProperty("auto_update_sources", true);
  });
});
