// frontend/src/components/knowledge/KnowledgeCollectionLog.test.tsx
//
// A collection page's To do and Change log (spec knowledge "Show a collection
// as one tree of read-only documents in the web UI", "Record a tidy as one
// change", "Undo a tidy"): the findings grouped by kind, most severe first,
// each page by title opening its file; the changes feed for the collection on
// a timeline — what each did, its writer and time, its files by title, each
// opening that file at its history — a tidy as one entry with its report and
// Undo this tidy…, edits on disk close together as one entry, and Show more
// while more are left. Mocked only at the network boundary.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import { answerFromFixtures, renderKnowledge } from "@/test/knowledgeHarness";

import { ApiError } from "@/lib/api/errors";

import { COLLECTION, GATEWAY, NAME, RELEASE, SESSION, UID, change } from "./knowledgeTestData";

vi.mock("@/lib/api/knowledge", () => ({
  listCollections: vi.fn(),
  createCollection: vi.fn(),
  getTree: vi.fn(),
  getFile: vi.fn(),
  deleteFile: vi.fn(),
  uploadFile: vi.fn(),
  listChanges: vi.fn(),
  restoreDeleted: vi.fn(),
  describeCollection: vi.fn(),
  getCheck: vi.fn(),
  getCollectionFiles: vi.fn(),
  undoChange: vi.fn(),
}));
vi.mock("@/lib/api/vault", () => ({
  vaultApi: { history: vi.fn(), diff: vi.fn(), restore: vi.fn() },
}));
vi.mock("@/lib/api/agentProviders", () => ({
  agentProvidersApi: { list: vi.fn().mockResolvedValue({ agents: [] }) },
}));
vi.mock("@/lib/hooks/useDaemonEvents", () => ({ useDaemonEvents: () => undefined }));

const api = vi.mocked(await import("@/lib/api/knowledge"));
const { vaultApi } = await import("@/lib/api/vault");
const ROOT = `/knowledge/${UID}`;

const AGENT_EDIT = change({
  version: "a9e3",
  writer: "agent",
  agent: "claude-code",
  operation: "edit",
  documents: [{ path: GATEWAY.path, status: "modified", added: 4, removed: 1 }],
});

beforeEach(() => {
  answerFromFixtures();
  vi.mocked(vaultApi.history).mockResolvedValue({
    path: `knowledge/${GATEWAY.path}`,
    versions: [],
    next_cursor: null,
  });
});
afterEach(() => {
  vi.clearAllMocks();
});

describe("the Change log", () => {
  acceptance("knowledge", "a collection's change log opens a file at its history", async () => {
    api.listChanges.mockResolvedValue({ changes: [AGENT_EDIT], next_cursor: null });
    renderKnowledge(ROOT);
    const log = await screen.findByRole("region", { name: "Change log" });
    // One row: what it did, its writer and time, the file it touched.
    expect(await within(log).findByText("Edited")).toBeInTheDocument();
    expect(within(log).getByText(/^Claude Code · Today/)).toBeInTheDocument();
    expect(within(log).getByText("+4 −1")).toBeInTheDocument();
    expect(api.listChanges).toHaveBeenCalledWith(expect.objectContaining({ collection: NAME }));

    fireEvent.click(within(log).getByRole("link", { name: GATEWAY.title }));
    // The page opens at its history.
    await waitFor(() =>
      expect(screen.getByTestId("where")).toHaveTextContent(
        `${ROOT}?file=${encodeURIComponent(GATEWAY.path)}&history=1`,
      ),
    );
    expect(
      await screen.findByRole("region", { name: "History of gateway.md" }),
    ).toBeInTheDocument();
    await waitFor(() => expect(vaultApi.history).toHaveBeenCalledWith(`knowledge/${GATEWAY.path}`));
  });

  test("Show more reads the next page while more are left", async () => {
    api.listChanges
      .mockResolvedValueOnce({ changes: [AGENT_EDIT], next_cursor: "p2" })
      .mockResolvedValueOnce({
        changes: [change({ version: "f1le", writer: "daemon", operation: "layout" })],
        next_cursor: null,
      });
    renderKnowledge(ROOT);
    const log = await screen.findByRole("region", { name: "Change log" });
    fireEvent.click(await within(log).findByRole("button", { name: "Show more" }));
    expect(await within(log).findByText("Filed into pages")).toBeInTheDocument();
    expect(within(log).getByText(/^Coffer · /)).toBeInTheDocument();
    expect(api.listChanges).toHaveBeenLastCalledWith(expect.objectContaining({ cursor: "p2" }));
    expect(within(log).queryByRole("button", { name: "Show more" })).toBeNull();
  });

  test("a collection with no changes says so", async () => {
    renderKnowledge(ROOT);
    const log = await screen.findByRole("region", { name: "Change log" });
    expect(await within(log).findByText("No changes yet.")).toBeInTheDocument();
  });
});

describe("a tidy in the Change log", () => {
  const TIDY = change({
    version: "t1dy",
    writer: "agent",
    agent: "claude-code",
    operation: "tidy",
    status: "reported",
    summary: "Integrated the release notes; merged two gateway pages; left the cache TTL question.",
    documents: [
      { path: GATEWAY.path, status: "modified", added: 9, removed: 4 },
      { path: SESSION.path, status: "modified", added: 2, removed: 2 },
      { path: `${NAME}/pages/cache.md`, status: "added", added: 12, removed: 0 },
    ],
  });
  const minutesAgo = (n: number) => new Date(Date.now() - n * 60_000).toISOString();

  acceptance(
    "knowledge",
    "a tidy shows in the change log as one entry with its report and Undo",
    async () => {
      api.listChanges.mockResolvedValue({
        changes: [
          change({
            version: "d2",
            writer: "disk",
            operation: "edit",
            time: minutesAgo(1),
            documents: [{ path: GATEWAY.path, status: "modified", added: 1, removed: 0 }],
          }),
          change({
            version: "d1",
            writer: "disk",
            operation: "edit",
            time: minutesAgo(6),
            documents: [{ path: SESSION.path, status: "modified", added: 1, removed: 1 }],
          }),
          { ...TIDY, time: minutesAgo(30) },
          change({
            version: "exp1",
            writer: "agent",
            operation: "tidy",
            status: "expired",
            summary: "Tidied shopee",
            time: minutesAgo(90),
            documents: [{ path: GATEWAY.path, status: "modified", added: 1, removed: 1 }],
          }),
        ],
        next_cursor: null,
      });
      renderKnowledge(ROOT);
      const log = await screen.findByRole("region", { name: "Change log" });
      const entries = await within(log).findAllByRole("listitem", {
        name: (_n, el) => el.parentElement?.getAttribute("aria-label") === "Change log",
      });
      // The two disk edits five minutes apart are one entry listing both files.
      expect(entries).toHaveLength(3);
      expect(entries[0]).toHaveTextContent("2 saves");
      expect(within(entries[0]).getByRole("link", { name: GATEWAY.title })).toBeInTheDocument();
      expect(within(entries[0]).getByRole("link", { name: SESSION.title })).toBeInTheDocument();
      // The tidy: its agent, time, report, pages by title, and Undo this tidy….
      const tidy = entries[1];
      expect(within(tidy).getByText("Tidy")).toBeInTheDocument();
      expect(within(tidy).getByText(/^Claude Code · Today/)).toBeInTheDocument();
      expect(within(tidy).getByText(TIDY.summary)).toBeInTheDocument();
      expect(within(tidy).getByRole("link", { name: GATEWAY.title })).toBeInTheDocument();
      expect(within(tidy).getByRole("link", { name: "pages/cache.md" })).toBeInTheDocument();
      expect(within(tidy).getByRole("button", { name: "Undo this tidy…" })).toBeInTheDocument();
      // The expired tidy reads closed without a report.
      expect(entries[2]).toHaveTextContent("Closed without a report");
      expect(entries[2]).not.toHaveTextContent("Tidied shopee");
    },
  );

  test("Undo this tidy… asks first, then undoes it as one change", async () => {
    api.listChanges.mockResolvedValue({ changes: [TIDY], next_cursor: null });
    api.undoChange.mockResolvedValue(
      change({ version: "u1", operation: "restore", undoes: TIDY.version }),
    );
    renderKnowledge(ROOT);
    const log = await screen.findByRole("region", { name: "Change log" });
    fireEvent.click(await within(log).findByRole("button", { name: "Undo this tidy…" }));
    const dialog = await screen.findByRole("dialog", { name: "Undo this tidy?" });
    expect(dialog).toHaveTextContent("The 3 files it changed go back");
    expect(api.undoChange).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Undo tidy" }));
    await waitFor(() => expect(api.undoChange).toHaveBeenCalledWith(TIDY.version, false));
    expect(await screen.findByText("Tidy undone")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  acceptance("knowledge", "undoing a tidy whose files changed since asks first", async () => {
    api.listChanges
      .mockResolvedValueOnce({ changes: [TIDY], next_cursor: null })
      .mockResolvedValue({
        changes: [change({ version: "u1", operation: "restore", undoes: TIDY.version }), TIDY],
        next_cursor: null,
      });
    api.undoChange
      .mockRejectedValueOnce(
        new ApiError("KNOWLEDGE_UNDO_CONFLICT", "edited since", {
          version: TIDY.version,
          documents: [GATEWAY.path],
        }),
      )
      .mockResolvedValueOnce(change({ version: "u1", operation: "restore", undoes: TIDY.version }));
    renderKnowledge(ROOT);
    const log = await screen.findByRole("region", { name: "Change log" });
    fireEvent.click(await within(log).findByRole("button", { name: "Undo this tidy…" }));
    fireEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Undo tidy" }),
    );
    // The second question names the edited page by title and offers Undo anyway.
    const conflict = await screen.findByRole("dialog", {
      name: "Some files changed since this tidy",
    });
    expect(within(conflict).getByText(GATEWAY.title)).toBeInTheDocument();
    expect(api.undoChange).toHaveBeenCalledTimes(1);
    fireEvent.click(within(conflict).getByRole("button", { name: "Undo anyway" }));
    await waitFor(() => expect(api.undoChange).toHaveBeenLastCalledWith(TIDY.version, true));
    // The Change log shows the undo, and the tidy as undone with no Undo of its own.
    expect(await within(log).findByText("Undid a tidy")).toBeInTheDocument();
    expect(within(log).getByText("Undone")).toBeInTheDocument();
    expect(within(log).queryByRole("button", { name: "Undo this tidy…" })).toBeNull();
  });
});

describe("To do", () => {
  test("lists the findings grouped by kind, most severe first, each page by title opening its file", async () => {
    api.getCheck.mockResolvedValue({
      collection: COLLECTION,
      findings: [
        { kind: "waiting_source", path: RELEASE.path, target: null, others: [] },
        { kind: "dead_link", path: GATEWAY.path, target: "gone", others: [] },
        { kind: "orphan_page", path: GATEWAY.path, target: null, others: [] },
      ],
    });
    renderKnowledge(ROOT);
    const todo = await screen.findByRole("region", { name: "To do" });
    // The kinds that break a reader first; the minor ones folded into a row.
    const groups = (await within(todo).findAllByRole("heading", { level: 3 })).map(
      (h) => h.firstChild?.textContent,
    );
    expect(groups).toEqual(["Dead links", "Waiting sources"]);
    expect(within(todo).getByText("→ gone")).toBeInTheDocument();
    expect(within(todo).getByRole("button", { name: "Pages nothing links to 1" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );

    fireEvent.click(await within(todo).findByRole("link", { name: RELEASE.title }));
    await waitFor(() =>
      expect(screen.getByTestId("where")).toHaveTextContent(
        `${ROOT}?file=${encodeURIComponent(RELEASE.path)}`,
      ),
    );
    expect(await screen.findByRole("heading", { level: 1, name: RELEASE.title })).toBeVisible();
  });

  test("says when there is nothing to do", async () => {
    renderKnowledge(ROOT);
    const todo = await screen.findByRole("region", { name: "To do" });
    expect(await within(todo).findByText("Nothing to do.")).toBeInTheDocument();
    expect(api.getCheck).toHaveBeenCalledWith(UID);
  });
});
