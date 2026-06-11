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

vi.mock("@/lib/hooks/useResources", () => ({
  useResources: vi.fn(),
  useResource: vi.fn(),
}));
const hooks = await import("@/lib/hooks/useResources");
const useResourcesMock = vi.mocked(hooks.useResources);

afterEach(() => vi.clearAllMocks());

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

const KB = {
  ref: "knowledge_base:designs",
  kind: "knowledge_base",
  name: "designs",
  description: "design notes",
  config: {
    enabled_modes: ["keyword", "grep"],
    default_mode: "keyword",
    chunk_size: 1000,
    chunk_overlap: 100,
    max_document_bytes: 1048576,
    embedding: null,
  },
  enabled: true,
  created_at: "2026-05-29T00:00:00Z",
  updated_at: "2026-05-29T00:00:00Z",
};

describe("KnowledgeBasesPage", () => {
  test("renders the loading state while resources are pending", () => {
    useResourcesMock.mockReturnValue({
      data: undefined,
      isPending: true,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof hooks.useResources>);

    render(<KnowledgeBasesPage />, { wrapper: wrap() });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  test("renders the welcome panel when no knowledge bases exist (no header CTA)", () => {
    useResourcesMock.mockReturnValue({
      data: [],
      isPending: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof hooks.useResources>);

    render(<KnowledgeBasesPage />, { wrapper: wrap() });
    expect(screen.getByText(/manage your knowledge bases/i)).toBeInTheDocument();
  });

  test("renders the populated table and the header Add action opens the dialog", () => {
    useResourcesMock.mockReturnValue({
      data: [KB],
      isPending: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof hooks.useResources>);

    render(<KnowledgeBasesPage />, { wrapper: wrap() });
    expect(screen.getByText("designs")).toBeInTheDocument();
    expect(screen.getByText("design notes")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /new knowledge base/i }));
    // The create dialog opens with its name field.
    expect(screen.getByLabelText(/^name$/i)).toBeInTheDocument();
  });

  test("renders an error card when the resources query fails", () => {
    useResourcesMock.mockReturnValue({
      data: undefined,
      isPending: false,
      error: new Error("HTTP 500"),
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof hooks.useResources>);

    render(<KnowledgeBasesPage />, { wrapper: wrap() });
    expect(screen.getByText("Failed to load knowledge bases")).toBeInTheDocument();
    expect(screen.getByText("HTTP 500")).toBeInTheDocument();
  });
});
