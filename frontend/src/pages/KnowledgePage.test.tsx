// frontend/src/pages/KnowledgePage.test.tsx
// The unified 知识 surface: scope axis + intermixed notes/documents list +
// add-by-shape + trash. Mocks the two api modules (the network boundary) and
// renders through a real QueryClientProvider + MemoryRouter.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";

vi.mock("@/kinds/memory/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/kinds/memory/api")>()),
  listMemoryStores: vi.fn(),
  listFacts: vi.fn(),
  addFact: vi.fn(),
}));
vi.mock("@/kinds/knowledge_base/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/kinds/knowledge_base/api")>()),
  listKnowledgeBases: vi.fn(),
  listDocuments: vi.fn(),
}));

const memApi = await import("@/kinds/memory/api");
const kbApi = await import("@/kinds/knowledge_base/api");
const { KnowledgePage } = await import("./KnowledgePage");
const GLOBAL = "00000000000000000000000000";

afterEach(() => vi.clearAllMocks());

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

function seed(opts: { facts?: boolean; docs?: boolean } = {}) {
  vi.mocked(memApi.listMemoryStores).mockResolvedValue({
    memory_stores: [
      {
        ref: "m:g",
        kind: "memory",
        name: "global",
        scope: "global",
        project_id: GLOBAL,
        project_root: null,
        description: null,
        config: {
          retrieval_modes: ["keyword"],
          default_mode: "keyword",
          embedding_dimensions: 768,
          max_fact_chars: 8192,
        },
        enabled: true,
        created_at: "t",
        updated_at: "t",
      },
    ],
  });
  vi.mocked(memApi.listFacts).mockResolvedValue({
    facts: opts.facts
      ? [
          {
            id: "f1",
            store_name: "global",
            scope: "global",
            name: "my note",
            description: "",
            text: "the body",
            actor: "agent",
            created_at: "t",
            updated_at: "2026-06-10T00:00:00Z",
          },
        ]
      : [],
    total: opts.facts ? 1 : 0,
  });
  vi.mocked(kbApi.listKnowledgeBases).mockResolvedValue([{ name: "kb1" }] as never);
  vi.mocked(kbApi.listDocuments).mockResolvedValue({
    documents: opts.docs
      ? [
          {
            id: "d1",
            kind: "knowledge_base",
            resource_name: "kb1",
            title: "my doc",
            source_mode: "converted",
            content_sha256: "x",
            locked: false,
            project_id: GLOBAL,
            deleted_at: null,
            metadata: {},
            created_at: "t",
            updated_at: "2026-06-20T00:00:00Z",
          },
        ]
      : [],
    total: opts.docs ? 1 : 0,
  });
}

describe("KnowledgePage", () => {
  test("renders the scope axis (Global) and intermixed notes + documents", async () => {
    seed({ facts: true, docs: true });
    render(<KnowledgePage />, { wrapper: wrap() });
    expect(await screen.findByText("Global")).toBeInTheDocument();
    expect(await screen.findByText("my note")).toBeInTheDocument();
    expect(await screen.findByText("my doc")).toBeInTheDocument();
  });

  test("add-by-shape: a pasted note calls addFact on the scope store", async () => {
    seed();
    vi.mocked(memApi.addFact).mockResolvedValue({} as never);
    render(<KnowledgePage />, { wrapper: wrap() });
    await screen.findByText("Global");
    fireEvent.change(await screen.findByPlaceholderText(/paste a link or write a note/i), {
      target: { value: "remember this" },
    });
    fireEvent.click(screen.getByRole("button", { name: /add note/i }));
    await waitFor(() =>
      expect(memApi.addFact).toHaveBeenCalledWith("global", { text: "remember this" }),
    );
  });

  test("scopes the document listing to the active scope's project_id", async () => {
    seed({ docs: true });
    render(<KnowledgePage />, { wrapper: wrap() });
    await screen.findByText("my doc");
    expect(kbApi.listDocuments).toHaveBeenCalledWith("kb1", { limit: 200, projectId: GLOBAL });
  });

  test("opens the trash panel from the header", async () => {
    seed();
    render(<KnowledgePage />, { wrapper: wrap() });
    await screen.findByText("Global");
    fireEvent.click(screen.getByRole("button", { name: /^trash$/i }));
    expect(await screen.findByText(/soft-deleted documents/i)).toBeInTheDocument();
  });
});
