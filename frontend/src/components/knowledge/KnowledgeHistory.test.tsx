// frontend/src/components/knowledge/KnowledgeHistory.test.tsx
//
// The Knowledge page over the vault's history, mocked only at the network
// boundary: a document's History tab (versions with their writers, a diff,
// Restore this version, a failed read that leaves the Document tab working),
// Recent changes (a cross-collection timeline, the waiting items with Curate
// now, a collection filter) and one curation pass with Undo this pass — asked
// first, and a refusal that names the document changed since.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { answerFromFixtures, renderKnowledge } from "./knowledgeTestHarness";
import { EDIT, GATEWAY, NAME, OTHER, PASS, UID } from "./knowledgeTestData";
import { ApiError } from "@/lib/api/errors";

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
  restoreVersion: vi.fn(),
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
  test("lists versions with their writers, shows the diff and restores as a new version", async () => {
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

    expect(await screen.findByText("2 versions · newest first")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Curation.*Current/ })).toBeInTheDocument();
    const older = screen.getByRole("button", { name: /^You/ });
    expect(older).toHaveTextContent(`added gateway.md as written`);
    fireEvent.click(older);

    await waitFor(() => expect(api.getVersionDiff).toHaveBeenCalledWith(GATEWAY.path, "c0ffee01"));
    expect(await screen.findByText("The orchestration layer.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Restore this version" }));
    await waitFor(() =>
      expect(api.restoreVersion).toHaveBeenCalledWith({ path: GATEWAY.path, version: "c0ffee01" }),
    );
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

  test("a history that fails to load says so with a retry, and the Document tab still renders", async () => {
    api.getHistory.mockRejectedValue(new ApiError("KNOWLEDGE_HISTORY_UNAVAILABLE", "no git"));
    renderKnowledge(historyAddress);
    expect(await screen.findByText("Couldn't read this document's history")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(api.getHistory).toHaveBeenCalledTimes(2));

    fireEvent.mouseDown(screen.getByRole("tab", { name: "Document" }));
    expect(await screen.findByText("The orchestration layer.")).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent(`/knowledge/${UID}?file=`);
  });
});

describe("Recent changes", () => {
  test("a cross-collection timeline, the items waiting with Curate now, and a collection filter", async () => {
    api.curateCollection.mockResolvedValue({
      collection: NAME,
      status: "ok",
      total: 1,
      passes: [],
    });
    renderKnowledge("/knowledge");

    const pass = await screen.findByRole("link", {
      name: /Curation.*curated Codex's item into 2 documents/,
    });
    expect(pass).toHaveAttribute("href", `/knowledge/changes/${PASS.version}`);
    expect(screen.getByRole("link", { name: /You.*edited on-call.md/ })).toHaveTextContent(
      OTHER.name,
    );

    const waiting = screen.getByRole("region", { name: "Waiting to be curated" });
    expect(within(waiting).getByRole("link", { name: "Login retry" })).toBeInTheDocument();
    fireEvent.click(within(waiting).getByRole("button", { name: "Curate now" }));
    await waitFor(() => expect(api.curateCollection).toHaveBeenCalledWith(UID, null));

    // Writer filter: "You" leaves only the person's edit.
    fireEvent.click(screen.getByRole("button", { name: "You" }));
    expect(screen.queryByRole("link", { name: /Curation/ })).toBeNull();
    expect(screen.getByRole("link", { name: /edited on-call.md/ })).toBeInTheDocument();
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
  test("shows each document it changed with its diff, and undoes the whole pass after asking", async () => {
    api.undoPass.mockResolvedValue({
      ...PASS,
      version: "u9",
      operation: "undo",
      undoes: PASS.version,
    });
    renderKnowledge(`/knowledge/changes/${PASS.version}`);

    expect(await screen.findByText(GATEWAY.path)).toBeInTheDocument();
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
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      `Nothing was undone: ${GATEWAY.path} was changed after this pass`,
    );
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
