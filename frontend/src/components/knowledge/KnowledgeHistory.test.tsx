// frontend/src/components/knowledge/KnowledgeHistory.test.tsx
//
// The Knowledge page over the vault's history, mocked only at the network
// boundary: a document's History tab (versions with their writers, a diff,
// Restore this version, a failed read that leaves the Document tab working),
// Recent changes (a cross-collection timeline, the waiting items with Curate
// now, a collection filter, Restore on a delete) and one curation pass with
// Undo this pass — asked first, and a refusal that names the document changed
// since on the pass's page.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { answerFromFixtures, renderKnowledge } from "./knowledgeTestHarness";
import { EDIT, GATEWAY, NAME, OTHER, PASS, UID } from "./knowledgeTestData";
import { ApiError } from "@/lib/api/errors";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/api/knowledge", () => ({
  listCollections: vi.fn(),
  createCollection: vi.fn(),
  getTree: vi.fn(),
  getFile: vi.fn(),
  saveFile: vi.fn(),
  deleteFile: vi.fn(),
  curateCollection: vi.fn(),
  uploadFile: vi.fn(),
  submitMaterial: vi.fn(),
  listChanges: vi.fn(),
  getChange: vi.fn(),
  undoPass: vi.fn(),
  getHistory: vi.fn(),
  getVersionDiff: vi.fn(),
  getVersionBody: vi.fn(),
  restoreVersion: vi.fn(),
  restoreDeleted: vi.fn(),
  describeCollection: vi.fn(),
}));
vi.mock("@/lib/api/internalEngine", () => ({ internalEngineApi: { get: vi.fn() } }));
vi.mock("@/lib/api/upkeep", () => ({ listUpkeepRuns: vi.fn() }));
vi.mock("@/lib/hooks/useDaemonEvents", () => ({ useDaemonEvents: () => undefined }));

const api = vi.mocked(await import("@/lib/api/knowledge"));

beforeEach(() => {
  answerFromFixtures();
});
afterEach(() => {
  vi.clearAllMocks();
});

const historyAddress = `/knowledge/${UID}/history?file=${encodeURIComponent(GATEWAY.path)}`;

describe("a document's History tab", () => {
  acceptance("web-ui", "the history tab lists versions with their writers", async () => {
    const created = {
      ...EDIT,
      version: "c0ffee01",
      collections: [NAME],
      operation: "promote",
      documents: [{ path: GATEWAY.path, status: "added" as const, added: 3, removed: 0 }],
    };
    api.getHistory.mockResolvedValue({
      path: GATEWAY.path,
      versions: [
        { change: PASS, removed: false },
        { change: created, removed: false },
      ],
    });
    api.restoreVersion.mockResolvedValue(GATEWAY);
    renderKnowledge(historyAddress);

    expect(await screen.findByText("2 versions")).toBeInTheDocument();
    expect(screen.getByText("newest first")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Curation.*Current/ })).toBeInTheDocument();
    const older = screen.getByRole("button", { name: /^You/ });
    expect(older).toHaveTextContent("Added as written");
    fireEvent.click(older);

    await waitFor(() => expect(api.getVersionDiff).toHaveBeenCalledWith(GATEWAY.path, "c0ffee01"));
    expect(await screen.findByText("The orchestration layer.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Restore this version" }));
    await waitFor(() =>
      expect(api.restoreVersion).toHaveBeenCalledWith({ path: GATEWAY.path, version: "c0ffee01" }),
    );
    expect(await screen.findByText("Restored as a new version")).toBeInTheDocument();
  });

  test("Compare with current sets a version against the document as it is now", async () => {
    const older = { ...EDIT, version: "c0ffee01", collections: [NAME] };
    api.getHistory.mockResolvedValue({
      path: GATEWAY.path,
      versions: [
        { change: PASS, removed: false },
        { change: older, removed: false },
      ],
    });
    api.getVersionBody.mockResolvedValue({
      path: GATEWAY.path,
      version: "c0ffee01",
      body: "# Account Gateway\n\nThe old layer.",
    });
    renderKnowledge(historyAddress);
    fireEvent.click(await screen.findByRole("button", { name: /^You/ }));
    fireEvent.click(screen.getByRole("button", { name: "Compare with current" }));
    await waitFor(() => expect(api.getVersionBody).toHaveBeenCalledWith(GATEWAY.path, "c0ffee01"));
    expect(await screen.findByText("The old layer.")).toBeInTheDocument();
    expect(screen.getByText("The orchestration layer.")).toBeInTheDocument();
  });

  test("the current version offers no restore, and a pass links to the whole pass", async () => {
    api.getHistory.mockResolvedValue({
      path: GATEWAY.path,
      versions: [{ change: PASS, removed: false }],
    });
    renderKnowledge(historyAddress);
    expect(await screen.findByRole("link", { name: "See the whole pass" })).toHaveAttribute(
      "href",
      `/knowledge/changes/${PASS.version}`,
    );
    expect(screen.queryByRole("button", { name: "Restore this version" })).toBeNull();
  });

  acceptance("web-ui", "a history that fails to load leaves the document readable", async () => {
    api.getHistory.mockRejectedValue(new ApiError("KNOWLEDGE_HISTORY_UNAVAILABLE", "no git"));
    renderKnowledge(historyAddress);
    expect(await screen.findByText("Couldn't read this document's history")).toBeInTheDocument();
    const before = api.getHistory.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(api.getHistory.mock.calls.length).toBe(before + 1));

    fireEvent.click(screen.getByRole("link", { name: "Document" }));
    expect(await screen.findByText("The orchestration layer.")).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent(`/knowledge/${UID}?file=`);
  });
});

describe("Recent changes", () => {
  acceptance(
    "web-ui",
    "recent changes shows a cross-collection timeline with waiting items",
    async () => {
      api.curateCollection.mockResolvedValue({
        collection: NAME,
        status: "ok",
        total: 1,
        passes: [],
      });
      renderKnowledge("/knowledge");

      // The pass names what it curated and links to what it changed.
      const pass = await screen.findByRole("link", { name: "See the pass" });
      expect(pass).toHaveAttribute("href", `/knowledge/changes/${PASS.version}`);
      expect(screen.getByText("curated Codex's item into")).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "gateway.md" })).toHaveAttribute(
        "href",
        `/knowledge/${UID}?file=${encodeURIComponent(GATEWAY.path)}`,
      );
      // The person's edit in the other collection links to its document.
      expect(screen.getByRole("link", { name: "on-call.md" })).toHaveAttribute(
        "href",
        `/knowledge/${OTHER.uid}?file=${encodeURIComponent(`${OTHER.name}/on-call.md`)}`,
      );

      const waiting = screen.getByRole("region", { name: "Waiting to be curated" });
      expect(within(waiting).getByText("Login retry")).toBeInTheDocument();
      expect(within(waiting).getByRole("button", { name: "Curate now" })).toBeInTheDocument();

      // Filtering to the other collection asks for its changes only.
      api.listChanges.mockImplementation(async ({ collection }) => ({
        changes: collection === OTHER.name ? [EDIT] : [PASS, EDIT],
        waiting: [],
        next_cursor: null,
      }));
      const filter = screen.getByRole("combobox", { name: "Collection" });
      fireEvent.keyDown(filter, { key: "ArrowDown" });
      fireEvent.click(await screen.findByRole("option", { name: OTHER.name }));
      await waitFor(() =>
        expect(api.listChanges).toHaveBeenLastCalledWith(
          expect.objectContaining({ collection: OTHER.name }),
        ),
      );
      await waitFor(() => expect(screen.queryByRole("link", { name: "See the pass" })).toBeNull());
      expect(screen.getByRole("link", { name: "on-call.md" })).toBeInTheDocument();
    },
  );

  test("a waiting item opens in its collection's inbox", async () => {
    renderKnowledge("/knowledge");
    const waiting = await screen.findByRole("region", { name: "Waiting to be curated" });
    fireEvent.click(within(waiting).getByRole("button", { name: "Open Login retry" }));
    expect(screen.getByTestId("where")).toHaveTextContent(`/knowledge/${UID}/inbox?file=`);
  });

  test("Curate now in Recent changes curates each collection with items waiting", async () => {
    api.curateCollection.mockResolvedValue({
      collection: NAME,
      status: "ok",
      total: 1,
      passes: [],
    });
    renderKnowledge("/knowledge");
    const waiting = await screen.findByRole("region", { name: "Waiting to be curated" });
    fireEvent.click(within(waiting).getByRole("button", { name: "Curate now" }));
    await waitFor(() => expect(api.curateCollection).toHaveBeenCalledWith(UID, null));
  });

  test("the writer filter leaves only the person's own changes under You", async () => {
    renderKnowledge("/knowledge");
    expect(await screen.findByRole("link", { name: "See the pass" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "You" }));
    expect(screen.queryByRole("link", { name: "See the pass" })).toBeNull();
    expect(screen.getByRole("link", { name: "on-call.md" })).toBeInTheDocument();
  });

  test("no change and nothing waiting says so", async () => {
    api.listChanges.mockResolvedValue({ changes: [], waiting: [], next_cursor: null });
    renderKnowledge("/knowledge");
    expect(await screen.findByText("No changes in the last 7 days.")).toBeInTheDocument();
    expect(screen.getByText(/Nothing waiting/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Curate now" })).toBeNull();
  });
});

describe("a curation pass", () => {
  acceptance("web-ui", "a pass is inspected and undone as a whole", async () => {
    api.undoPass.mockResolvedValue({
      ...PASS,
      version: "u9",
      operation: "undo",
      undoes: PASS.version,
    });
    renderKnowledge(`/knowledge/changes/${PASS.version}`);

    expect(await screen.findByRole("link", { name: GATEWAY.path })).toBeInTheDocument();
    expect(screen.getAllByText("The orchestration layer.").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "History" })[0]).toHaveAttribute(
      "href",
      `/knowledge/${UID}/history?file=${encodeURIComponent(GATEWAY.path)}`,
    );

    fireEvent.click(screen.getByRole("button", { name: "Undo this pass" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Undo this curation pass?")).toBeInTheDocument();
    expect(api.undoPass).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Undo pass" }));
    await waitFor(() => expect(api.undoPass).toHaveBeenCalledWith(PASS.version));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  test("a refused undo names the document changed since and writes nothing", async () => {
    api.undoPass.mockRejectedValue(
      new ApiError("KNOWLEDGE_UNDO_CONFLICT", "changed since", {
        version: PASS.version,
        document: GATEWAY.path,
        later_version: "ffff",
      }),
    );
    renderKnowledge(`/knowledge/changes/${PASS.version}`);
    fireEvent.click(await screen.findByRole("button", { name: "Undo this pass" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Undo pass" }));
    // The dialog steps aside; the pass's page says what happened and names the
    // document changed since.
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(await screen.findByText("Couldn't undo this pass")).toBeInTheDocument();
    expect(screen.getByText(/was edited after this pass, so nothing was undone/)).toHaveTextContent(
      `${GATEWAY.path} was edited after this pass, so nothing was undone`,
    );
    expect(screen.getByText("Not undone")).toBeInTheDocument();
    expect(screen.getByText("changed after this pass")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Undo this pass" })).toBeNull();
  });

  test("a pass already undone says so instead of offering undo", async () => {
    api.listChanges.mockResolvedValue({
      changes: [{ ...PASS, version: "u9", operation: "undo", undoes: PASS.version }, PASS],
      waiting: [],
      next_cursor: null,
    });
    renderKnowledge(`/knowledge/changes/${PASS.version}`);
    expect(await screen.findByText("Undone")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Undo this pass" })).toBeNull();
  });
});

describe("restore a delete from Recent changes", () => {
  const REMOVAL = {
    ...EDIT,
    version: "d31e7e00",
    operation: "remove",
    summary: "Remove collection runbooks",
    collections: [OTHER.name],
    documents: [
      { path: `${OTHER.name}/README.md`, status: "removed" as const, added: 0, removed: 3 },
      { path: `${OTHER.name}/on-call.md`, status: "removed" as const, added: 0, removed: 9 },
    ],
  };
  const DELETE = {
    ...EDIT,
    version: "de1e7e00",
    operation: "delete",
    summary: "Delete",
    collections: [NAME],
    documents: [{ path: GATEWAY.path, status: "removed" as const, added: 0, removed: 3 }],
  };

  acceptance("knowledge", "restore a deleted collection from Recent changes", async () => {
    api.listChanges.mockResolvedValue({ changes: [REMOVAL], waiting: [], next_cursor: null });
    api.restoreDeleted.mockResolvedValue({
      ...REMOVAL,
      version: "r3570be0",
      operation: "restore",
      restored_from: REMOVAL.version,
      documents: REMOVAL.documents.map((d) => ({ ...d, status: "added" as const })),
    });
    renderKnowledge("/knowledge");

    // The delete of a whole collection is listed, by the collection's name, with Restore.
    const verb = await screen.findByText("deleted the collection");
    const row = verb.closest("li") as HTMLElement;
    expect(within(row).getByText(OTHER.name)).toBeInTheDocument();
    fireEvent.click(within(row).getByRole("button", { name: "Restore" }));
    await waitFor(() => expect(api.restoreDeleted).toHaveBeenCalledWith(REMOVAL.version));
    expect(await screen.findByText(`Restored ${OTHER.name}`)).toBeInTheDocument();
  });

  test("restore a deleted document", async () => {
    api.listChanges.mockResolvedValue({ changes: [DELETE], waiting: [], next_cursor: null });
    api.restoreDeleted.mockResolvedValue({ ...DELETE, version: "r2", operation: "restore" });
    renderKnowledge("/knowledge");
    expect(await screen.findByText("deleted")).toBeInTheDocument();
    expect(
      screen.getByText("Removed from the collection; its versions stay in the vault's history."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Restore" }));
    await waitFor(() => expect(api.restoreDeleted).toHaveBeenCalledWith(DELETE.version));
  });

  test("a restore that would overwrite is refused on the delete's row", async () => {
    api.listChanges.mockResolvedValue({ changes: [DELETE], waiting: [], next_cursor: null });
    api.restoreDeleted.mockRejectedValue(
      new ApiError("KNOWLEDGE_RESTORE_CONFLICT", "exists again", { document: GATEWAY.path }),
    );
    renderKnowledge("/knowledge");
    fireEvent.click(await screen.findByRole("button", { name: "Restore" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Not restored: a document exists at that path again.",
    );
  });

  test("a delete a later change restored reads Restored", async () => {
    api.listChanges.mockResolvedValue({
      changes: [
        { ...DELETE, version: "r2", operation: "restore", restored_from: DELETE.version },
        DELETE,
      ],
      waiting: [],
      next_cursor: null,
    });
    renderKnowledge("/knowledge");
    expect(await screen.findByText("Restored")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Restore" })).toBeNull();
  });
});
