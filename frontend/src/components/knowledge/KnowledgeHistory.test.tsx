// frontend/src/components/knowledge/KnowledgeHistory.test.tsx
//
// The Knowledge page over the vault's history, mocked only at the network
// boundary: a document's History tab (versions with their writers, a diff,
// Restore this version, a failed read that leaves the Document tab working) and
// Recent changes (a cross-collection timeline, a collection filter, Restore on
// a delete). A version an earlier curation pass wrote keeps its curation label.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { answerFromFixtures, renderKnowledge } from "@/test/knowledgeHarness";
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
  uploadFile: vi.fn(),
  listChanges: vi.fn(),
  getHistory: vi.fn(),
  getVersionDiff: vi.fn(),
  getVersionBody: vi.fn(),
  restoreVersion: vi.fn(),
  restoreDeleted: vi.fn(),
  describeCollection: vi.fn(),
}));
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

    expect(await screen.findAllByRole("listitem")).toHaveLength(2);
    expect(screen.queryByText("2 versions")).toBeNull();
    expect(screen.queryByText("newest first")).toBeNull();
    expect(await screen.findByText("Current")).toBeInTheDocument();
    const older = screen.getByRole("button", { name: /^You/ });
    expect(older).not.toHaveAttribute("aria-current");
    fireEvent.click(older);
    expect(older).toHaveAttribute("aria-current", "true");

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

  test("the current version offers no restore, and an earlier curation pass keeps its label", async () => {
    api.getHistory.mockResolvedValue({
      path: GATEWAY.path,
      versions: [{ change: PASS, removed: false }],
    });
    renderKnowledge(historyAddress);
    fireEvent.click(await screen.findByRole("button", { name: /^Curation/ }));
    expect(screen.queryByRole("link", { name: "See the pass" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Restore this version" })).toBeNull();
  });

  acceptance("web-ui", "a history that fails to load leaves the document readable", async () => {
    api.getHistory.mockRejectedValue(new ApiError("KNOWLEDGE_HISTORY_UNAVAILABLE", "no git"));
    renderKnowledge(historyAddress);
    expect(await screen.findByText("Couldn’t read this document’s history")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Activity" })).toHaveAttribute(
      "href",
      "/activity",
    );
    const before = api.getHistory.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(api.getHistory.mock.calls.length).toBe(before + 1));

    fireEvent.click(screen.getByRole("link", { name: "Document" }));
    expect(await screen.findByText("The orchestration layer.")).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent(`/knowledge/${UID}?file=`);
  });
});

describe("Recent changes", () => {
  test("a collection filter asks for that collection's changes only", async () => {
    renderKnowledge("/knowledge");

    // A change an earlier curation pass made links to what it changed.
    expect(await screen.findByRole("link", { name: "gateway.md" })).toHaveAttribute(
      "href",
      `/knowledge/${UID}?file=${encodeURIComponent(GATEWAY.path)}`,
    );
    // The person's edit in the other collection links to its document.
    expect(screen.getByRole("link", { name: "on-call.md" })).toHaveAttribute(
      "href",
      `/knowledge/${OTHER.uid}?file=${encodeURIComponent(`${OTHER.name}/on-call.md`)}`,
    );

    // Filtering to the other collection asks for its changes only.
    api.listChanges.mockImplementation(async ({ collection }) => ({
      changes: collection === OTHER.name ? [EDIT] : [PASS, EDIT],
      next_cursor: null,
    }));
    fireEvent.click(screen.getByRole("button", { name: /^Collection/ }));
    fireEvent.click(await screen.findByRole("option", { name: OTHER.name }));
    await waitFor(() =>
      expect(api.listChanges).toHaveBeenLastCalledWith(
        expect.objectContaining({ collection: OTHER.name }),
      ),
    );
    expect(screen.getByTestId("where")).toHaveTextContent(`collection=${OTHER.name}`);
    await waitFor(() => expect(screen.queryByRole("link", { name: "gateway.md" })).toBeNull());
    expect(screen.getByRole("link", { name: "on-call.md" })).toBeInTheDocument();
  });

  test("the writer filter leaves only the person's own changes under You", async () => {
    renderKnowledge("/knowledge");
    expect(await screen.findByRole("link", { name: "gateway.md" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Author/ }));
    fireEvent.click(await screen.findByRole("option", { name: "You" }));
    expect(screen.getByTestId("where")).toHaveTextContent("author=user");
    expect(screen.queryByRole("link", { name: "gateway.md" })).toBeNull();
    expect(screen.getByRole("link", { name: "on-call.md" })).toBeInTheDocument();
  });

  test("no change says so, with nothing waiting and no Curate now", async () => {
    api.listChanges.mockResolvedValue({ changes: [], next_cursor: null });
    renderKnowledge("/knowledge");
    expect(await screen.findByText("No changes in the last 7 days.")).toBeInTheDocument();
    expect(screen.queryByText(/Nothing waiting/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Curate now" })).toBeNull();
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
    api.listChanges.mockResolvedValue({ changes: [REMOVAL], next_cursor: null });
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
    api.listChanges.mockResolvedValue({ changes: [DELETE], next_cursor: null });
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
    api.listChanges.mockResolvedValue({ changes: [DELETE], next_cursor: null });
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
      next_cursor: null,
    });
    renderKnowledge("/knowledge");
    expect(await screen.findByText("Restored")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Restore" })).toBeNull();
  });
});
