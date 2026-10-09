// frontend/src/pages/KnowledgePage.test.tsx
//
// The Knowledge page's tree and read-only file pane (spec knowledge "Show a
// collection as one tree of read-only documents in the web UI"), mocked only at
// the network boundary: one tree of collections with their pages and sources,
// Pages and Sources first and a waiting source marked; the file pane with no
// tabs — History, Preview / Source, Open in editor, reveal and delete (at
// once, with an Undo toast). A file is never edited here.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { answerFromFixtures, renderKnowledge } from "@/test/knowledgeHarness";
import { COLLECTION, GATEWAY, NAME, SESSION, UID } from "@/components/knowledge/knowledgeTestData";
import { acceptance } from "@/test/acceptance";

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
}));
vi.mock("@/lib/api/fs", () => ({
  fsApi: {
    open: vi.fn().mockResolvedValue(undefined),
    reveal: vi.fn().mockResolvedValue(undefined),
    listEditors: vi.fn().mockResolvedValue([]),
  },
}));
vi.mock("@/lib/hooks/useDaemonEvents", () => ({ useDaemonEvents: () => undefined }));

const api = vi.mocked(await import("@/lib/api/knowledge"));
const { fsApi } = await import("@/lib/api/fs");

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
    // The collection's root shows Pages and Sources first, labelled.
    await within(nav).findByRole("button", { name: "Pages" });
    const folders = within(nav)
      .getAllByRole("button", { expanded: false })
      .map((b) => b.textContent)
      .filter((name) => name === "Pages" || name === "Sources");
    expect(folders).toEqual(["Pages", "Sources"]);
    // Both pages — one at the folder's root, one in a folder — each named by
    // its file, as it is on disk; and the source with its Waiting mark.
    fireEvent.click(within(nav).getByRole("button", { name: "Pages" }));
    expect(await within(nav).findByRole("button", { name: "gateway.md" })).toBeInTheDocument();
    fireEvent.click(within(nav).getByRole("button", { name: "account" }));
    expect(await within(nav).findByRole("button", { name: "session.md" })).toBeInTheDocument();
    fireEvent.click(within(nav).getByRole("button", { name: "Sources" }));
    const source = await within(nav).findByRole("button", { name: /^release-notes\.md/ });
    expect(source).toHaveTextContent("Waiting");
    expect(within(nav).getByRole("button", { name: "gateway.md" })).not.toHaveTextContent(
      "Waiting",
    );
    // No Inbox node and no hidden entry.
    expect(within(nav).queryByRole("button", { name: /^Inbox/ })).toBeNull();
    expect(within(nav).queryByText(/^\./)).toBeNull();

    // The page's pane carries no tabs, offers History, Preview and Source and
    // Open in editor, and Reveal in Finder and Delete in its ⋯ menu.
    fireEvent.click(within(nav).getByRole("button", { name: "gateway.md" }));
    expect(await screen.findByRole("button", { name: "Open in editor" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Document views" })).toBeNull();
    expect(screen.getByRole("button", { name: "History" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Source" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: `More actions for ${GATEWAY.path}` }));
    expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual([
      "Reveal in Finder",
      "Delete",
    ]);
  });

  test("a collection opened from the list stays open when a document in it is opened", async () => {
    renderKnowledge("/knowledge");
    fireEvent.click(await within(tree()).findByRole("button", { name: `Expand ${NAME}` }));
    fireEvent.click(await within(tree()).findByRole("button", { name: "Pages" }));
    fireEvent.click(await within(tree()).findByRole("button", { name: "gateway.md" }));
    expect(await screen.findByRole("button", { name: "Open in editor" })).toBeInTheDocument();
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
    expect(within(tree()).queryByRole("button", { name: "Pages" })).toBeNull();
    // Leave for the bare address, then come back in through a document address.
    fireEvent.click(within(tree()).getByRole("button", { name: `Expand ${NAME}` }));
    fireEvent.click(await within(tree()).findByRole("button", { name: "Pages" }));
    fireEvent.click(await within(tree()).findByRole("button", { name: "gateway.md" }));
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

describe("a document opens in the person's editor", () => {
  acceptance("knowledge", "a document opens in the person's editor", async () => {
    renderKnowledge(`/knowledge/${UID}?file=${encodeURIComponent(GATEWAY.path)}`);
    fireEvent.click(await screen.findByRole("button", { name: "Open in editor" }));
    await waitFor(() => expect(fsApi.open).toHaveBeenCalledWith(GATEWAY.file_path, undefined));

    fireEvent.click(screen.getByRole("button", { name: `More actions for ${GATEWAY.path}` }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Reveal in Finder" }));
    await waitFor(() => expect(fsApi.reveal).toHaveBeenCalledWith(GATEWAY.file_path));

    // The pane is read-only: Preview and Source, its line from the frontmatter, no Edit.
    expect(screen.getByRole("button", { name: "Preview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Source" })).toBeInTheDocument();
    expect(screen.getByText(/^Created Sep 12 by/)).toBeInTheDocument();
    expect(screen.getByTestId("page-type")).toHaveTextContent(GATEWAY.page_type);
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
  });
});

describe("delete a document", () => {
  acceptance("knowledge", "delete a document at once and undo it", async () => {
    const deletion = {
      version: "d3l3t3",
      time: new Date().toISOString(),
      writer: "user" as const,
      operation: "delete",
      summary: "Delete",
      actor: "user",
      agent: null,
      collections: [NAME],
      item: null,
      status: null,
      restored_from: null,
      undoes: null,
      documents: [{ path: GATEWAY.path, status: "removed" as const, added: 0, removed: 3 }],
    };
    api.deleteFile.mockResolvedValue(undefined);
    renderKnowledge(`/knowledge/${UID}?file=${encodeURIComponent(GATEWAY.path)}`);
    fireEvent.click(
      await screen.findByRole("button", { name: `More actions for ${GATEWAY.path}` }),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete" }));
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
