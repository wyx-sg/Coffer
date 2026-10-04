// frontend/src/pages/KnowledgePage.test.tsx
//
// The Knowledge page's tree, reader and editor (spec knowledge "Present a
// collection as one tree in the web UI"), mocked only at the network boundary:
// one tree of collections with each collection's Inbox node and documents;
// the document pane with Edit, open-in-editor, reveal and delete (at once,
// with an Undo toast); an inbox item read-only; the body-only editor saving
// with the fingerprint it read and refusing a stale save with Compare / Copy my
// text / Reload; and the page with Coffer's model not set.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { answerFromFixtures, renderKnowledge } from "@/test/knowledgeHarness";
import {
  COLLECTION,
  GATEWAY,
  ITEM,
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
  curateCollection: vi.fn(),
  uploadFile: vi.fn(),
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
    expect(screen.queryByRole("button", { name: "Add a document" })).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("searchbox")).toBeNull();
    // Both documents — the root one and the one in a folder, opened on the way —
    // each named by its file, as it is on disk.
    expect(await within(nav).findByRole("button", { name: "gateway.md" })).toBeInTheDocument();
    fireEvent.click(within(nav).getByRole("button", { name: "account" }));
    expect(await within(nav).findByRole("button", { name: "session.md" })).toBeInTheDocument();
    // The inbox is its own node, holding the waiting item.
    expect(within(nav).getByRole("button", { name: /^Inbox/ })).toHaveTextContent("1");

    // A document offers Edit, open-in-editor, reveal and delete.
    fireEvent.click(within(nav).getByRole("button", { name: "gateway.md" }));
    expect(await screen.findByRole("button", { name: "Edit" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: `More actions for ${GATEWAY.path}` }));
    expect(screen.getByRole("menuitem", { name: "Open in editor" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Reveal in Finder" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Delete document…" })).toBeInTheDocument();
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });

    // The inbox item offers neither Edit nor delete.
    fireEvent.click(within(nav).getByRole("button", { name: /^Inbox/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Login retry/ }));
    expect(await screen.findByText("Retries back off after three failures.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByRole("button", { name: /More actions/ })).toBeNull();
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

  test("the Inbox list closes on its chevron and the collection stays open", async () => {
    renderKnowledge(`/knowledge/${UID}/inbox`);
    const item = await within(tree()).findByRole("button", { name: ITEM.path.split("/").pop() });
    expect(item).toBeInTheDocument();
    fireEvent.click(within(tree()).getByRole("button", { name: "Collapse Inbox" }));
    expect(within(tree()).queryByRole("button", { name: ITEM.path.split("/").pop() })).toBeNull();
    expect(within(tree()).getByRole("button", { name: "gateway.md" })).toBeInTheDocument();
    fireEvent.click(within(tree()).getByRole("button", { name: "Expand Inbox" }));
    expect(
      await within(tree()).findByRole("button", { name: ITEM.path.split("/").pop() }),
    ).toBeInTheDocument();
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
      expect(within(tree()).getByRole("button", { name: /^Inbox/ })).toHaveTextContent("1");
      expect(await screen.findByTestId("knowledge-automatic")).toBeInTheDocument();
      // The collection page's properties: documents, what waits, when it last ran.
      expect(within(stats).getByText("1 waiting")).toBeInTheDocument();
      expect(await within(stats).findByText("2 hours ago")).toBeInTheDocument();
      expect(within(stats).queryByRole("link", { name: "1" })).toBeNull();
      // Curate now lives in the Inbox view, not in the header or on documents.
      expect(screen.queryByRole("button", { name: "Curate now" })).toBeNull();
      fireEvent.click(within(stats).getByRole("button", { name: "Open Inbox" }));
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
    const link = await screen.findByRole("button", { name: "Curation needs Coffer’s engine" });
    expect(
      screen.getByText("Documents you and your agents write together. Every agent can read them."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload" })).toBeInTheDocument();
    expect(within(tree()).queryByRole("button", { name: /^Inbox/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Curate now" })).toBeNull();
    expect(screen.queryByTestId("knowledge-automatic")).toBeNull();
    expect(screen.getByTestId("knowledge-stats")).not.toHaveTextContent("waiting");
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

  acceptance("knowledge", "a stale save offers compare, copy and reload", async () => {
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

    api.listChanges.mockResolvedValue({ changes: [deletion], waiting: [], next_cursor: null });
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

test("an inbox item carries who wrote it", async () => {
  renderKnowledge(`/knowledge/${UID}/inbox?file=${encodeURIComponent(ITEM.path)}`);
  expect(await screen.findByText(/Written by An agent/)).toBeInTheDocument();
});
