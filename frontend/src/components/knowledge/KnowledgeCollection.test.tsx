// frontend/src/components/knowledge/KnowledgeCollection.test.tsx
//
// A collection's own page (boards 5.1.10, 5.1.11, 5.1.12, 5.1.14), mocked only
// at the network boundary: the folder name as the heading, the description
// edited in place (blur / ⌘Enter saves, Esc cancels, the toast offers Undo),
// the summary line and what Coffer does with the collection, its To do,
// Contents and Change log, Open in Obsidian when it is installed, the empty
// collection's one muted line, Rename… from the
// ⋯ menu (a dialog that closes only on success), and Delete collection… from
// the same menu — which asks first, then offers Undo in a toast.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";

import { answerFromFixtures, renderKnowledge } from "@/test/knowledgeHarness";
import {
  COLLECTION,
  EDIT,
  GATEWAY,
  NAME,
  OTHER,
  RELEASE,
  SESSION,
  UID,
  change,
  summary as summaryOf,
} from "./knowledgeTestData";
import { acceptance } from "@/test/acceptance";
import { ApiError } from "@/lib/api/errors";

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
vi.mock("@/lib/api/resources", () => ({ resourcesApi: { remove: vi.fn(), rename: vi.fn() } }));
vi.mock("@/lib/hooks/useDaemonEvents", () => ({ useDaemonEvents: () => undefined }));
vi.mock("@/lib/api/agentProviders", () => ({
  agentProvidersApi: {
    list: vi.fn().mockResolvedValue({
      agents: [{ agent_key: "claude_code", display_name: "Claude Code", available: true }],
    }),
  },
}));
vi.mock("@/lib/api/fs", () => ({
  fsApi: {
    listTerminals: vi.fn().mockResolvedValue([]),
    openTerminal: vi.fn(),
    reveal: vi.fn().mockResolvedValue(undefined),
    open: vi.fn().mockResolvedValue(undefined),
    listEditors: vi.fn().mockResolvedValue([]),
  },
}));

const api = vi.mocked(await import("@/lib/api/knowledge"));
const { resourcesApi } = await import("@/lib/api/resources");

beforeEach(() => {
  answerFromFixtures();
});
afterEach(() => {
  vi.clearAllMocks();
});

const DESCRIPTION = { name: "What belongs in this collection" };

describe("the summary", () => {
  test("one line of counts, folder and update time, and what Coffer does with it — no table, no danger zone", async () => {
    renderKnowledge(`/knowledge/${UID}`);
    const summary = await screen.findByTestId("knowledge-summary");
    expect(summary).toHaveTextContent("2 pages · 1 sources (1 waiting)");
    expect(within(summary).getByText("~/.coffer/knowledge/shopee")).toBeInTheDocument();
    expect(summary).toHaveTextContent(/updated /);
    expect(summary).toHaveTextContent(
      "Kept in Coffer: synced to your other Macs, every change kept in its history, tidied by your agent.",
    );
    expect(screen.queryByTestId("knowledge-stats")).toBeNull();
    expect(screen.queryByText("Last curated")).toBeNull();
    expect(screen.queryByRole("button", { name: "Edit description" })).toBeNull();
    expect(screen.queryByText("Danger zone")).toBeNull();
  });

  test("the folder path copies from its icon button", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    renderKnowledge(`/knowledge/${UID}`);
    const summary = await screen.findByTestId("knowledge-summary");
    fireEvent.click(within(summary).getByRole("button", { name: "Copy path" }));
    expect(writeText).toHaveBeenCalledWith(COLLECTION.folder_path);
  });

  test("while an agent has a tidy open, the page says so", async () => {
    api.listCollections.mockResolvedValue({
      collections: [{ ...COLLECTION, tidy_running: true }, OTHER],
    });
    renderKnowledge(`/knowledge/${UID}`);
    expect(
      await screen.findByText(
        "An agent is tidying this collection. Its edits show here as one change when it finishes.",
      ),
    ).toBeInTheDocument();
  });

  acceptance(
    "knowledge",
    "the collection page shows a summary line, its to-do list, its contents and its change log",
    async () => {
      api.getCheck.mockResolvedValue({
        collection: COLLECTION,
        findings: [
          { kind: "unsourced_page", path: GATEWAY.path, target: null, others: [] },
          { kind: "waiting_source", path: RELEASE.path, target: null, others: [] },
          { kind: "dead_link", path: SESSION.path, target: "nowhere", others: [] },
        ],
      });
      api.getCollectionFiles.mockResolvedValue({
        files: [GATEWAY, { ...SESSION, page_type: "how-to" }, RELEASE].map(summaryOf),
      });
      api.listChanges.mockResolvedValue({
        changes: [
          change({
            version: "c1",
            writer: "agent",
            agent: "claude-code",
            operation: "edit",
            documents: [{ path: GATEWAY.path, status: "modified", added: 3, removed: 1 }],
          }),
        ],
        next_cursor: null,
      });
      renderKnowledge(`/knowledge/${UID}`);
      expect(await screen.findByRole("heading", { name: NAME })).toBeInTheDocument();
      expect(screen.getByText(COLLECTION.description)).toBeInTheDocument();
      const summary = screen.getByTestId("knowledge-summary");
      expect(summary).toHaveTextContent("2 pages · 1 sources (1 waiting)");
      expect(within(summary).getByRole("button", { name: "Copy path" })).toBeInTheDocument();
      expect(summary).toHaveTextContent(/Kept in Coffer/);

      // To do: the dead link before the waiting source, each page by title;
      // the page without sources folded into one collapsed row.
      const todo = screen.getByRole("region", { name: "To do" });
      const dead = await within(todo).findByText("Dead links");
      const waiting = within(todo).getByText("Waiting sources");
      expect(dead.compareDocumentPosition(waiting) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      expect(await within(todo).findByRole("link", { name: "Session ownership" })).toHaveAttribute(
        "title",
        "pages/account/session.md",
      );
      expect(within(todo).getByRole("link", { name: "Release notes" })).toBeInTheDocument();
      const folded = within(todo).getByRole("button", { name: "Pages without sources 1" });
      expect(folded).toHaveAttribute("aria-expanded", "false");
      expect(within(todo).queryByRole("link", { name: "Account Gateway" })).toBeNull();
      fireEvent.click(folded);
      expect(within(todo).getByRole("link", { name: "Account Gateway" })).toBeInTheDocument();

      // Contents: a card per page type, then Sources.
      const contents = screen.getByRole("region", { name: "Contents" });
      const concepts = within(contents).getByRole("region", { name: "Concepts" });
      expect(within(concepts).getByRole("link", { name: "Account Gateway" })).toBeInTheDocument();
      const howTos = within(contents).getByRole("region", { name: "How-tos" });
      expect(within(howTos).getByRole("link", { name: "Session ownership" })).toBeInTheDocument();
      const sources = within(contents).getByRole("region", { name: "Sources" });
      expect(within(sources).getByText("Waiting")).toBeInTheDocument();

      // A Change log.
      const log = screen.getByRole("region", { name: "Change log" });
      expect(await within(log).findByText("Edited")).toBeInTheDocument();

      // Tidy, and no Check with agent; its ⋯ menu.
      expect(await screen.findByRole("button", { name: "Tidy" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Check with agent" })).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: `More actions for ${NAME}` }));
      expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual([
        "Reveal in Finder",
        "Copy path",
        "Rename…",
        "Delete collection…",
      ]);
    },
  );
});

describe("Open in Obsidian", () => {
  acceptance("knowledge", "Open in Obsidian shows only when Obsidian is installed", async () => {
    const { fsApi } = await import("@/lib/api/fs");
    const listEditors = vi.mocked(fsApi.listEditors);
    const open = vi.mocked(fsApi.open);
    listEditors.mockResolvedValue([{ label: "Obsidian", value: "Obsidian" }]);
    renderKnowledge(`/knowledge/${UID}`);
    await waitFor(() => expect(listEditors).toHaveBeenCalled());
    fireEvent.click(await screen.findByRole("button", { name: `More actions for ${NAME}` }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Open in Obsidian" }));
    expect(open).toHaveBeenCalledWith(COLLECTION.folder_path, "Obsidian");

    // A page's ⋯ menu offers it too, with the page's path.
    cleanup();
    renderKnowledge(`/knowledge/${UID}?file=${encodeURIComponent(GATEWAY.path)}`);
    fireEvent.click(
      await screen.findByRole("button", { name: `More actions for ${GATEWAY.path}` }),
    );
    fireEvent.click(await screen.findByRole("menuitem", { name: "Open in Obsidian" }));
    expect(open).toHaveBeenLastCalledWith(GATEWAY.file_path, "Obsidian");

    // Without Obsidian neither menu names it.
    cleanup();
    listEditors.mockResolvedValue([{ label: "Cursor", value: "Cursor" }]);
    renderKnowledge(`/knowledge/${UID}?file=${encodeURIComponent(GATEWAY.path)}`);
    fireEvent.click(
      await screen.findByRole("button", { name: `More actions for ${GATEWAY.path}` }),
    );
    expect(await screen.findByRole("menuitem", { name: "Reveal in Finder" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Open in Obsidian" })).toBeNull();
    cleanup();
    renderKnowledge(`/knowledge/${UID}`);
    fireEvent.click(await screen.findByRole("button", { name: `More actions for ${NAME}` }));
    expect(await screen.findByRole("menuitem", { name: "Copy path" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Open in Obsidian" })).toBeNull();
  });
});

describe("a just created, empty collection", () => {
  test("is the same page with one muted line and a Reveal in Finder link", async () => {
    renderKnowledge(`/knowledge/${OTHER.uid}`);
    expect(await screen.findByRole("heading", { name: OTHER.name })).toBeInTheDocument();
    expect(
      screen.getByText(
        /No pages or sources yet\. Upload a document, or drop Markdown files into the folder\./,
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reveal in Finder" })).toBeInTheDocument();
    // No Add a document: people write in their own editor, agents write files.
    expect(screen.queryByRole("button", { name: /Add a document/ })).toBeNull();
  });
});

describe("the description", () => {
  acceptance("knowledge", "edit a collection's description in place", async () => {
    api.describeCollection.mockResolvedValue({ ...COLLECTION, description: "Shops and owners." });
    renderKnowledge(`/knowledge/${UID}`);
    fireEvent.click(await screen.findByText(COLLECTION.description));
    const field = screen.getByRole("textbox", DESCRIPTION);
    expect(field).toHaveValue(COLLECTION.description);
    fireEvent.change(field, { target: { value: "  Shops and owners.  " } });
    fireEvent.blur(field);
    await waitFor(() =>
      expect(api.describeCollection).toHaveBeenCalledWith(UID, "Shops and owners."),
    );
    await waitFor(() => expect(screen.queryByRole("textbox")).toBeNull());
    expect(await screen.findByText("Description updated")).toBeInTheDocument();

    // Undo puts the previous description back through the same mutation.
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() =>
      expect(api.describeCollection).toHaveBeenLastCalledWith(UID, COLLECTION.description),
    );
  });

  test("⌘Enter saves", async () => {
    api.describeCollection.mockResolvedValue({ ...COLLECTION, description: "New." });
    renderKnowledge(`/knowledge/${UID}`);
    fireEvent.click(await screen.findByText(COLLECTION.description));
    const field = screen.getByRole("textbox", DESCRIPTION);
    fireEvent.change(field, { target: { value: "New." } });
    fireEvent.keyDown(field, { key: "Enter", metaKey: true });
    await waitFor(() => expect(api.describeCollection).toHaveBeenCalledWith(UID, "New."));
  });

  test("Esc cancels without saving, even though the field then loses focus", async () => {
    renderKnowledge(`/knowledge/${UID}`);
    fireEvent.click(await screen.findByText(COLLECTION.description));
    const field = screen.getByRole("textbox", DESCRIPTION);
    fireEvent.change(field, { target: { value: "Something else" } });
    fireEvent.keyDown(field, { key: "Escape" });
    fireEvent.blur(field);
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.getByText(COLLECTION.description)).toBeInTheDocument();
    expect(api.describeCollection).not.toHaveBeenCalled();
  });

  test("an empty description cannot be saved: leaving it blank keeps the old one", async () => {
    renderKnowledge(`/knowledge/${UID}`);
    fireEvent.click(await screen.findByText(COLLECTION.description));
    const field = screen.getByRole("textbox", DESCRIPTION);
    fireEvent.change(field, { target: { value: "   " } });
    fireEvent.blur(field);
    await waitFor(() => expect(screen.queryByRole("textbox")).toBeNull());
    expect(api.describeCollection).not.toHaveBeenCalled();
    expect(screen.getByText(COLLECTION.description)).toBeInTheDocument();
  });
});

describe("Delete collection…", () => {
  const REMOVAL = {
    ...EDIT,
    version: "r3m0ve",
    operation: "remove",
    collections: [NAME],
    documents: [],
  };

  const askToDelete = async () => {
    fireEvent.click(await screen.findByRole("button", { name: `More actions for ${NAME}` }));
    expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual([
      "Reveal in Finder",
      "Copy path",
      "Rename…",
      "Delete collection…",
    ]);
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete collection…" }));
    return screen.findByRole("dialog");
  };

  acceptance(
    "knowledge",
    "delete a collection after asking and undo it from the toast",
    async () => {
      vi.mocked(resourcesApi.remove).mockResolvedValue(undefined);
      renderKnowledge(`/knowledge/${UID}`);
      const dialog = await askToDelete();

      // The confirmation names the collection and its files, and nothing is deleted yet.
      expect(within(dialog).getByText(`Delete ${NAME}?`)).toBeInTheDocument();
      expect(within(dialog).getByText(/3 files go with it/)).toBeInTheDocument();
      expect(within(dialog).queryByRole("textbox")).toBeNull();
      expect(resourcesApi.remove).not.toHaveBeenCalled();

      fireEvent.click(within(dialog).getByRole("button", { name: "Delete collection" }));
      await waitFor(() => expect(resourcesApi.remove).toHaveBeenCalledWith(UID));
      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
      expect(await screen.findByText(`Deleted ${NAME}`)).toBeInTheDocument();
      // The page goes to Knowledge.
      await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent(/^\/knowledge$/));

      // Undo restores it from the vault's history.
      api.listChanges.mockResolvedValue({ changes: [REMOVAL], next_cursor: null });
      api.restoreDeleted.mockResolvedValue(REMOVAL);
      fireEvent.click(screen.getByRole("button", { name: "Undo" }));
      await waitFor(() => expect(api.restoreDeleted).toHaveBeenCalledWith("r3m0ve"));
    },
  );

  test("Cancel deletes nothing", async () => {
    renderKnowledge(`/knowledge/${UID}`);
    const dialog = await askToDelete();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(resourcesApi.remove).not.toHaveBeenCalled();
    expect(screen.getByTestId("where")).toHaveTextContent(`/knowledge/${UID}`);
  });

  test("a refused delete stays in the dialog, which stays open", async () => {
    vi.mocked(resourcesApi.remove).mockRejectedValue(new ApiError("INTERNAL_ERROR", "boom"));
    renderKnowledge(`/knowledge/${UID}`);
    const dialog = await askToDelete();
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete collection" }));
    expect(await within(dialog).findByText(`Couldn’t delete ${NAME}`)).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.queryByText(`Deleted ${NAME}`)).toBeNull();
  });

  test("an Undo the vault refuses is an error toast", async () => {
    vi.mocked(resourcesApi.remove).mockResolvedValue(undefined);
    renderKnowledge(`/knowledge/${UID}`);
    const dialog = await askToDelete();
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete collection" }));
    await screen.findByText(`Deleted ${NAME}`);
    api.listChanges.mockResolvedValue({ changes: [REMOVAL], next_cursor: null });
    api.restoreDeleted.mockRejectedValue(new Error("name taken"));
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(await screen.findByText(`Couldn’t restore ${NAME}`)).toBeInTheDocument();
  });
});

describe("Rename…", () => {
  const openRename = async () => {
    fireEvent.click(await screen.findByRole("button", { name: `More actions for ${NAME}` }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Rename…" }));
    return screen.findByRole("dialog");
  };

  acceptance("knowledge", "rename a collection from its menu", async () => {
    vi.mocked(resourcesApi.rename).mockResolvedValue({} as never);
    renderKnowledge(`/knowledge/${UID}`);
    const dialog = await openRename();
    const field = within(dialog).getByRole("textbox", { name: /Name/ });
    expect(field).toHaveValue(NAME);
    // Unchanged, the name cannot be submitted.
    expect(within(dialog).getByRole("button", { name: "Rename" })).toBeDisabled();
    fireEvent.change(field, { target: { value: "  shops  " } });
    expect(
      within(dialog).getByText("Folder: ~/.coffer/vault/knowledge/shops/"),
    ).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Rename" }));

    await waitFor(() => expect(resourcesApi.rename).toHaveBeenCalledWith(UID, "shops"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(await screen.findByText("Renamed to shops")).toBeInTheDocument();
    // The address carries the uid, so the page stays where it was.
    expect(screen.getByTestId("where")).toHaveTextContent(`/knowledge/${UID}`);
    // The collection list is read again.
    await waitFor(() => expect(api.listCollections.mock.calls.length).toBeGreaterThan(1));
  });

  test("a refused name is said under the field and the dialog stays open", async () => {
    vi.mocked(resourcesApi.rename).mockRejectedValue(
      new ApiError("RESOURCE_ALREADY_EXISTS", "knowledge 'shops' already exists"),
    );
    renderKnowledge(`/knowledge/${UID}`);
    const dialog = await openRename();
    fireEvent.change(within(dialog).getByRole("textbox", { name: /Name/ }), {
      target: { value: "shops" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Rename" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "A resource with that name already exists",
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.queryByText("Renamed to shops")).toBeNull();
  });
});
