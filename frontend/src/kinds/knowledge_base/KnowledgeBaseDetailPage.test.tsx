// frontend/src/kinds/knowledge_base/KnowledgeBaseDetailPage.test.tsx
//
// Exercises the redesigned KB detail surface: metrics header, keyword/vector
// search with a mode toggle, grep, reindex, and the per-document edit /
// source_mode badge / delete behaviors. The `./api` module is mocked so the
// component renders deterministically without a backend.

import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ApiError } from "@/lib/api/errors";
import { KnowledgeBaseDetailPage } from "./KnowledgeBaseDetailPage";

vi.mock("./api", () => ({
  listDocuments: vi.fn(),
  getDocument: vi.fn(),
  getKnowledgeBaseMetrics: vi.fn(),
  ingestDocument: vi.fn(),
  editDocument: vi.fn(),
  deleteDocument: vi.fn(),
  reindexKnowledgeBase: vi.fn(),
  searchKnowledgeBase: vi.fn(),
  grepKnowledgeBase: vi.fn(),
}));
const api = await import("./api");

const DOC = {
  id: "d1",
  kind: "knowledge_base",
  resource_name: "designs",
  title: "spec.md",
  source_mode: "converted" as const,
  content_sha256: "abc",
  chunk_count: 3,
  metadata: {},
  created_at: "2026-05-29T00:00:00Z",
  updated_at: "2026-05-29T00:00:00Z",
};

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
  test("shows metrics and the document list with a source_mode badge", async () => {
    vi.mocked(api.listDocuments).mockResolvedValue({ documents: [DOC], total: 1 });
    vi.mocked(api.getKnowledgeBaseMetrics).mockResolvedValue({
      document_count: 1,
      chunk_count: 3,
      indexed_modes: ["keyword"],
      disk_bytes: 100,
    });

    renderPage();
    expect(await screen.findByText("spec.md")).toBeInTheDocument();
    expect(screen.getByText(/1 documents/i)).toBeInTheDocument();
    expect(screen.getByText("Converted")).toBeInTheDocument();
  });

  test("search passes the selected mode and renders passages", async () => {
    vi.mocked(api.listDocuments).mockResolvedValue({ documents: [], total: 0 });
    vi.mocked(api.getKnowledgeBaseMetrics).mockResolvedValue({
      document_count: 0,
      chunk_count: 0,
      indexed_modes: [],
      disk_bytes: 0,
    });
    vi.mocked(api.searchKnowledgeBase).mockResolvedValue({
      mode: "vector",
      fallback: null,
      passages: [
        { text: "hello world", document_id: "d1", title: "spec.md", score: 0.8, position: 0 },
      ],
    });

    renderPage();
    const input = await screen.findByPlaceholderText(/search this knowledge base/i);
    fireEvent.change(input, { target: { value: "hello" } });
    // Pick the vector mode.
    fireEvent.change(screen.getByLabelText(/^mode$/i), { target: { value: "vector" } });
    fireEvent.click(screen.getByRole("button", { name: /^search$/i }));

    await waitFor(() =>
      expect(api.searchKnowledgeBase).toHaveBeenCalledWith("designs", "hello", {
        topK: 5,
        mode: "vector",
      }),
    );
    expect(await screen.findByText("hello world")).toBeInTheDocument();
  });

  test("grep calls the grep helper and renders hits", async () => {
    vi.mocked(api.listDocuments).mockResolvedValue({ documents: [], total: 0 });
    vi.mocked(api.getKnowledgeBaseMetrics).mockResolvedValue({
      document_count: 0,
      chunk_count: 0,
      indexed_modes: [],
      disk_bytes: 0,
    });
    vi.mocked(api.grepKnowledgeBase).mockResolvedValue({
      hits: [{ path: "docs/d1.md", line_number: 4, line: "TODO ship it" }],
      truncated: false,
    });

    renderPage();
    const input = await screen.findByPlaceholderText(/pattern/i);
    fireEvent.change(input, { target: { value: "TODO" } });
    fireEvent.click(screen.getByRole("button", { name: /^grep$/i }));

    await waitFor(() => expect(api.grepKnowledgeBase).toHaveBeenCalledWith("designs", "TODO", 100));
    expect(await screen.findByText(/TODO ship it/)).toBeInTheDocument();
  });

  test("reindex triggers the reindex helper", async () => {
    vi.mocked(api.listDocuments).mockResolvedValue({ documents: [], total: 0 });
    vi.mocked(api.getKnowledgeBaseMetrics).mockResolvedValue({
      document_count: 0,
      chunk_count: 0,
      indexed_modes: [],
      disk_bytes: 0,
    });
    vi.mocked(api.reindexKnowledgeBase).mockResolvedValue({
      documents_scanned: 1,
      documents_reindexed: 0,
      documents_skipped: 1,
    });

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /reindex/i }));
    await waitFor(() => expect(api.reindexKnowledgeBase).toHaveBeenCalledWith("designs"));
  });

  test("editing a document loads its markdown then PUTs the new body", async () => {
    vi.mocked(api.listDocuments).mockResolvedValue({ documents: [DOC], total: 1 });
    vi.mocked(api.getKnowledgeBaseMetrics).mockResolvedValue({
      document_count: 1,
      chunk_count: 3,
      indexed_modes: ["keyword"],
      disk_bytes: 100,
    });
    vi.mocked(api.getDocument).mockResolvedValue({ ...DOC, markdown: "# original" });
    vi.mocked(api.editDocument).mockResolvedValue({ ...DOC, source_mode: "edited" });

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /^edit$/i }));

    const editor = await screen.findByLabelText(/edit markdown for spec.md/i);
    fireEvent.change(editor, { target: { value: "# rewritten" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() =>
      expect(api.editDocument).toHaveBeenCalledWith("designs", "d1", "# rewritten"),
    );
  });

  test("deleting a document calls the delete helper after confirmation", async () => {
    vi.mocked(api.listDocuments).mockResolvedValue({ documents: [DOC], total: 1 });
    vi.mocked(api.getKnowledgeBaseMetrics).mockResolvedValue({
      document_count: 1,
      chunk_count: 3,
      indexed_modes: ["keyword"],
      disk_bytes: 100,
    });
    vi.mocked(api.deleteDocument).mockResolvedValue(undefined);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    await waitFor(() => expect(api.deleteDocument).toHaveBeenCalledWith("designs", "d1"));
    confirmSpy.mockRestore();
  });

  test("surfaces a localized error when the document/metrics query fails", async () => {
    vi.mocked(api.listDocuments).mockRejectedValue(new ApiError("RESOURCE_NOT_FOUND", "nope"));
    vi.mocked(api.getKnowledgeBaseMetrics).mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "nope"),
    );

    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(/resource not found/i);
  });

  test("does NOT delete a document when the confirm is cancelled", async () => {
    vi.mocked(api.listDocuments).mockResolvedValue({ documents: [DOC], total: 1 });
    vi.mocked(api.getKnowledgeBaseMetrics).mockResolvedValue({
      document_count: 1,
      chunk_count: 3,
      indexed_modes: ["keyword"],
      disk_bytes: 100,
    });
    vi.mocked(api.deleteDocument).mockResolvedValue(undefined);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    expect(confirmSpy).toHaveBeenCalled();
    expect(api.deleteDocument).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});
