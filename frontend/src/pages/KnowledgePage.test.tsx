// frontend/src/pages/KnowledgePage.test.tsx
//
// The Knowledge page's tree, reader and editor (spec knowledge "Present a
// collection as one tree in the web UI"), mocked only at the network boundary:
// one tree of collections with each collection's Inbox node and documents;
// the document pane with Edit, open-in-editor, reveal and delete; an inbox
// item read-only; the body-only editor saving with the fingerprint it read and
// refusing a stale save with Reload / Compare / Copy my text; Add a document
// submitting an item; and the page with Coffer's model not set.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { answerFromFixtures, renderKnowledge } from "@/components/knowledge/knowledgeTestHarness";
import {
  COLLECTION,
  GATEWAY,
  ITEM,
  NAME,
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
const upkeep = vi.mocked(await import("@/lib/api/upkeep"));
const { internalEngineApi } = await import("@/lib/api/internalEngine");

/** Coffer's engine config with a curate schedule, so the header's Automatic
 *  control has a pass to show whenever the model is set. */
function withCurateSchedule(model: string | null) {
  vi.mocked(internalEngineApi.get).mockResolvedValue({
    model,
    curate_owner_machine_id: null,
    default_model_timeout_s: 60,
    model_timeout_s: null,
    transcribe_model: null,
    updated_at: null,
    upkeep: {
      curate: {
        enabled: true,
        interval_s: null,
        default_interval_s: 3600,
        last_pass_at: null,
        next_pass_at: null,
      },
    },
  });
}

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
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("searchbox")).toBeNull();
    // Both documents — the root one and the one in a folder, opened on the way —
    // each named by its file, as it is on disk.
    expect(await within(nav).findByRole("button", { name: "gateway.md" })).toBeInTheDocument();
    fireEvent.click(within(nav).getByRole("button", { name: "account" }));
    expect(await within(nav).findByRole("button", { name: "session.md" })).toBeInTheDocument();
    // The inbox is its own node, holding the waiting item.
    expect(within(nav).getByRole("button", { name: /Inbox/ })).toHaveTextContent("1");

    // A document offers Edit, open-in-editor, reveal and delete.
    fireEvent.click(within(nav).getByRole("button", { name: "gateway.md" }));
    expect(await screen.findByRole("button", { name: "Edit" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: `More actions for ${GATEWAY.path}` }));
    expect(screen.getByRole("menuitem", { name: "Open in editor" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Reveal in Finder" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Delete document…" })).toBeInTheDocument();
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });

    // The inbox item offers neither Edit nor delete.
    fireEvent.click(within(nav).getByRole("button", { name: /Inbox/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Login retry/ }));
    expect(await screen.findByText("Retries back off after three failures.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByRole("button", { name: /More actions/ })).toBeNull();
  });

  test("a deep link opens the folders on the way to its document", async () => {
    renderKnowledge(`/knowledge/${UID}?file=${encodeURIComponent(SESSION.path)}`);
    const row = await within(
      await screen.findByRole("navigation", { name: "Collections and documents" }),
    ).findByRole("button", { name: "session.md" });
    expect(row).toHaveAttribute("aria-current", "page");
    expect(await screen.findByText("Login state is owned by account.session.")).toBeInTheDocument();
  });

  acceptance(
    "knowledge",
    "the inbox node counts waiting items and holds the only trigger",
    async () => {
      withCurateSchedule("claude-haiku");
      renderKnowledge(`/knowledge/${UID}`);
      const stats = await screen.findByTestId("knowledge-stats");
      expect(within(tree()).getByRole("button", { name: /Inbox/ })).toHaveTextContent("1");
      expect(await screen.findByTestId("knowledge-automatic")).toBeInTheDocument();
      expect(stats).toHaveTextContent("Documents2");
      expect(stats).toHaveTextContent("Waiting1");
      await waitFor(() => expect(stats).toHaveTextContent(/Curated2 hours ago/));
      // Curate now lives in the Inbox view, not in the header or on documents.
      expect(screen.queryByRole("button", { name: "Curate now" })).toBeNull();
      fireEvent.click(within(stats).getByRole("link", { name: "1" }));
      expect(screen.getByTestId("where")).toHaveTextContent(`/knowledge/${UID}/inbox`);
      expect(await screen.findByRole("button", { name: "Curate now" })).toBeInTheDocument();
    },
  );

  test("a running curation reads its progress, from the daemon's run list by uid", async () => {
    upkeep.listUpkeepRuns.mockResolvedValue({
      runs: [
        { kind: "knowledge", name: UID, started_at: new Date().toISOString(), done: 1, total: 3 },
      ],
    });
    renderKnowledge(`/knowledge/${UID}/inbox`);
    expect(await screen.findByRole("button", { name: "Curating · 2 of 3" })).toBeDisabled();
    // The collection's own status line says the same, in place of "Curated".
    fireEvent.click(within(tree()).getByRole("button", { name: /^shopee/ }));
    await waitFor(() =>
      expect(screen.getByTestId("knowledge-stats")).toHaveTextContent("Curating · 2 of 3"),
    );
  });

  test("Curate now curates this collection by uid", async () => {
    api.curateCollection.mockResolvedValue({
      collection: NAME,
      status: "ok",
      total: 1,
      passes: [],
    });
    renderKnowledge(`/knowledge/${UID}/inbox`);
    fireEvent.click(await screen.findByRole("button", { name: "Curate now" }));
    await waitFor(() => expect(api.curateCollection).toHaveBeenCalledWith(UID, null));
  });
});

describe("with Coffer's model not set", () => {
  acceptance("knowledge", "no model shows no curation controls", async () => {
    answerFromFixtures({ modelSet: false });
    withCurateSchedule(null);
    renderKnowledge(`/knowledge/${UID}`);
    const link = await screen.findByRole("button", { name: "Settings › General" });
    expect(
      screen.getByText(/Set Coffer's model to curate new items into your documents/),
    ).toBeInTheDocument();
    expect(within(tree()).queryByRole("button", { name: /Inbox/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Curate now" })).toBeNull();
    expect(screen.queryByTestId("knowledge-automatic")).toBeNull();
    expect(screen.getByTestId("knowledge-stats")).not.toHaveTextContent("Waiting");
    fireEvent.click(link);
    expect(screen.getByTestId("where")).toHaveTextContent("/settings/general");
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

  acceptance("knowledge", "a stale save offers reload and compare", async () => {
    api.saveFile.mockRejectedValue(
      new ApiError("KNOWLEDGE_FILE_CONFLICT", "changed on disk", {
        saved: false,
        current_body: "# Account Gateway\n\nCuration added a line.",
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
    expect(alert).toHaveTextContent("Your text was not saved");
    // No second save over it.
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(within(alert).getByRole("button", { name: "Reload" })).toBeInTheDocument();
    expect(within(alert).getByRole("button", { name: "Copy my text" })).toBeInTheDocument();
    fireEvent.click(within(alert).getByRole("button", { name: "Compare" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Curation added a line.")).toBeInTheDocument();
    expect(within(dialog).getByText("My version.")).toBeInTheDocument();
  });
});

describe("Add a document", () => {
  acceptance("knowledge", "add a document submits an item", async () => {
    api.submitMaterial.mockResolvedValue({
      status: "pending",
      collection: NAME,
      title: "Retry policy",
      path: null,
    });
    renderKnowledge(`/knowledge/${UID}`);
    fireEvent.click(await screen.findByRole("button", { name: "Add a document" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/^Title/), {
      target: { value: "Retry policy" },
    });
    fireEvent.change(within(dialog).getByLabelText(/^Document/), {
      target: { value: "Back off after three failures. Then give up." },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add to Inbox" }));
    await waitFor(() =>
      expect(api.submitMaterial).toHaveBeenCalledWith({
        collection: COLLECTION.name,
        title: "Retry policy",
        description: "Back off after three failures.",
        body: "Back off after three failures. Then give up.",
      }),
    );
    // Nothing is written as a document from here: the item goes to the inbox.
    expect(api.saveFile).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});

describe("delete a document", () => {
  test("names the exact file before it runs and leaves the document afterwards", async () => {
    api.deleteFile.mockResolvedValue(undefined);
    renderKnowledge(`/knowledge/${UID}?file=${encodeURIComponent(GATEWAY.path)}`);
    fireEvent.click(
      await screen.findByRole("button", { name: `More actions for ${GATEWAY.path}` }),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete document…" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(GATEWAY.file_path)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete document" }));
    await waitFor(() => expect(api.deleteFile).toHaveBeenCalledWith(GATEWAY.path));
    await waitFor(() =>
      expect(screen.getByTestId("where")).toHaveTextContent(new RegExp(`/knowledge/${UID}$`)),
    );
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
    fireEvent.click(await screen.findByRole("button", { name: "Edit description" }));
    const field = screen.getByRole("textbox", { name: "What belongs in this collection" });
    expect(field).toHaveValue(COLLECTION.description);
    fireEvent.change(field, { target: { value: "  Shops and owners.  " } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(api.describeCollection).toHaveBeenCalledWith(UID, "Shops and owners."),
    );
    await waitFor(() => expect(screen.queryByRole("textbox")).toBeNull());
  });

  test("an empty description cannot be saved", async () => {
    renderKnowledge(`/knowledge/${UID}`);
    fireEvent.click(await screen.findByRole("button", { name: "Edit description" }));
    fireEvent.change(screen.getByRole("textbox", { name: "What belongs in this collection" }), {
      target: { value: "   " },
    });
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });
});

describe("the reader", () => {
  test("carries the document's outline and properties beside it", async () => {
    renderKnowledge(`/knowledge/${UID}?file=${encodeURIComponent(GATEWAY.path)}`);
    const rail = await screen.findByRole("complementary", { name: "About this document" });
    expect(within(rail).getByText("On this page")).toBeInTheDocument();
    expect(within(rail).getByRole("button", { name: "Account Gateway" })).toBeInTheDocument();
    expect(within(rail).getByText("Properties")).toBeInTheDocument();
    expect(within(rail).getByRole("button", { name: "Delete document…" })).toBeInTheDocument();
  });

  test("after a delete the pane says no document is open and where to restore it", async () => {
    api.deleteFile.mockResolvedValue(undefined);
    renderKnowledge(`/knowledge/${UID}?file=${encodeURIComponent(GATEWAY.path)}`);
    fireEvent.click(await screen.findByRole("button", { name: "Delete document…" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete document" }));
    expect(await screen.findByText("No document open")).toBeInTheDocument();
    expect(
      screen.getByText(/Recent changes lists the delete and can restore it/),
    ).toBeInTheDocument();
  });
});

test("an inbox item carries who wrote it", async () => {
  renderKnowledge(`/knowledge/${UID}/inbox?file=${encodeURIComponent(ITEM.path)}`);
  expect(await screen.findByText(/Written by An agent/)).toBeInTheDocument();
});
