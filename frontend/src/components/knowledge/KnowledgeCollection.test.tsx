// frontend/src/components/knowledge/KnowledgeCollection.test.tsx
//
// A collection's own page (boards 5.1.10, 5.1.11, 5.1.12, 5.1.14), mocked only
// at the network boundary: the folder name as the heading, the description
// edited in place (blur / ⌘Enter saves, Esc cancels, the toast offers Undo),
// the properties rows, the empty collection's one muted line, Rename… from the
// ⋯ menu (a dialog that closes only on success), and Delete collection… from
// the same menu — which asks first, then offers Undo in a toast.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { answerFromFixtures, renderKnowledge } from "@/test/knowledgeHarness";
import { COLLECTION, EDIT, NAME, OTHER, UID } from "./knowledgeTestData";
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
}));
vi.mock("@/lib/api/resources", () => ({ resourcesApi: { remove: vi.fn(), rename: vi.fn() } }));
vi.mock("@/lib/hooks/useDaemonEvents", () => ({ useDaemonEvents: () => undefined }));

const api = vi.mocked(await import("@/lib/api/knowledge"));
const { resourcesApi } = await import("@/lib/api/resources");

beforeEach(() => {
  answerFromFixtures();
});
afterEach(() => {
  vi.clearAllMocks();
});

const DESCRIPTION = { name: "What belongs in this collection" };

describe("the properties", () => {
  test("Documents and Folder — no inbox, no last-curated, no big numbers or danger zone", async () => {
    renderKnowledge(`/knowledge/${UID}`);
    const stats = await screen.findByTestId("knowledge-stats");
    expect(within(stats).getByText("Documents")).toBeInTheDocument();
    expect(within(stats).getByText("Folder")).toBeInTheDocument();
    expect(within(stats).getByText("~/.coffer/knowledge/shopee")).toBeInTheDocument();
    expect(within(stats).queryByText("Inbox")).toBeNull();
    expect(within(stats).queryByText("Last curated")).toBeNull();
    expect(screen.queryByRole("button", { name: "Edit description" })).toBeNull();
    expect(screen.queryByText("Danger zone")).toBeNull();
  });

  test("the folder path copies from its icon button", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    renderKnowledge(`/knowledge/${UID}`);
    fireEvent.click(await screen.findByRole("button", { name: "Copy path" }));
    expect(writeText).toHaveBeenCalledWith(COLLECTION.folder_path);
  });

  acceptance("knowledge", "a collection page shows its properties", async () => {
    renderKnowledge(`/knowledge/${UID}`);
    expect(await screen.findByRole("heading", { name: NAME })).toBeInTheDocument();
    expect(screen.getByText(COLLECTION.description)).toBeInTheDocument();
    const stats = screen.getByTestId("knowledge-stats");
    expect(within(stats).getByText("Documents")).toBeInTheDocument();
    expect(within(stats).getByText("Folder")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: `More actions for ${NAME}` }));
    expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual([
      "Reveal in Finder",
      "Copy path",
      "Rename…",
      "Delete collection…",
    ]);
  });
});

describe("a just created, empty collection", () => {
  test("is the same page with one muted line and a Reveal in Finder link", async () => {
    renderKnowledge(`/knowledge/${OTHER.uid}`);
    expect(await screen.findByRole("heading", { name: OTHER.name })).toBeInTheDocument();
    expect(
      screen.getByText(/No documents yet\. Upload one, or drop Markdown files into the folder\./),
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

      // The confirmation names the collection and its documents, and nothing is deleted yet.
      expect(within(dialog).getByText(`Delete ${NAME}?`)).toBeInTheDocument();
      expect(within(dialog).getByText(/2 documents go with it/)).toBeInTheDocument();
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
