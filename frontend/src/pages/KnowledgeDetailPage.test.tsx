// frontend/src/pages/KnowledgeDetailPage.test.tsx
//
// The collection viewer, which is ONE tree of documents rooted at the
// collection directory. Data hooks are mocked so the test asserts the page's
// own rendering: the tree (the inbox a folder in it), the document's body in
// the pane beside it, the same actions on every document whoever wrote it —
// Edit / Save included — and none on an inbox item, with no status control,
// no filter and no pending-material banner around them.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { useSyncExternalStore } from "react";
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
// screen — the title, and every `path` its tree asks for — is built from
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
  // this suite only exercises the tree + preview, so both get an inert default.
  useUploadKnowledgeFile: vi.fn(),
  useDeleteKnowledgeFile: vi.fn(),
  useSaveKnowledgeFile: vi.fn(),
}));

const {
  useKnowledgeTree,
  useKnowledgeFile,
  useCurateCollection,
  useUploadKnowledgeFile,
  useDeleteKnowledgeFile,
  useSaveKnowledgeFile,
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
const saveMock = vi.mocked(useSaveKnowledgeFile);

/** A document a person wrote. */
const MINE = {
  path: "shopee/gateway.md",
  title: "Account Gateway",
  description: "where account decisions are made",
  actor: "user" as const,
  created_at: "2026-09-12T00:00:00Z",
  updated_at: "2026-09-12T00:00:00Z",
  curated_at: "2026-09-13T00:00:00Z",
  body: "The orchestration layer.",
  file_path: "/Users/dev/.coffer/knowledge/shopee/gateway.md",
  folder_path: "/Users/dev/.coffer/knowledge/shopee",
  fingerprint: "fp-gateway-1",
  inbox: false,
};

/** A document curation wrote, one folder down. */
const CURATED = {
  path: "shopee/account/session-ownership.md",
  title: "Session ownership",
  description: "who owns a login session",
  actor: "agent" as const,
  created_at: "2026-09-12T00:00:00Z",
  updated_at: "2026-09-12T00:00:00Z",
  curated_at: "",
  body: "Login state is owned by account.session.",
  file_path: "/Users/dev/.coffer/knowledge/shopee/account/session-ownership.md",
  folder_path: "/Users/dev/.coffer/knowledge/shopee/account",
  fingerprint: "fp-session-1",
  inbox: false,
};

/** Material waiting in the collection's inbox to be merged — readable, never
 *  edited or deleted. */
const WAITING = {
  path: "shopee/.inbox/20260928-login-retry.md",
  title: "Login retry note",
  description: "",
  actor: "agent" as const,
  created_at: "2026-09-28T00:00:00Z",
  updated_at: "2026-09-28T00:00:00Z",
  curated_at: "",
  body: "Retries back off after three failures.",
  file_path: "/Users/dev/.coffer/knowledge/shopee/.inbox/20260928-login-retry.md",
  folder_path: "/Users/dev/.coffer/knowledge/shopee/.inbox",
  fingerprint: "fp-waiting-1",
  inbox: true,
};

/** What each path reads as. Mutable per test, so a save can change what the
 *  next render reads — the way the real save writes its cache entry. */
let documents: Record<string, typeof MINE | typeof CURATED | typeof WAITING> = {};
/** The pane's `reload`: the answer to a conflict. */
const refetch = vi.fn(async () => ({}));

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

/** The tree answers for its own path, the way the real hook does: the
 *  collection root lists its non-empty inbox first, then the `account` folder
 *  and one document; the folder holds the curated document and the inbox holds
 *  one item of material. */
function stubTree({ empty = false } = {}) {
  documents = { [MINE.path]: MINE, [CURATED.path]: CURATED, [WAITING.path]: WAITING };
  const levels: Record<string, { directories: unknown[]; files: unknown[] }> = {
    [COLLECTION_NAME]: {
      directories: [
        { path: "shopee/.inbox", name: ".inbox", file_count: 1, inbox: true },
        { path: "shopee/account", name: "account", file_count: 1, inbox: false },
      ],
      files: [MINE],
    },
    "shopee/account": { directories: [], files: [CURATED] },
    "shopee/.inbox": { directories: [], files: [WAITING] },
  };
  treeMock.mockImplementation(
    (path: string) =>
      ({
        data: empty
          ? { path, directories: [], files: [] }
          : { path, ...(levels[path] ?? { directories: [], files: [] }) },
        isPending: false,
        error: null,
      }) as unknown as ReturnType<typeof useKnowledgeTree>,
  );
  fileMock.mockImplementation(useStubbedFile);
}

/** Re-renders whoever reads `documents` — what a query cache update does. */
const listeners = new Set<() => void>();
function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The file query, stubbed over `documents`. It is enabled only while one is
 *  selected (`enabled: Boolean(path)`), answers for whichever document was
 *  asked for, and re-renders when a save writes that document — as the real
 *  save does by writing the query's cache entry. */
function useStubbedFile(path: string | null) {
  const data = useSyncExternalStore(subscribe, () => (path ? documents[path] : undefined));
  return { data, isPending: false, error: null, refetch } as unknown as ReturnType<
    typeof useKnowledgeFile
  >;
}

/** The save the pane's editor calls, stubbed. By default it succeeds and
 *  writes the new body where the next render reads it. */
function stubSave(impl?: (input: { path: string; body: string }) => Promise<string>) {
  const save = vi.fn(
    impl ??
      (async (input: { path: string; body: string }) => {
        documents = {
          ...documents,
          [input.path]: { ...documents[input.path], body: input.body, fingerprint: "fp-2" },
        };
        listeners.forEach((listener) => listener());
        return "fp-2";
      }),
  );
  saveMock.mockReturnValue(save as unknown as ReturnType<typeof useSaveKnowledgeFile>);
  return save;
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
  stubTree();
  stubSave();
  refetch.mockClear();
});

function renderPage(search = "") {
  // The header's Curate button carries a tooltip, which Layout's provider
  // normally hosts; the page is rendered bare here, so mount one.
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[`/knowledge/${COLLECTION_UID}${search}`]}>
          <Routes>
            <Route path="/knowledge/:uid" element={<KnowledgeDetailPage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

/** Open the `account` folder, which lists the curated document. */
function openAccountFolder() {
  fireEvent.click(screen.getByRole("button", { name: /^account$/ }));
}

describe("KnowledgeDetailPage", () => {
  acceptance("knowledge", "the viewer shows one tree of documents", () => {
    renderPage();

    // No tabs and no filter input: the collection is one tree, rooted at its
    // own directory.
    expect(screen.queryByRole("tab")).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();

    // --- a document a person wrote: edit, open, reveal, delete --------------
    fireEvent.click(screen.getByRole("button", { name: /Account Gateway/ }));
    expect(screen.getByText("The orchestration layer.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^edit$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reveal/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /delete document/i })).toBeInTheDocument();

    // --- a document curation wrote, in the same tree: the same actions -------
    openAccountFolder();
    fireEvent.click(screen.getByRole("button", { name: /Session ownership/ }));
    expect(screen.getByText(/Login state is owned by account\.session\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^edit$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reveal/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /delete document/i })).toBeInTheDocument();

    // --- the inbox: a folder in the same tree, its item read-only ------------
    fireEvent.click(screen.getByRole("button", { name: /waiting to merge/i }));
    fireEvent.click(screen.getByRole("button", { name: /Login retry note/ }));
    expect(screen.getByText("Retries back off after three failures.")).toBeInTheDocument();
    expect(screen.getByText(/disappears from here once merged/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^edit$/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /delete document/i })).toBeNull();
    expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
  });

  test("the inbox folder reads as an inbox, with how many items wait", () => {
    renderPage();
    const inbox = screen.getByRole("button", { name: /waiting to merge/i });
    expect(inbox).toHaveTextContent("1");
    expect(inbox).not.toHaveTextContent(".inbox");
    expect(inbox).toHaveAttribute("aria-expanded", "false");
    // It is listed first, ahead of the ordinary folders.
    const rows = screen.getAllByRole("button", { name: /waiting to merge|^account$/i });
    expect(rows[0]).toBe(inbox);
  });

  acceptance("knowledge", "edit a document in place", async () => {
    const save = stubSave();
    renderPage(`?file=${encodeURIComponent(MINE.path)}`);

    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    const editor = screen.getByRole("textbox", { name: /edit shopee\/gateway\.md/i });
    expect(editor).toHaveValue("The orchestration layer.");
    fireEvent.change(editor, { target: { value: "Rewritten by hand." } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() =>
      expect(save).toHaveBeenCalledWith({
        path: MINE.path,
        body: "Rewritten by hand.",
        expected_fingerprint: "fp-gateway-1",
      }),
    );
    // Back to the rendered view, showing what was saved.
    expect(await screen.findByText("Rewritten by hand.")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  test("a stale save keeps the draft and offers discard-and-reload", async () => {
    stubSave(() => Promise.reject(new ApiError("KNOWLEDGE_FILE_CONFLICT", "changed on disk")));
    renderPage(`?file=${encodeURIComponent(MINE.path)}`);

    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "my work" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/changed on disk since you opened it/i),
    );
    expect(screen.getByRole("textbox")).toHaveValue("my work");

    fireEvent.click(screen.getByRole("button", { name: /discard my edits/i }));
    await waitFor(() => expect(refetch).toHaveBeenCalled());
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  test("the tree is rooted at the collection directory", () => {
    renderPage();
    const askedFor = treeMock.mock.calls.map((call) => call[0]);
    expect(askedFor).toContain(COLLECTION_NAME);
    // The folder is listed, its contents are not fetched until it opens.
    expect(screen.getByRole("button", { name: /^account$/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Session ownership/ })).toBeNull();
  });

  test("the open document lives in the URL", () => {
    renderPage(`?file=${encodeURIComponent(MINE.path)}`);
    expect(screen.getByText("The orchestration layer.")).toBeInTheDocument();
  });

  test("no pending-material banner — the inbox is not reported as a count", () => {
    renderPage();
    expect(screen.queryByText(/being merged/i)).toBeNull();
  });

  acceptance("web-ui", "a kind that cannot be disabled shows no status control", () => {
    // The collection's page half: no reach or status button in the header.
    renderPage();
    expect(screen.queryByTestId("scope-control")).toBeNull();
    expect(screen.queryByRole("button", { name: /^(enabled|disabled|every agent)$/i })).toBeNull();
  });

  test("shows when curation last had the document, or that it never has", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Account Gateway/ }));
    expect(screen.getByText(/last curated/i)).toBeInTheDocument();

    openAccountFolder();
    fireEvent.click(screen.getByRole("button", { name: /Session ownership/ }));
    expect(screen.getByText(/not curated yet/i)).toBeInTheDocument();
  });

  test("prompts for a selection before a file is chosen", () => {
    stubTree({ empty: true });
    renderPage();
    expect(screen.getByText(/select a file/i)).toBeInTheDocument();
    expect(screen.getByText(/no documents yet/i)).toBeInTheDocument();
  });

  test("no input beside the tree — neither a filter nor a retrieval box", () => {
    // The layer exposes no search and no grep (spec knowledge "Present a
    // collection as one tree in the web UI"), and the tree has no filter.
    renderPage();
    expect(screen.queryByRole("textbox")).toBeNull();
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
    // directory is its NAME. So the tree, the title and the run-list lookup
    // all speak the name, and only the curate request speaks the uid.
    renderPage();

    expect(resourceMock).toHaveBeenCalledWith(COLLECTION_UID);
    expect(screen.getByRole("heading", { name: COLLECTION_NAME })).toBeInTheDocument();
    expect(curateMock).toHaveBeenCalledWith(COLLECTION_UID);
    // `/upkeep/runs` reports a running pass by the collection's name.
    expect(runningMock).toHaveBeenCalledWith("knowledge", COLLECTION_NAME);

    const askedFor = treeMock.mock.calls.map((call) => call[0]);
    expect(askedFor.some((path) => path.includes(COLLECTION_UID))).toBe(false);
  });

  test("offers the way back to the collection list", () => {
    // A collection is reached by clicking a row, so leaving it must not depend
    // on the browser's own back button — every other detail page carries this.
    renderPage();
    expect(screen.getByRole("link", { name: /back to knowledge/i })).toBeInTheDocument();
  });
});

// Deleting ONE document: the previewed file is the anchor — it is the file the
// user is looking at, and the only one the page can name for certain.
describe("KnowledgeDetailPage — deleting the previewed document", () => {
  /** Open the collection and click the tree row, so a document is being previewed. */
  function openDocument() {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Account Gateway/ }));
  }

  test("offers nothing to delete until a file is being previewed", () => {
    // The page can only name the file it has open; with none open, a delete
    // button could only mean the collection, which is the list page's action.
    renderPage();
    expect(screen.queryByRole("button", { name: /delete document/i })).toBeNull();
  });

  test("the confirmation names the exact file path", () => {
    openDocument();

    fireEvent.click(screen.getByRole("button", { name: /delete document/i }));
    expect(screen.getByRole("dialog")).toHaveTextContent("shopee/gateway.md");
  });

  test("a refused delete keeps the dialog open with the reason", () => {
    const mutate = stubDelete({
      error: new ApiError("KNOWLEDGE_UNSAFE_PATH", "that path is outside the knowledge root"),
    });
    openDocument();

    fireEvent.click(screen.getByRole("button", { name: /delete document/i }));
    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));

    expect(mutate).toHaveBeenCalledWith("shopee/gateway.md", expect.anything());
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/outside the knowledge root/i);
  });

  test("a deleted file leaves the preview instead of previewing a 404", () => {
    const mutate = stubDelete({
      mutate: vi.fn((_path: string, opts?: { onSuccess?: () => void }) => opts?.onSuccess?.()),
    });
    openDocument();
    expect(screen.getByText("The orchestration layer.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /delete document/i }));
    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));

    expect(mutate).toHaveBeenCalledWith("shopee/gateway.md", expect.anything());
    expect(screen.queryByRole("dialog")).toBeNull();
    // Back to the empty pane: the file is gone, so re-reading it would 404.
    expect(screen.getByText(/select a file/i)).toBeInTheDocument();
  });
});
