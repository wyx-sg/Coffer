// frontend/src/pages/KnowledgeDetailPage.test.tsx
//
// The collection viewer, which is TWO trees. Data hooks are mocked so the test
// asserts the page's own rendering: a lane per tab, the file's body in the pane
// beside it, and — the thing this page exists to get right — that what may be
// DONE to a file follows the lane it is in.
//
// Radix tabs activate on **mousedown**, not click. A test that switches them
// with `fireEvent.click` silently stays on the first tab and then passes its
// assertions for the wrong reason, so every tab switch below is a `mouseDown`.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/errors";
import { TooltipProvider } from "@/components/ui/tooltip";
import { KnowledgeDetailPage } from "./KnowledgeDetailPage";
import { acceptance } from "@/test/acceptance";

// The page asks the DAEMON whether a curation pass is running (that is the
// whole point — a component's own pending flag dies on navigation), so the hook
// is mocked here the way every other data hook is.
vi.mock("@/lib/hooks/useUpkeep", () => ({ useUpkeepRunning: vi.fn(() => false) }));
// The route carries the collection's UID, and everything the page puts on
// screen — the title, and every `path` its two trees ask for — is built from
// the NAME. The name arrives on this read and nowhere else, so it is stubbed
// like any other data hook rather than left to a query that never resolves.
vi.mock("@/lib/hooks/useResources", () => ({
  useResource: vi.fn(() => ({
    data: { uid: "kn-8c1f", kind: "knowledge", name: "shopee", enabled: true },
    isPending: false,
    error: null,
  })),
}));
vi.mock("@/lib/hooks/useKnowledge", () => ({
  useKnowledgeTree: vi.fn(),
  useKnowledgeFile: vi.fn(),
  useCurateCollection: vi.fn(),
  // Mounted transitively via KnowledgeUploadButton;
  // this suite only exercises the trees + preview, so both get an inert default.
  useUploadKnowledgeFile: vi.fn(),
  useDeleteKnowledgeFile: vi.fn(),
}));

const {
  useKnowledgeTree,
  useKnowledgeFile,
  useCurateCollection,
  useUploadKnowledgeFile,
  useDeleteKnowledgeFile,
} = await import("@/lib/hooks/useKnowledge");
const { useUpkeepRunning } = await import("@/lib/hooks/useUpkeep");
const { useResource } = await import("@/lib/hooks/useResources");
const resourceMock = vi.mocked(useResource);
const runningMock = vi.mocked(useUpkeepRunning);
const treeMock = vi.mocked(useKnowledgeTree);
const fileMock = vi.mocked(useKnowledgeFile);
const curateMock = vi.mocked(useCurateCollection);
const uploadMock = vi.mocked(useUploadKnowledgeFile);
const deleteMock = vi.mocked(useDeleteKnowledgeFile);

const SOURCE = {
  path: "shopee/sources/gateway.md",
  title: "Account Gateway",
  description: "where account decisions are made",
  actor: "user" as const,
  created_at: "2026-09-12T00:00:00Z",
  updated_at: "2026-09-12T00:00:00Z",
  ingested_at: "2026-09-13T00:00:00Z",
  body: "The orchestration layer.",
  file_path: "/Users/dev/.coffer/knowledge/shopee/sources/gateway.md",
  folder_path: "/Users/dev/.coffer/knowledge/shopee/sources",
};

const TOPIC = {
  path: "shopee/topics/session-ownership.md",
  title: "Session ownership",
  description: "who owns a login session",
  actor: "agent" as const,
  created_at: "2026-09-12T00:00:00Z",
  updated_at: "2026-09-12T00:00:00Z",
  ingested_at: "",
  body: "Login state is owned by account.session.",
  file_path: "/Users/dev/.coffer/knowledge/shopee/topics/session-ownership.md",
  folder_path: "/Users/dev/.coffer/knowledge/shopee/topics",
};

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

/** The collection's two identities, deliberately unlike each other: the uid the
 *  URL and the curate request carry, and the name the directory — and so every
 *  knowledge PATH — is built from. */
const COLLECTION_UID = "kn-8c1f";
const COLLECTION_NAME = "shopee";

/** The curate mutation, stubbed. `error` is how a 409 reaches the button. */
function stubCurate(overrides: { mutate?: ReturnType<typeof vi.fn>; error?: unknown } = {}) {
  const mutate = overrides.mutate ?? vi.fn();
  curateMock.mockReturnValue({
    mutate,
    isPending: false,
    error: overrides.error ?? null,
  } as unknown as ReturnType<typeof useCurateCollection>);
  return mutate;
}

/** Each lane answers for its own path, the way the real hook does — a tree stub
 *  that ignored the path would show the same files under both tabs, which is
 *  exactly the bug this page could have. */
function stubLanes({ sources = [SOURCE], topics = [TOPIC] } = {}) {
  treeMock.mockImplementation(
    (path: string) =>
      ({
        data: {
          path,
          directories: [],
          files: path.endsWith("/topics") ? topics : sources,
        },
        isPending: false,
        error: null,
      }) as unknown as ReturnType<typeof useKnowledgeTree>,
  );
  // The file query is enabled only while one is selected (`enabled:
  // Boolean(path)`), and answers for whichever lane's file was asked for.
  fileMock.mockImplementation(
    (path: string | null) =>
      ({
        data: path === TOPIC.path ? TOPIC : path ? SOURCE : undefined,
        isPending: false,
        error: null,
      }) as unknown as ReturnType<typeof useKnowledgeFile>,
  );
}

function stubInertDefaults() {
  runningMock.mockReturnValue(false);
  uploadMock.mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useUploadKnowledgeFile>);
}

beforeEach(() => {
  stubDelete();
  stubCurate();
  stubInertDefaults();
  stubLanes();
});

function renderPage() {
  // The header's reach control reads the collection's Resource, so the page
  // needs a real query client — the fetch never resolves here, and the control
  // renders from its own defaults.
  // The header's Curate button carries a tooltip, which Layout's provider
  // normally hosts; the page is rendered bare here, so mount one.
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[`/knowledge/${COLLECTION_UID}`]}>
          <Routes>
            <Route path="/knowledge/:uid" element={<KnowledgeDetailPage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

/** Switch lanes. Radix activates a tab on mousedown; `click` would not. */
function openTopics() {
  fireEvent.mouseDown(screen.getByRole("tab", { name: /topics/i }));
}

describe("KnowledgeDetailPage", () => {
  acceptance("knowledge", "the viewer edits sources and renders topics read-only", () => {
    renderPage();

    // --- the sources lane: open, reveal, delete -----------------------------
    fireEvent.click(screen.getByRole("button", { name: /Account Gateway/ }));
    expect(screen.getByText("The orchestration layer.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reveal/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /delete file/i })).toBeInTheDocument();

    // --- the topics lane: open and reveal only -----------------------------
    openTopics();
    expect(screen.getByRole("tab", { name: /topics/i })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("button", { name: /Session ownership/ }));

    expect(screen.getByText(/Login state is owned by account\.session\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reveal/i })).toBeInTheDocument();
    // No delete, no editor — curation is the only writer of this lane…
    expect(screen.queryByRole("button", { name: /delete file/i })).toBeNull();
    expect(screen.queryByRole("textbox", { name: /body|content/i })).toBeNull();
    // …and the page says so, rather than leaving the reader to discover it.
    expect(screen.getByText(/overwritten by the next pass/i)).toBeInTheDocument();
  });

  test("switching lanes leaves the pane on no file, not on the other lane's", () => {
    // A path belongs to one lane. Previewing a source beside the topics tree
    // would offer a source's delete under the Topics tab.
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Account Gateway/ }));
    expect(screen.getByText("The orchestration layer.")).toBeInTheDocument();

    openTopics();

    expect(screen.queryByText("The orchestration layer.")).toBeNull();
    expect(screen.getByText(/select a file/i)).toBeInTheDocument();
  });

  test("prompts for a selection before a file is chosen", () => {
    stubLanes({ sources: [], topics: [] });
    renderPage();
    expect(screen.getByText(/select a file/i)).toBeInTheDocument();
  });

  test("the one input beside a tree is a filter, not a retrieval box", () => {
    // The layer exposes no search and no grep (FR-050/FR-061). The only textbox
    // on the page narrows the names already on screen.
    renderPage();

    const boxes = screen.getAllByRole("textbox");
    expect(boxes).toHaveLength(1);
    expect(boxes[0]).toHaveAttribute("aria-label", "Filter by name…");
  });

  test("the Curate button is idle when nothing is running", () => {
    const mutate = stubCurate();
    renderPage();

    const button = screen.getByRole("button", { name: /^curate$/i });
    expect(button).not.toBeDisabled();
    expect(button.querySelector(".animate-spin")).toBeNull();
    fireEvent.click(button);
    expect(mutate).toHaveBeenCalled();
  });

  test("spins the Curate button while a pass this page did not start is running", () => {
    // The bug: the spinner used to come from the mutation's own `isPending`,
    // which a remount resets — so leaving the page mid-pass and coming back
    // showed an idle button and invited a second concurrent rewrite. The
    // running state is the daemon's answer now.
    runningMock.mockReturnValue(true);
    renderPage();

    const button = screen.getByRole("button", { name: /already running/i });
    expect(button).toBeDisabled();
    expect(button.querySelector(".animate-spin")).not.toBeNull();
  });

  test("a refused pass says one is already running, rather than going dead", () => {
    // The daemon refuses a second pass with 409 rather than queueing it. A
    // button that merely greyed out would say nothing about why.
    stubCurate({ error: new ApiError("UPKEEP_ALREADY_RUNNING", "a pass is running") });
    renderPage();

    const button = screen.getByRole("button", { name: /already running/i });
    expect(button).toBeDisabled();
  });

  test("the uid addresses the collection; its name builds every path", () => {
    // The split this page exists to hold: it is reached by an opaque uid, and
    // a knowledge `path` names a place on disk, where the collection's
    // directory is its NAME. So the trees, the title and the run-list lookup
    // all speak the name, and only the curate request speaks the uid.
    renderPage();

    expect(resourceMock).toHaveBeenCalledWith(COLLECTION_UID);
    expect(screen.getByRole("heading", { name: COLLECTION_NAME })).toBeInTheDocument();
    expect(curateMock).toHaveBeenCalledWith(COLLECTION_UID);
    // `/upkeep/runs` reports a running pass by the collection's name.
    expect(runningMock).toHaveBeenCalledWith("knowledge", COLLECTION_NAME);

    const askedFor = treeMock.mock.calls.map((call) => call[0]);
    expect(askedFor).toContain(`${COLLECTION_NAME}/sources`);
    expect(askedFor).toContain(`${COLLECTION_NAME}/topics`);
    expect(askedFor.some((path) => path.includes(COLLECTION_UID))).toBe(false);
  });

  test("offers the way back to the collection list", () => {
    // A collection is reached by clicking a row, so leaving it must not depend
    // on the browser's own back button — every other detail page carries this.
    renderPage();
    expect(screen.getByRole("link", { name: /back to knowledge/i })).toBeInTheDocument();
  });
});

// Deleting ONE source: the previewed file is the anchor — it is the file the
// user is looking at, and the only one the page can name for certain.
describe("KnowledgeDetailPage — deleting the previewed source", () => {
  /** Open the collection and click the tree row, so a source is being previewed. */
  function openSource() {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Account Gateway/ }));
  }

  test("offers nothing to delete until a file is being previewed", () => {
    // The page can only name the file it has open; with none open, a delete
    // button could only mean the collection, which is the list page's action.
    renderPage();
    expect(screen.queryByRole("button", { name: /delete file/i })).toBeNull();
  });

  test("the confirmation names the exact file path", () => {
    openSource();

    fireEvent.click(screen.getByRole("button", { name: /delete file/i }));
    expect(screen.getByRole("dialog")).toHaveTextContent("shopee/sources/gateway.md");
  });

  test("a refused delete keeps the dialog open with the reason", () => {
    const mutate = stubDelete({
      error: new ApiError("KNOWLEDGE_UNSAFE_PATH", "that path is outside the knowledge root"),
    });
    openSource();

    fireEvent.click(screen.getByRole("button", { name: /delete file/i }));
    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));

    expect(mutate).toHaveBeenCalledWith("shopee/sources/gateway.md", expect.anything());
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/outside the knowledge root/i);
  });

  test("a deleted file leaves the preview instead of previewing a 404", () => {
    const mutate = stubDelete({
      mutate: vi.fn((_path: string, opts?: { onSuccess?: () => void }) => opts?.onSuccess?.()),
    });
    openSource();
    expect(screen.getByText("The orchestration layer.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /delete file/i }));
    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));

    expect(mutate).toHaveBeenCalledWith("shopee/sources/gateway.md", expect.anything());
    expect(screen.queryByRole("dialog")).toBeNull();
    // Back to the empty pane: the file is gone, so re-reading it would 404.
    expect(screen.getByText(/select a file/i)).toBeInTheDocument();
  });
});
