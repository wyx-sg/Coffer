// frontend/src/components/knowledge/KnowledgeItemViewer.test.tsx
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

vi.mock("@/kinds/knowledge_base/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/kinds/knowledge_base/api")>()),
  getDocument: vi.fn(),
}));
const kbApi = await import("@/kinds/knowledge_base/api");

import { KnowledgeItemViewer } from "./KnowledgeItemViewer";
import type { KnowledgeItem } from "@/lib/api/knowledge";

afterEach(() => vi.clearAllMocks());

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

const NOTE: KnowledgeItem = {
  ref: "note:g:f1",
  type: "note",
  scopeId: "g",
  title: "a fact",
  preview: "",
  updatedAt: "t",
  storeName: "global",
  factId: "f1",
  noteBody: "## Fact body\n\nthe note text",
  path: "/p/f1.md",
  folderPath: "/p",
};

const LOCKED_DOC: KnowledgeItem = {
  ref: "doc:kb1:d1",
  type: "document",
  scopeId: "g",
  title: "a doc",
  preview: "",
  updatedAt: "t",
  kbName: "kb1",
  documentId: "d1",
  locked: true,
};

describe("KnowledgeItemViewer", () => {
  test("renders a note's body read-only without fetching", () => {
    render(
      <KnowledgeItemViewer
        item={NOTE}
        isDeletePending={false}
        onDelete={() => {}}
        onClose={() => {}}
      />,
      {
        wrapper: wrap(),
      },
    );
    expect(screen.getByText("the note text")).toBeInTheDocument();
    expect(kbApi.getDocument).not.toHaveBeenCalled();
  });

  test("fetches and renders a document's markdown body", async () => {
    vi.mocked(kbApi.getDocument).mockResolvedValue({
      id: "d1",
      kind: "knowledge_base",
      resource_name: "kb1",
      title: "a doc",
      source_mode: "converted",
      content_sha256: "x",
      locked: true,
      project_id: "g",
      metadata: {},
      created_at: "t",
      updated_at: "t",
      markdown: "the converted markdown",
      path: "/k/d1.md",
      folder_path: "/k",
    });
    render(
      <KnowledgeItemViewer
        item={LOCKED_DOC}
        isDeletePending={false}
        onDelete={() => {}}
        onClose={() => {}}
      />,
      { wrapper: wrap() },
    );
    expect(await screen.findByText("the converted markdown")).toBeInTheDocument();
  });

  test("disables delete on a locked document", () => {
    render(
      <KnowledgeItemViewer
        item={LOCKED_DOC}
        isDeletePending={false}
        onDelete={() => {}}
        onClose={() => {}}
      />,
      { wrapper: wrap() },
    );
    expect(screen.getByRole("button", { name: /delete/i })).toBeDisabled();
    expect(screen.getByText("Locked")).toBeInTheDocument();
  });
});
