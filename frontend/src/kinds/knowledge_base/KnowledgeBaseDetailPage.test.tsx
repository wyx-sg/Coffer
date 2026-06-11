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
  getKnowledgeBase: vi.fn(),
  getKnowledgeBaseMetrics: vi.fn(),
  ingestDocument: vi.fn(),
  editDocument: vi.fn(),
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
  title: "spec.md",
  source_mode: "converted" as const,
  content_sha256: "abc",
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

  test("settings dialog submits the merged config (chunking + embedding + vector mode)", async () => {
    vi.mocked(api.listDocuments).mockResolvedValue({ documents: [], total: 0 });
    vi.mocked(api.getKnowledgeBaseMetrics).mockResolvedValue({
      document_count: 0,
      chunk_count: 0,
      indexed_modes: [],
      disk_bytes: 0,
    });
    vi.mocked(api.getKnowledgeBase).mockResolvedValue(KB);
    vi.mocked(api.updateKnowledgeBaseConfig).mockResolvedValue(KB);

    renderPage();
    // The Settings action stays disabled until the KB config has loaded.
    const settings = await screen.findByRole("button", { name: /settings/i });
    await waitFor(() => expect(settings).toBeEnabled());
    fireEvent.click(settings);

    // The dialog opens pre-filled with the current config.
    const chunkSize = await screen.findByLabelText(/chunk size/i);
    expect(chunkSize).toHaveValue(1000);
    fireEvent.change(chunkSize, { target: { value: "800" } });
    fireEvent.change(screen.getByLabelText(/chunk overlap/i), { target: { value: "80" } });

    // Turning vector on reveals the embedding block; fill it in.
    fireEvent.click(screen.getByRole("switch"));
    fireEvent.change(screen.getByLabelText(/embedding provider/i), {
      target: { value: "openai" },
    });
    fireEvent.change(screen.getByLabelText(/embedding model/i), {
      target: { value: "text-embedding-3-small" },
    });
    fireEvent.change(screen.getByLabelText(/dimensions/i), { target: { value: "1536" } });
    fireEvent.change(screen.getByLabelText(/base url/i), {
      target: { value: "https://api.openai.com/v1" },
    });
    fireEvent.change(screen.getByLabelText(/credential reference/i), {
      target: { value: "keychain:openai" },
    });

    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() =>
      expect(api.updateKnowledgeBaseConfig).toHaveBeenCalledWith("designs", {
        enabled_modes: ["keyword", "grep", "vector"],
        default_mode: "keyword",
        chunk_size: 800,
        chunk_overlap: 80,
        max_document_bytes: 1048576,
        embedding: {
          provider: "openai",
          model: "text-embedding-3-small",
          base_url: "https://api.openai.com/v1",
          credential_ref: "keychain:openai",
          dimensions: 1536,
        },
      }),
    );
  });

  test("settings dialog keeps embedding null when vector stays off", async () => {
    vi.mocked(api.listDocuments).mockResolvedValue({ documents: [], total: 0 });
    vi.mocked(api.getKnowledgeBaseMetrics).mockResolvedValue({
      document_count: 0,
      chunk_count: 0,
      indexed_modes: [],
      disk_bytes: 0,
    });
    vi.mocked(api.getKnowledgeBase).mockResolvedValue(KB);
    vi.mocked(api.updateKnowledgeBaseConfig).mockResolvedValue(KB);

    renderPage();
    const settings = await screen.findByRole("button", { name: /settings/i });
    await waitFor(() => expect(settings).toBeEnabled());
    fireEvent.click(settings);
    fireEvent.change(await screen.findByLabelText(/chunk size/i), { target: { value: "1200" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() =>
      expect(api.updateKnowledgeBaseConfig).toHaveBeenCalledWith("designs", {
        enabled_modes: ["keyword", "grep"],
        default_mode: "keyword",
        chunk_size: 1200,
        chunk_overlap: 100,
        max_document_bytes: 1048576,
        embedding: null,
      }),
    );
  });

  test("reconvert action calls the reconvert helper for converted documents", async () => {
    vi.mocked(api.listDocuments).mockResolvedValue({ documents: [DOC], total: 1 });
    vi.mocked(api.getKnowledgeBaseMetrics).mockResolvedValue({
      document_count: 1,
      chunk_count: 3,
      indexed_modes: ["keyword"],
      disk_bytes: 100,
    });
    vi.mocked(api.reconvertDocument).mockResolvedValue(DOC);

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /reconvert/i }));
    await waitFor(() => expect(api.reconvertDocument).toHaveBeenCalledWith("designs", "d1"));
  });

  test("hides the reconvert action for edited documents and surfaces blocked errors", async () => {
    const edited = { ...DOC, id: "d2", source_mode: "edited" as const };
    vi.mocked(api.listDocuments).mockResolvedValue({ documents: [DOC, edited], total: 2 });
    vi.mocked(api.getKnowledgeBaseMetrics).mockResolvedValue({
      document_count: 2,
      chunk_count: 3,
      indexed_modes: ["keyword"],
      disk_bytes: 100,
    });
    vi.mocked(api.reconvertDocument).mockRejectedValue(
      new ApiError("RECONVERSION_BLOCKED", "document was edited"),
    );

    renderPage();
    // Only the converted document gets a Reconvert action.
    const buttons = await screen.findAllByRole("button", { name: /reconvert/i });
    expect(buttons).toHaveLength(1);

    fireEvent.click(buttons[0]);
    expect(await screen.findByText(/document was edited/i)).toBeInTheDocument();
  });

  test("a duplicate upload offers a replace retry that re-ingests with replace=true", async () => {
    vi.mocked(api.listDocuments).mockResolvedValue({ documents: [], total: 0 });
    vi.mocked(api.getKnowledgeBaseMetrics).mockResolvedValue({
      document_count: 0,
      chunk_count: 0,
      indexed_modes: [],
      disk_bytes: 0,
    });
    vi.mocked(api.ingestDocument)
      .mockRejectedValueOnce(new ApiError("INGEST_REJECTED", "duplicate document"))
      .mockResolvedValueOnce(DOC);

    const { container } = renderPage();
    await screen.findByRole("button", { name: /upload/i });

    const fileInput = container.querySelector('input[type="file"]')!;
    const file = new File(["alpha"], "a.md", { type: "text/markdown" });
    fireEvent.change(fileInput, { target: { files: [file] } });

    await waitFor(() => expect(api.ingestDocument).toHaveBeenCalledWith("designs", file, false));
    expect(await screen.findByText(/duplicate document/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /replace/i }));
    await waitFor(() => expect(api.ingestDocument).toHaveBeenLastCalledWith("designs", file, true));
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
