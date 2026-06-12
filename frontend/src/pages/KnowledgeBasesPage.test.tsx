// frontend/src/pages/KnowledgeBasesPage.test.tsx
//
// KnowledgeBasesPage mirrors SkillsPage: PageHeader + welcome panel (empty) /
// DataTable (populated), with a modal add dialog. We mock `useResources` so
// the page renders deterministically and assert the loading/empty/populated/
// error states (mirrors MemoryPage.test.tsx).

import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";
import { KnowledgeBasesPage } from "./KnowledgeBasesPage";
import type { KnowledgeBaseOut } from "@/kinds/knowledge_base/api";

vi.mock("@/kinds/knowledge_base/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/kinds/knowledge_base/api")>()),
  listKnowledgeBases: vi.fn(),
}));
const api = await import("@/kinds/knowledge_base/api");
const listMock = vi.mocked(api.listKnowledgeBases);

afterEach(() => vi.clearAllMocks());

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

const KB: KnowledgeBaseOut = {
  ref: "knowledge_base:designs",
  kind: "knowledge_base",
  name: "designs",
  description: "design notes",
  config: {
    enabled_modes: ["keyword", "grep"] as ("keyword" | "grep" | "vector")[],
    default_mode: "keyword",
    chunk_size: 1000,
    chunk_overlap: 100,
    max_document_bytes: 1048576,
    embedding: null,
  },
  enabled: true,
  document_count: 3,
  created_at: "2026-05-29T00:00:00Z",
  updated_at: "2026-05-29T00:00:00Z",
} as unknown as KnowledgeBaseOut;

describe("KnowledgeBasesPage", () => {
  test("renders the loading state while the query is pending", () => {
    listMock.mockReturnValue(new Promise(() => {}) as Promise<never>);
    render(<KnowledgeBasesPage />, { wrapper: wrap() });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  test("renders the welcome panel when no knowledge bases exist (no header CTA)", async () => {
    listMock.mockResolvedValue([]);
    render(<KnowledgeBasesPage />, { wrapper: wrap() });
    expect(await screen.findByText(/manage your knowledge bases/i)).toBeInTheDocument();
  });

  test("renders the populated table and the header Add action opens the dialog", async () => {
    listMock.mockResolvedValue([KB]);
    render(<KnowledgeBasesPage />, { wrapper: wrap() });
    expect(await screen.findByText("designs")).toBeInTheDocument();
    expect(screen.getByText("design notes")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /new knowledge base/i }));
    expect(screen.getByLabelText(/^name$/i)).toBeInTheDocument();
  });

  test("renders an error card when the query fails", async () => {
    listMock.mockRejectedValue(new Error("HTTP 500"));
    render(<KnowledgeBasesPage />, { wrapper: wrap() });
    expect(await screen.findByText("Failed to load knowledge bases")).toBeInTheDocument();
    expect(screen.getByText("HTTP 500")).toBeInTheDocument();
  });
});
