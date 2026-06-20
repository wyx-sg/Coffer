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
    // The read-only viewer offers the copy-path affordance (jsdom is not Tauri).
    expect(screen.getByRole("button", { name: /copy path/i })).toBeInTheDocument();
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
});
