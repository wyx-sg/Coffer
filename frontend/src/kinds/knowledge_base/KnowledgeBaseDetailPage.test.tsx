// frontend/src/kinds/knowledge_base/KnowledgeBaseDetailPage.test.tsx
//
// Exercises the redesigned KB detail surface: the unified retrieval bar
// (one input + a keyword/vector/grep mode dropdown), and the document tree →
// READ-ONLY preview flow (select a doc on the left; the right pane renders the
// Markdown with FileActions + reconvert / delete, no in-app editing). The
// `./api` module is mocked so the component renders without a backend.

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
  grepKnowledgeBase: vi.fn(),
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

  test("the unified bar searches with the selected mode", async () => {
    seedBaseQueries();
    vi.mocked(api.searchKnowledgeBase).mockResolvedValue({
      mode: "keyword",
      fallback: null,
      passages: [
        { text: "make release", document_id: "d1", title: "Deploys", score: 0.9, position: 0 },
      ],
    });
    renderPage();
    fireEvent.change(await screen.findByPlaceholderText(/search this knowledge base/i), {
      target: { value: "release" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^search$/i }));
    await waitFor(() =>
      expect(api.searchKnowledgeBase).toHaveBeenCalledWith("designs", "release", {
        topK: 5,
        mode: "keyword",
      }),
    );
    expect(await screen.findByText(/make release/)).toBeVisible();
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

  test("grep mode calls the grep helper", async () => {
    seedBaseQueries();
    vi.mocked(api.grepKnowledgeBase).mockResolvedValue({
      hits: [{ path: "d1.md", line_number: 2, line: "needle" }],
      truncated: false,
    });
    renderPage();
    fireEvent.click(await screen.findByRole("combobox"));
    fireEvent.click(await screen.findByRole("option", { name: "Grep" }));
    fireEvent.change(screen.getByPlaceholderText(/pattern/i), { target: { value: "needle" } });
    fireEvent.click(screen.getByRole("button", { name: /^search$/i }));
    await waitFor(() =>
      expect(api.grepKnowledgeBase).toHaveBeenCalledWith("designs", "needle", 100),
    );
    expect(await screen.findByText("needle")).toBeVisible();
  });

  test("shows a load-more affordance and fetches the next page when over the page size", async () => {
    // 100 docs loaded, but the KB has 150 — the cap must not silently hide the
    // rest. A "Load more" button shows the loaded/total split and, on click,
    // re-queries with a larger limit so the remaining docs become reachable.
    const page1 = Array.from({ length: 100 }, (_, i) => ({
      ...DOC,
      id: `d${i}`,
      title: `doc-${i}`,
    }));
    const page2 = Array.from({ length: 150 }, (_, i) => ({
      ...DOC,
      id: `d${i}`,
      title: `doc-${i}`,
    }));
    vi.mocked(api.listDocuments).mockImplementation(async (_kb, limit) =>
      (limit ?? 0) > 100 ? { documents: page2, total: 150 } : { documents: page1, total: 150 },
    );
    vi.mocked(api.getKnowledgeBaseMetrics).mockResolvedValue({
      document_count: 150,
      chunk_count: 3,
      documents_degraded: 0,
      indexed_modes: ["keyword", "grep"],
      disk_bytes: 264,
    });
    vi.mocked(api.getKnowledgeBase).mockResolvedValue(KB);

    renderPage();
    const loadMore = await screen.findByRole("button", { name: /showing 100 of 150/i });
    expect(loadMore).toBeVisible();
    expect(await screen.findByText("doc-99")).toBeVisible();

    fireEvent.click(loadMore);
    await waitFor(() => expect(api.listDocuments).toHaveBeenCalledWith("designs", 200, 0));
    expect(await screen.findByText("doc-149")).toBeVisible();
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
          { document_id: "d1", title: "Deploys", source_path: "/abs/deploys.md", status: "changed" },
        ],
      })
      .mockResolvedValueOnce({
        sources: [
          { document_id: "d1", title: "Deploys", source_path: "/abs/deploys.md", status: "unchanged" },
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

  test("the doc filter narrows the visible rows by title and restores on clear", async () => {
    seedBaseQueries();
    vi.mocked(api.listDocuments).mockResolvedValue({
      documents: [
        { ...DOC, id: "d1", title: "Deploys" },
        { ...DOC, id: "d2", title: "Runbook" },
      ],
      total: 2,
    });
    renderPage();

    const tree = screen.getByRole("complementary");
    expect(await within(tree).findByText("Deploys")).toBeVisible();
    expect(within(tree).getByText("Runbook")).toBeVisible();

    const filter = within(tree).getByPlaceholderText(/filter documents/i);
    fireEvent.change(filter, { target: { value: "run" } });
    // Case-insensitive title substring: only Runbook survives.
    expect(within(tree).queryByText("Deploys")).toBeNull();
    expect(within(tree).getByText("Runbook")).toBeVisible();

    // A filter that matches nothing shows the muted no-matches line.
    fireEvent.change(filter, { target: { value: "zzz" } });
    expect(within(tree).getByText(/no documents match the filter/i)).toBeVisible();

    // Clearing the filter restores every row.
    fireEvent.change(filter, { target: { value: "" } });
    expect(within(tree).getByText("Deploys")).toBeVisible();
    expect(within(tree).getByText("Runbook")).toBeVisible();
  });

  test("selecting two rows shows the bulk bar and bulk-deletes after confirm", async () => {
    seedBaseQueries();
    vi.mocked(api.listDocuments).mockResolvedValue({
      documents: [
        { ...DOC, id: "d1", title: "Deploys" },
        { ...DOC, id: "d2", title: "Runbook" },
      ],
      total: 2,
    });
    vi.mocked(api.deleteDocument).mockResolvedValue(undefined);
    renderPage();

    const tree = screen.getByRole("complementary");
    await within(tree).findByText("Deploys");
    // Each row carries a "Select row" checkbox sibling of the title button.
    const rowChecks = within(tree).getAllByLabelText(/select row/i);
    expect(rowChecks).toHaveLength(2);
    fireEvent.click(rowChecks[0]);
    fireEvent.click(rowChecks[1]);

    // The bulk bar reports the selected count and offers Delete.
    expect(within(tree).getByText(/2 selected/i)).toBeVisible();
    fireEvent.click(within(tree).getByRole("button", { name: /^delete$/i }));

    // Confirm dialog → on confirm, deleteDocument fires once per selected id.
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));
    await waitFor(() => expect(api.deleteDocument).toHaveBeenCalledWith("designs", "d1"));
    await waitFor(() => expect(api.deleteDocument).toHaveBeenCalledWith("designs", "d2"));
    expect(api.deleteDocument).toHaveBeenCalledTimes(2);
    // Selection clears: the bulk bar disappears.
    await waitFor(() => expect(within(tree).queryByText(/2 selected/i)).toBeNull());
  });

  test("bulk-deleting the currently-viewed document resets the viewer", async () => {
    seedBaseQueries();
    vi.mocked(api.listDocuments).mockResolvedValue({
      documents: [
        { ...DOC, id: "d1", title: "Deploys" },
        { ...DOC, id: "d2", title: "Runbook" },
      ],
      total: 2,
    });
    vi.mocked(api.getDocument).mockResolvedValue({ ...DOC, id: "d1", markdown: "viewed-body" });
    vi.mocked(api.deleteDocument).mockResolvedValue(undefined);
    renderPage();

    const tree = screen.getByRole("complementary");
    // View d1 in the right pane.
    fireEvent.click(await within(tree).findByText("Deploys"));
    expect(await screen.findByText("viewed-body")).toBeVisible();

    // Select d1's checkbox and bulk-delete it.
    fireEvent.click(within(tree).getAllByLabelText(/select row/i)[0]);
    fireEvent.click(within(tree).getByRole("button", { name: /^delete$/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));

    await waitFor(() => expect(api.deleteDocument).toHaveBeenCalledWith("designs", "d1"));
    // The viewer drops the deleted doc — selectedId resets, the preview clears.
    await waitFor(() => expect(screen.queryByText("viewed-body")).toBeNull());
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
