// frontend/src/kinds/knowledge_base/KnowledgeBaseDetailPage.test.tsx
//
// Exercises the redesigned KB detail surface: the unified retrieval bar
// (one input + a keyword/vector/grep mode dropdown), and the document tree →
// preview/editor flow (select a doc on the left, then edit / reconvert /
// delete it on the right). The `./api` module is mocked so the component
// renders deterministically without a backend.

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
  title: "Deploys",
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

  test("selecting a document loads its markdown, and editing PUTs the new body", async () => {
    seedBaseQueries();
    vi.mocked(api.getDocument).mockResolvedValue({ ...DOC, markdown: "# Deploys\n\nbody" });
    vi.mocked(api.editDocument).mockResolvedValue(DOC);
    renderPage();

    const tree = screen.getByRole("complementary");
    fireEvent.click(await within(tree).findByText("Deploys"));
    // Viewing renders the Markdown: the body text is shown (the raw "# " is gone).
    expect(await screen.findByText("body")).toBeVisible();

    // Editing drops back to the raw Markdown source in a textarea.
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    const textarea = await screen.findByDisplayValue(/# Deploys/);
    fireEvent.change(textarea, { target: { value: "# Deploys\n\nedited" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() =>
      expect(api.editDocument).toHaveBeenCalledWith("designs", "d1", "# Deploys\n\nedited"),
    );
  });

  test("deleting a selected document calls delete after confirmation", async () => {
    seedBaseQueries();
    vi.mocked(api.getDocument).mockResolvedValue({ ...DOC, markdown: "body" });
    vi.mocked(api.deleteDocument).mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderPage();

    const tree = screen.getByRole("complementary");
    fireEvent.click(await within(tree).findByText("Deploys"));
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    await waitFor(() => expect(api.deleteDocument).toHaveBeenCalledWith("designs", "d1"));
  });

  test("does not delete when the confirm is cancelled", async () => {
    seedBaseQueries();
    vi.mocked(api.getDocument).mockResolvedValue({ ...DOC, markdown: "body" });
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderPage();

    const tree = screen.getByRole("complementary");
    fireEvent.click(await within(tree).findByText("Deploys"));
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
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
