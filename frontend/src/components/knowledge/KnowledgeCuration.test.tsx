// frontend/src/components/knowledge/KnowledgeCuration.test.tsx
//
// A collection's Inbox and the curation pass pages (boards 5.1.15, 5.1.16,
// 5.1.18, 5.1.19, 5.1.20), mocked only at the network boundary: the Inbox list
// (a title, one note, rows that open whole), an inbox item read-only with its
// one meta line, a pass's title and meta, Undo this pass asking first, and a
// refused undo naming the document changed since with a button to its History.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { answerFromFixtures, renderKnowledge } from "@/test/knowledgeHarness";
import { GATEWAY, ITEM, PASS, UID } from "./knowledgeTestData";
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

beforeEach(() => {
  answerFromFixtures();
});
afterEach(() => {
  vi.clearAllMocks();
});

describe("the Inbox list", () => {
  test("a title, one note, and rows that open whole — no Open buttons, no count", async () => {
    renderKnowledge(`/knowledge/${UID}/inbox`);
    expect(await screen.findByRole("heading", { name: "Inbox" })).toBeInTheDocument();
    expect(
      screen.getByText("Curated into your documents within the hour, then removed from here."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/items? waiting/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Open" })).toBeNull();
    expect(screen.getByRole("button", { name: "Curate now" })).toBeInTheDocument();

    fireEvent.click(await screen.findByRole("button", { name: `Open ${ITEM.title}` }));
    expect(screen.getByTestId("where")).toHaveTextContent(
      `/knowledge/${UID}/inbox?file=${encodeURIComponent(ITEM.path)}`,
    );
  });
});

describe("an inbox item", () => {
  test("is read-only: one meta line, the title, Read-only and Curate now in the bar", async () => {
    renderKnowledge(`/knowledge/${UID}/inbox?file=${encodeURIComponent(ITEM.path)}`);
    expect(await screen.findByRole("heading", { name: ITEM.title, level: 1 })).toBeInTheDocument();
    expect(
      screen.getByText(/^Written by .* with coffer__write · .* · Waiting to be curated$/),
    ).toBeInTheDocument();
    expect(screen.getByText("Read-only")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Curate now" })).toBeInTheDocument();
    // The old status line is gone.
    expect(screen.queryByText(/Curated automatically within the hour/)).toBeNull();
  });
});

describe("a curation pass", () => {
  test("is titled, with one meta line naming where it came from", async () => {
    renderKnowledge(`/knowledge/changes/${PASS.version}`);
    expect(
      await screen.findByRole("heading", { name: "What this curation pass changed" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/· from 1 inbox item \(1 from Codex\)$/)).toBeInTheDocument();
    expect(screen.queryByText(/one new version per document/)).toBeNull();
    expect(screen.queryByText(/inbox items this pass curated left the Inbox/)).toBeNull();
    // A document link is an accent name, not an underlined one.
    expect(screen.getByRole("link", { name: GATEWAY.path })).not.toHaveClass("hover:underline");
  });

  acceptance("web-ui", "a pass is inspected and undone as a whole", async () => {
    api.undoPass.mockResolvedValue({
      ...PASS,
      version: "u9",
      operation: "undo",
      undoes: PASS.version,
    });
    renderKnowledge(`/knowledge/changes/${PASS.version}`);

    expect(await screen.findByRole("link", { name: GATEWAY.path })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "History" })[0]).toHaveAttribute(
      "href",
      `/knowledge/${UID}/history?file=${encodeURIComponent(GATEWAY.path)}`,
    );

    fireEvent.click(screen.getByRole("button", { name: "Undo this pass" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Undo this curation pass?")).toBeInTheDocument();
    expect(
      within(dialog).getByText(
        "If any document changed after this pass, nothing is undone. The inbox items aren’t queued again.",
      ),
    ).toBeInTheDocument();
    expect(api.undoPass).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Undo pass" }));
    await waitFor(() => expect(api.undoPass).toHaveBeenCalledWith(PASS.version));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  test("a refused undo is one sentence and an Open its History button; Undo this pass stays", async () => {
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
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    expect(await screen.findByText("Couldn’t undo this pass")).toBeInTheDocument();
    expect(
      screen.getByText(`${GATEWAY.path} changed after it, so nothing was undone.`),
    ).toBeInTheDocument();
    expect(screen.getByText("changed after this pass")).toBeInTheDocument();
    expect(screen.queryByText("Not undone")).toBeNull();
    // No hand-off: the way out is the document's History.
    expect(screen.queryByRole("button", { name: /Ask an agent|Copy prompt/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Undo this pass" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Open its History" }));
    expect(screen.getByTestId("where")).toHaveTextContent(
      `/knowledge/${UID}/history?file=${encodeURIComponent(GATEWAY.path)}`,
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
