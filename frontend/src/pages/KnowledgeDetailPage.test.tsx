// frontend/src/pages/KnowledgeDetailPage.test.tsx
//
// The collection viewer. Data hooks are mocked so the test asserts the page's
// own rendering: one tree (no lane tabs), the file's body, and the fact that
// the only way to change it leaves the app.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/errors";
import { TooltipProvider } from "@/components/ui/tooltip";
import { KnowledgeDetailPage } from "./KnowledgeDetailPage";
import { acceptance } from "@/test/acceptance";

// The page asks the DAEMON whether a tidy pass is running (that is the whole
// point — a component's own pending flag dies on navigation), so the hook is
// mocked here the way every other data hook is.
vi.mock("@/lib/hooks/useUpkeep", () => ({ useUpkeepRunning: vi.fn(() => false) }));
vi.mock("@/lib/hooks/useKnowledge", () => ({
  useKnowledgeTree: vi.fn(),
  useKnowledgeFile: vi.fn(),
  useTidyCollection: vi.fn(),
  // Mounted transitively via KnowledgeUploadButton;
  // this suite only exercises the tree + preview, so both get an inert default.
  useUploadKnowledgeFile: vi.fn(),
  useDeleteKnowledgeFile: vi.fn(),
}));

const {
  useKnowledgeTree,
  useKnowledgeFile,
  useTidyCollection,
  useUploadKnowledgeFile,
  useDeleteKnowledgeFile,
} = await import("@/lib/hooks/useKnowledge");
const { useUpkeepRunning } = await import("@/lib/hooks/useUpkeep");
const runningMock = vi.mocked(useUpkeepRunning);
const treeMock = vi.mocked(useKnowledgeTree);
const fileMock = vi.mocked(useKnowledgeFile);
const tidyMock = vi.mocked(useTidyCollection);
const uploadMock = vi.mocked(useUploadKnowledgeFile);
const deleteMock = vi.mocked(useDeleteKnowledgeFile);

/** The delete mutation, stubbed. `mutate` reports nothing unless a test hands
 *  it an implementation — the default is a click that never succeeds, which is
 *  what the dialog has to survive without closing. */
function stubDelete(
  overrides: { mutate?: ReturnType<typeof vi.fn>; isPending?: boolean; error?: unknown } = {},
) {
  const mutate = overrides.mutate ?? vi.fn();
  deleteMock.mockReturnValue({
    mutate,
    isPending: overrides.isPending ?? false,
    error: overrides.error ?? null,
    reset: vi.fn(),
  } as unknown as ReturnType<typeof useDeleteKnowledgeFile>);
  return mutate;
}

beforeEach(() => stubDelete());

function stubEmptyTree() {
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
}

function stubInertDefaults() {
  runningMock.mockReturnValue(false);
  uploadMock.mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useUploadKnowledgeFile>);
}

function renderPage() {
  // The header's reach control reads the collection's Resource, so the page now
  // needs a real query client — the fetch never resolves here, and the control
  // renders from its own defaults.
  // The header's Tidy button carries a tooltip, which Layout's provider
  // normally hosts; the page is rendered bare here, so mount one.
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter initialEntries={["/knowledge/shopee"]}>
          <Routes>
            <Route path="/knowledge/:name" element={<KnowledgeDetailPage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
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
  acceptance("knowledge", "the viewer renders content read-only and offers open and reveal", () => {
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
    stubInertDefaults();

    renderPage();
    // The viewer only opens once a file is chosen, so choose one — the tree
    // row is a button carrying the file's title.
    fireEvent.click(screen.getByRole("button", { name: /Account Gateway/ }));

    // The body renders…
    expect(screen.getByText("The orchestration layer.")).toBeInTheDocument();
    // …and the actions that change it hand the file to the user's own tools
    // (spec knowledge FR-013/FR-035) — there is no in-app editor, because the
    // files are the only copy and an edit made elsewhere is live on the next
    // read with nothing to reconcile.
    expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reveal/i })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /body|content/i })).toBeNull();
    // One tree, not a Documents/Notes tab pair.
    expect(screen.queryByRole("tab")).toBeNull();
  });

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
    stubInertDefaults();

    renderPage();
    expect(screen.getByText(/select a file/i)).toBeInTheDocument();
  });

  test("spins the Tidy button while a pass this page did not start is running", () => {
    // The bug: the spinner used to come from the mutation's own `isPending`,
    // which a remount resets — so leaving the page mid-pass and coming back
    // showed an idle button and invited a second concurrent rewrite. The
    // running state is the daemon's answer now, so `isPending: false` and a
    // running pass must still read as running.
    stubEmptyTree();
    tidyMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useTidyCollection>);
    stubInertDefaults();
    runningMock.mockReturnValue(true);

    renderPage();

    const button = screen.getByRole("button", { name: /tidy/i });
    expect(button).toBeDisabled();
    expect(button.querySelector(".animate-spin")).not.toBeNull();
  });

  test("the Tidy button is idle when nothing is running", () => {
    stubEmptyTree();
    const mutate = vi.fn();
    tidyMock.mockReturnValue({
      mutate,
      isPending: false,
    } as unknown as ReturnType<typeof useTidyCollection>);
    stubInertDefaults();

    renderPage();

    const button = screen.getByRole("button", { name: /tidy/i });
    expect(button).not.toBeDisabled();
    expect(button.querySelector(".animate-spin")).toBeNull();
    fireEvent.click(button);
    expect(mutate).toHaveBeenCalled();
  });

  test("offers the way back to the collection list", () => {
    // A collection is reached by clicking a row, so leaving it must not depend
    // on the browser's own back button — every other detail page carries this.
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
    stubInertDefaults();

    renderPage();
    expect(screen.getByRole("link", { name: /back to knowledge/i })).toBeInTheDocument();
  });
});

// Deleting ONE file used to be possible only from an agent's `coffer__delete`
// or the CLI: the page offered no way to remove a single note, only the whole
// collection from the list page. The previewed file is the anchor — it is the
// file the user is looking at, and the only one the page can name for certain.
describe("KnowledgeDetailPage — deleting the previewed file", () => {
  /** The tree holds FILE; the file query answers only while one is selected,
   *  the way the real hook does (`enabled: Boolean(path)`). */
  function stubSelectableFile() {
    treeMock.mockReturnValue({
      data: { path: "shopee", directories: [], files: [FILE] },
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof useKnowledgeTree>);
    fileMock.mockImplementation(
      (path: string | null) =>
        ({
          data: path ? FILE : undefined,
          isPending: false,
          error: null,
        }) as unknown as ReturnType<typeof useKnowledgeFile>,
    );
    tidyMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useTidyCollection>);
    stubInertDefaults();
  }

  /** Open the collection and click the tree row, so a file is being previewed. */
  function openFile() {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Account Gateway/ }));
  }

  test("offers nothing to delete until a file is being previewed", () => {
    // The page can only name the file it has open; with none open, a delete
    // button could only mean the collection, which is the list page's action.
    stubSelectableFile();
    renderPage();
    expect(screen.queryByRole("button", { name: /delete file/i })).toBeNull();
  });

  test("the confirmation names the exact file path", () => {
    stubSelectableFile();
    openFile();

    fireEvent.click(screen.getByRole("button", { name: /delete file/i }));
    expect(screen.getByRole("dialog")).toHaveTextContent("shopee/gateway.md");
  });

  test("a refused delete keeps the dialog open with the reason", () => {
    const mutate = stubDelete({
      error: new ApiError("KNOWLEDGE_UNSAFE_PATH", "that path is outside the knowledge root"),
    });
    stubSelectableFile();
    openFile();

    fireEvent.click(screen.getByRole("button", { name: /delete file/i }));
    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));

    expect(mutate).toHaveBeenCalledWith("shopee/gateway.md", expect.anything());
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/outside the knowledge root/i);
  });

  test("a deleted file leaves the preview instead of previewing a 404", () => {
    const mutate = stubDelete({
      mutate: vi.fn((_path: string, opts?: { onSuccess?: () => void }) => opts?.onSuccess?.()),
    });
    stubSelectableFile();
    openFile();
    expect(screen.getByText("The orchestration layer.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /delete file/i }));
    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));

    expect(mutate).toHaveBeenCalledWith("shopee/gateway.md", expect.anything());
    expect(screen.queryByRole("dialog")).toBeNull();
    // Back to the empty pane: the file is gone, so re-reading it would 404.
    expect(screen.getByText(/select a file/i)).toBeInTheDocument();
  });
});
