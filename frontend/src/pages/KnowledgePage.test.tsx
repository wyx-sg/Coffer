// frontend/src/pages/KnowledgePage.test.tsx
//
// The Knowledge page's tree, reader and editor (spec knowledge "Show a
// collection as one tree of documents in the web UI"), mocked only at the
// network boundary: one tree of collections with their documents; the document
// pane with Edit, open-in-editor, reveal and delete (at once, with an Undo
// toast); the body-only editor saving with the fingerprint it read and
// refusing a stale save with Compare / Copy my text / Reload.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { answerFromFixtures, renderKnowledge } from "@/test/knowledgeHarness";
import {
  COLLECTION,
  GATEWAY,
  NAME,
  PASS,
  SESSION,
  UID,
} from "@/components/knowledge/knowledgeTestData";
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

function tree() {
  return screen.getByRole("navigation", { name: "Collections and documents" });
}

describe("the collection tree and the document pane", () => {
  acceptance("knowledge", "the viewer shows one tree of documents", async () => {
    renderKnowledge(`/knowledge/${UID}`);

    const nav = await screen.findByRole("navigation", { name: "Collections and documents" });
    // One tree: no lane headings, no tabs, no filter input.
    expect(within(nav).queryByRole("tab")).toBeNull();
    expect(screen.queryByRole("button", { name: "Add a document" })).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("searchbox")).toBeNull();
    // Both documents — the root one and the one in a folder, opened on the way —
    // each named by its file, as it is on disk.
    expect(await within(nav).findByRole("button", { name: "gateway.md" })).toBeInTheDocument();
    fireEvent.click(within(nav).getByRole("button", { name: "account" }));
    expect(await within(nav).findByRole("button", { name: "session.md" })).toBeInTheDocument();
    // No Inbox node: material becomes a document on arrival.
    expect(within(nav).queryByRole("button", { name: /^Inbox/ })).toBeNull();

    // A document offers Edit, open-in-editor, reveal and delete.
    fireEvent.click(within(nav).getByRole("button", { name: "gateway.md" }));
    expect(await screen.findByRole("button", { name: "Edit" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: `More actions for ${GATEWAY.path}` }));
    expect(screen.getByRole("menuitem", { name: "Open in editor" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Reveal in Finder" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Delete document…" })).toBeInTheDocument();
  });

  test("a collection opened from Recent changes stays open when a document in it is opened", async () => {
    renderKnowledge("/knowledge");
    fireEvent.click(await within(tree()).findByRole("button", { name: `Expand ${NAME}` }));
    fireEvent.click(await within(tree()).findByRole("button", { name: "gateway.md" }));
    expect(await screen.findByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(within(tree()).getByRole("button", { name: "gateway.md" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    // Its chevron still closes it.
    fireEvent.click(within(tree()).getByRole("button", { name: `Collapse ${NAME}` }));
    expect(within(tree()).queryByRole("button", { name: "gateway.md" })).toBeNull();
  });

  test("a collection closed on its chevron opens again when a link leads into it", async () => {
    renderKnowledge(`/knowledge/${UID}`);
    fireEvent.click(await within(tree()).findByRole("button", { name: `Collapse ${NAME}` }));
    expect(within(tree()).queryByRole("button", { name: "gateway.md" })).toBeNull();
    // Leave for Recent changes, then come back in through a document link.
    fireEvent.click(within(tree()).getByRole("link", { name: /Recent changes/ }));
    fireEvent.click(await screen.findByRole("link", { name: "gateway.md" }));
    expect(await within(tree()).findByRole("button", { name: "gateway.md" })).toBeInTheDocument();
  });

  test("a deep link opens the folders on the way to its document", async () => {
    renderKnowledge(`/knowledge/${UID}?file=${encodeURIComponent(SESSION.path)}`);
    const row = await within(
      await screen.findByRole("navigation", { name: "Collections and documents" }),
    ).findByRole("button", { name: "session.md" });
    expect(row).toHaveAttribute("aria-current", "page");
    expect(await screen.findByText("Login state is owned by account.session.")).toBeInTheDocument();
  });
});

describe("the body-only editor", () => {
  acceptance("knowledge", "edit a document in place", async () => {
    const saved = { ...GATEWAY, body: "Rewritten.", fingerprint: "fp-2" };
    api.saveFile.mockImplementation(async () => {
      api.getFile.mockResolvedValue(saved);
      return saved;
    });
    renderKnowledge(`/knowledge/${UID}?file=${encodeURIComponent(GATEWAY.path)}`);
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));

    // Title and description are read-only metadata; the textarea holds the body.
    expect(screen.getByText("where account decisions are made")).toBeInTheDocument();
    const editor = screen.getByRole("textbox", { name: `Edit ${GATEWAY.path}` });
    expect(editor).toHaveValue(GATEWAY.body);
    fireEvent.change(editor, { target: { value: "Rewritten." } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(api.saveFile).toHaveBeenCalledWith({
        path: GATEWAY.path,
        body: "Rewritten.",
        expected_fingerprint: GATEWAY.fingerprint,
      }),
    );
    expect(await screen.findByText("Rewritten.")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: `Edit ${GATEWAY.path}` })).toBeNull();
  });

  acceptance("knowledge", "a stale save offers compare, copy and reload", async () => {
    api.saveFile.mockRejectedValue(
      new ApiError("KNOWLEDGE_FILE_CONFLICT", "changed on disk", {
        saved: false,
        current_body: "# Account Gateway\n\nAn agent added a line.",
        current_fingerprint: "fp-new",
      }),
    );
    renderKnowledge(`/knowledge/${UID}?file=${encodeURIComponent(GATEWAY.path)}`);
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByRole("textbox", { name: `Edit ${GATEWAY.path}` }), {
      target: { value: "My version." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This document changed on disk while you were editing");
    expect(alert).toHaveTextContent(/gateway\.md/);
    expect(alert).toHaveTextContent("Your text isn’t saved yet.");
    expect(screen.getByText("Not saved")).toBeInTheDocument();
    // No second save over it.
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(within(alert).getByRole("button", { name: "Copy my text" })).toBeInTheDocument();
    // Reload asks before it drops the text.
    expect(within(alert).getByRole("button", { name: "Reload…" })).toBeInTheDocument();
    // Compare is an in-page view, not a dialog.
    fireEvent.click(within(alert).getByRole("button", { name: "Compare" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("radio", { name: /Keep my edit/ })).toBeChecked();
    expect(screen.getByRole("radio", { name: /Take the version on disk/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save my edit" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Back to editing" }));
    expect(screen.getByRole("textbox", { name: `Edit ${GATEWAY.path}` })).toHaveValue(
      "My version.",
    );
  });
});

describe("delete a document", () => {
  acceptance("knowledge", "delete a document at once and undo it", async () => {
    const deletion = {
      ...PASS,
      version: "d3l3t3",
      writer: "user" as const,
      operation: "delete",
      documents: [{ path: GATEWAY.path, status: "removed" as const, added: 0, removed: 3 }],
    };
    api.deleteFile.mockResolvedValue(undefined);
    renderKnowledge(`/knowledge/${UID}?file=${encodeURIComponent(GATEWAY.path)}`);
    fireEvent.click(
      await screen.findByRole("button", { name: `More actions for ${GATEWAY.path}` }),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete document…" }));
    // No dialog asks: the delete runs, the collection page shows, a toast offers Undo.
    await waitFor(() => expect(api.deleteFile).toHaveBeenCalledWith(GATEWAY.path));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(await screen.findByText(`Deleted ${GATEWAY.path.split("/").pop()}`)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId("where")).toHaveTextContent(new RegExp(`/knowledge/${UID}$`)),
    );
    expect(await screen.findByRole("heading", { name: NAME })).toBeInTheDocument();

    api.listChanges.mockResolvedValue({ changes: [deletion], next_cursor: null });
    api.restoreDeleted.mockResolvedValue(deletion);
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(api.restoreDeleted).toHaveBeenCalledWith("d3l3t3"));
  });
});

describe("a collection has no title", () => {
  acceptance("knowledge", "a collection carries no title", async () => {
    renderKnowledge(`/knowledge/${UID}`);
    // The heading and the tree name the collection by its folder.
    expect(await screen.findByRole("heading", { name: NAME })).toBeInTheDocument();
    expect(
      within(tree()).getByRole("button", { name: new RegExp(`^${NAME}`) }),
    ).toBeInTheDocument();
    expect(screen.getByText(COLLECTION.description)).toBeInTheDocument();
  });

  acceptance("knowledge", "edit a collection's description in place", async () => {
    api.describeCollection.mockResolvedValue({ ...COLLECTION, description: "Shops and owners." });
    renderKnowledge(`/knowledge/${UID}`);
    // No Edit / Save buttons: the text itself is the control.
    expect(await screen.findByText(COLLECTION.description)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit description" })).toBeNull();
    fireEvent.click(screen.getByText(COLLECTION.description));
    const field = screen.getByRole("textbox", { name: "What belongs in this collection" });
    expect(field).toHaveValue(COLLECTION.description);
    fireEvent.change(field, { target: { value: "  Shops and owners.  " } });
    fireEvent.blur(field);
    await waitFor(() =>
      expect(api.describeCollection).toHaveBeenCalledWith(UID, "Shops and owners."),
    );
    await waitFor(() => expect(screen.queryByRole("textbox")).toBeNull());
    expect(await screen.findByText("Description updated")).toBeInTheDocument();
  });

  test("an empty description cannot be saved", async () => {
    renderKnowledge(`/knowledge/${UID}`);
    fireEvent.click(await screen.findByText(COLLECTION.description));
    const field = screen.getByRole("textbox", { name: "What belongs in this collection" });
    fireEvent.change(field, { target: { value: "   " } });
    fireEvent.blur(field);
    await waitFor(() => expect(screen.queryByRole("textbox")).toBeNull());
    expect(api.describeCollection).not.toHaveBeenCalled();
  });
});

describe("the reader", () => {
  test("has no side rail: one properties line sits under the title", async () => {
    renderKnowledge(`/knowledge/${UID}?file=${encodeURIComponent(GATEWAY.path)}`);
    expect(await screen.findByRole("heading", { level: 1, name: GATEWAY.title })).toBeVisible();
    expect(screen.queryByRole("complementary")).toBeNull();
    expect(screen.queryByText("On this page")).toBeNull();
    expect(await screen.findByText(/^Created Sep 12 by/)).toBeInTheDocument();
  });
});
