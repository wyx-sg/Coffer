// frontend/src/kinds/knowledge/KnowledgeDetailPage.test.tsx
//
// The collection viewer. Data hooks are mocked so the test asserts the page's
// own rendering: one tree (no lane tabs), the file's body, and the fact that
// the only way to change it leaves the app.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { KnowledgeDetailPage } from "./KnowledgeDetailPage";
import { acceptance } from "@/test/acceptance";

vi.mock("./useKnowledge", () => ({
  useKnowledgeTree: vi.fn(),
  useKnowledgeFile: vi.fn(),
  useTidyCollection: vi.fn(),
}));

const { useKnowledgeTree, useKnowledgeFile, useTidyCollection } = await import("./useKnowledge");
const treeMock = vi.mocked(useKnowledgeTree);
const fileMock = vi.mocked(useKnowledgeFile);
const tidyMock = vi.mocked(useTidyCollection);

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/knowledge/shopee"]}>
      <Routes>
        <Route path="/knowledge/:scope" element={<KnowledgeDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const FILE = {
  path: "shopee/gateway.md",
  title: "Account Gateway",
  description: "where account decisions are made",
  actor: "user" as const,
  created_at: "2026-09-12T00:00:00Z",
  updated_at: "2026-09-12T00:00:00Z",
  body: "The orchestration layer.",
  file_path: "/Users/dev/.coffer/knowledge/shopee/gateway.md",
  folder_path: "/Users/dev/.coffer/knowledge/shopee",
};

describe("KnowledgeDetailPage", () => {
  acceptance(
    "knowledge",
    "the viewer renders content read-only and offers open and reveal",
    () => {
      treeMock.mockReturnValue({
        data: { path: "shopee", directories: [], files: [FILE] },
        isPending: false,
        error: null,
      } as unknown as ReturnType<typeof useKnowledgeTree>);
      fileMock.mockReturnValue({
        data: FILE,
        isPending: false,
        error: null,
      } as unknown as ReturnType<typeof useKnowledgeFile>);
      tidyMock.mockReturnValue({
        mutate: vi.fn(),
        isPending: false,
      } as unknown as ReturnType<typeof useTidyCollection>);

      renderPage();
      // The viewer only opens once a file is chosen, so choose one — the tree
      // row is a button carrying the file's title.
      fireEvent.click(screen.getByRole("button", { name: /Account Gateway/ }));

      // The body renders…
      expect(screen.getByText("The orchestration layer.")).toBeInTheDocument();
      // …and the actions that change it hand the file to the user's own tools
      // (spec knowledge FR-021/FR-061) — there is no in-app editor, because the
      // files are the only copy and an edit made elsewhere is live on the next
      // read with nothing to reconcile.
      expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /reveal/i })).toBeInTheDocument();
      expect(screen.queryByRole("textbox", { name: /body|content/i })).toBeNull();
      // One tree, not a Documents/Notes tab pair.
      expect(screen.queryByRole("tab")).toBeNull();
    },
  );

  test("prompts for a selection before a file is chosen", () => {
    treeMock.mockReturnValue({
      data: { path: "shopee", directories: [], files: [] },
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof useKnowledgeTree>);
    fileMock.mockReturnValue({
      data: undefined,
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof useKnowledgeFile>);
    tidyMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useTidyCollection>);

    renderPage();
    expect(screen.getByText(/select a file/i)).toBeInTheDocument();
  });
});
