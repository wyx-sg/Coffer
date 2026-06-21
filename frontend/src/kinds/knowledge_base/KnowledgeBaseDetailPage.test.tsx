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

  test("paginates the document tree by server offset (page 2 sends offset)", async () => {
    // The tree is page-paginated (default size 50, server-driven offset). Paging
    // forward re-queries listDocuments with offset = (page-1)*pageSize.
    const page1 = Array.from({ length: 50 }, (_, i) => ({
      ...DOC,
      id: `d${i}`,
      title: `doc-${i}`,
    }));
    const page2 = Array.from({ length: 50 }, (_, i) => ({
      ...DOC,
      id: `d${50 + i}`,
      title: `doc-${50 + i}`,
    }));
    vi.mocked(api.listDocuments).mockImplementation(async (_kb, _limit, offset) =>
      (offset ?? 0) >= 50 ? { documents: page2, total: 120 } : { documents: page1, total: 120 },
    );
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
    // First page fetched with offset 0.
    expect(await within(tree).findByText("doc-0")).toBeVisible();
    await waitFor(() => expect(api.listDocuments).toHaveBeenCalledWith("designs", 50, 0));

    // Next page → offset 50.
    fireEvent.click(within(tree).getByRole("button", { name: /next/i }));
    await waitFor(() => expect(api.listDocuments).toHaveBeenCalledWith("designs", 50, 50));
    expect(await within(tree).findByText("doc-99")).toBeVisible();
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

  test("clamps to a populated page when the total shrinks (last page emptied)", async () => {
    // Page 2 holds only the 51st doc; deleting it shrinks the total so page 2 no
    // longer exists — the tree must pull back to page 1, never strand the user on
    // an empty page past the end.
    const deleted = new Set<string>();
    const remaining = () =>
      Array.from({ length: 51 }, (_, i) => ({ ...DOC, id: `d${i}`, title: `doc-${i}` })).filter(
        (d) => !deleted.has(d.id),
      );
    vi.mocked(api.listDocuments).mockImplementation(async (_kb, _limit, offset) => {
      const all = remaining();
      const start = offset ?? 0;
      return { documents: all.slice(start, start + 50), total: all.length };
    });
    vi.mocked(api.getDocument).mockImplementation(async (_kb, id) => ({
      ...DOC,
      id,
      markdown: "body",
    }));
    vi.mocked(api.deleteDocument).mockImplementation(async (_kb, _id) => {
      deleted.add(_id);
    });
    vi.mocked(api.getKnowledgeBaseMetrics).mockResolvedValue({
      document_count: 51,
      chunk_count: 3,
      documents_degraded: 0,
      indexed_modes: ["keyword", "grep"],
      disk_bytes: 264,
    });
    vi.mocked(api.getKnowledgeBase).mockResolvedValue(KB);

    renderPage();
    const tree = screen.getByRole("complementary");
    await within(tree).findByText("doc-0");

    // Page 2 → the lone 51st doc; select it for the viewer.
    fireEvent.click(within(tree).getByRole("button", { name: /next/i }));
    fireEvent.click(await within(tree).findByText("doc-50"));

    // Delete it via the viewer's confirm dialog; total drops to 50 → page 2 gone.
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));
    await waitFor(() => expect(api.deleteDocument).toHaveBeenCalledWith("designs", "d50"));

    // The clamp pulls back to page 1 (offset 0): a populated page, not an empty one.
    expect(await within(tree).findByText("doc-0")).toBeVisible();
    expect(within(tree).queryByText("doc-50")).toBeNull();
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
