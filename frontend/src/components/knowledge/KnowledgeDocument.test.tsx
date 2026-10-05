// frontend/src/components/knowledge/KnowledgeDocument.test.tsx
//
// One open knowledge document (boards 5.1.01, 5.1.29): the read-only reader with
// its single properties line (read from the frontmatter) and no side rail, the
// pane bar (full path, no tabs, Preview / Source, Open in editor, ⋯), History…
// opening the shared dialog on the document's path in the vault, and delete at
// once with an Undo toast. Mocked only at the network boundary, like the
// Knowledge page tests.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { ApiError } from "@/lib/api/errors";
import { answerFromFixtures, renderKnowledge } from "@/test/knowledgeHarness";

import { GATEWAY, NAME, UID } from "./knowledgeTestData";

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
}));
vi.mock("@/lib/api/vault", () => ({ vaultApi: { historyHandoff: vi.fn() } }));
vi.mock("@/lib/api/agentProviders", () => ({
  agentProvidersApi: { list: vi.fn().mockResolvedValue({ agents: [] }) },
}));
vi.mock("@/lib/hooks/useDaemonEvents", () => ({ useDaemonEvents: () => undefined }));

const api = vi.mocked(await import("@/lib/api/knowledge"));
const { vaultApi } = await import("@/lib/api/vault");
const OPEN = `/knowledge/${UID}?file=${encodeURIComponent(GATEWAY.path)}`;
const ROOT = new RegExp(`/knowledge/${UID}$`);

beforeEach(() => {
  answerFromFixtures();
});
afterEach(() => {
  vi.clearAllMocks();
});

describe("the reader", () => {
  test("has no side rail, only one properties line read from the frontmatter under the title", async () => {
    renderKnowledge(OPEN);
    expect(await screen.findByRole("heading", { level: 1, name: GATEWAY.title })).toBeVisible();
    expect(screen.queryByRole("complementary")).toBeNull();
    expect(screen.queryByText("On this page")).toBeNull();
    expect(screen.queryByText("Properties")).toBeNull();
    expect(await screen.findByText("Created Sep 12 by you")).toBeInTheDocument();
  });

  test("names an agent that wrote it", async () => {
    api.getFile.mockResolvedValue({ ...GATEWAY, actor: "claude-code" });
    renderKnowledge(OPEN);
    expect(await screen.findByText("Created Sep 12 by Claude Code")).toBeVisible();
  });

  test("a document with no created date says nothing of it", async () => {
    api.getFile.mockResolvedValue({ ...GATEWAY, created_at: "" });
    renderKnowledge(OPEN);
    expect(await screen.findByRole("heading", { level: 1, name: GATEWAY.title })).toBeVisible();
    expect(screen.queryByText(/Created/)).toBeNull();
    expect(screen.queryByText(/Invalid Date/)).toBeNull();
  });

  test("the bar names the full path, has no tabs, and offers Preview / Source and Open in editor", async () => {
    renderKnowledge(OPEN);
    const where = await screen.findByRole("navigation", { name: "Where this document is" });
    expect(where).toHaveTextContent(NAME);
    expect(where).toHaveTextContent("gateway.md");
    expect(screen.queryByRole("link", { name: "History" })).toBeNull();
    expect(screen.queryByRole("navigation", { name: "Document views" })).toBeNull();
    expect(await screen.findByRole("button", { name: "Open in editor" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();

    const preview = await screen.findByRole("button", { name: "Preview" });
    expect(preview).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Source" }));
    expect(screen.getByRole("button", { name: "Source" })).toHaveAttribute("aria-pressed", "true");
    // Source is the raw text: the heading is shown as written, not rendered.
    expect(screen.queryByRole("heading", { name: GATEWAY.title })).toBeNull();
  });

  test("the ⋯ menu holds Reveal in Finder, History… and Delete document after a separator", async () => {
    renderKnowledge(OPEN);
    fireEvent.click(
      await screen.findByRole("button", { name: `More actions for ${GATEWAY.path}` }),
    );
    const items = screen.getAllByRole("menuitem").map((i) => i.textContent);
    expect(items).toEqual(["Reveal in Finder", "History…", "Delete document"]);
  });
});

describe("History…", () => {
  test("opens the shared dialog on the document's path in the vault", async () => {
    const path = `knowledge/${GATEWAY.path}`;
    vi.mocked(vaultApi.historyHandoff).mockResolvedValue({
      path,
      absolute_path: `/Users/dev/.coffer/vault/${path}`,
      vault_path: "/Users/dev/.coffer/vault",
      log_command: `git -C /Users/dev/.coffer/vault log -p -- ${path}`,
      handoff: { prompt: "Restore it." },
    });
    renderKnowledge(OPEN);
    fireEvent.click(
      await screen.findByRole("button", { name: `More actions for ${GATEWAY.path}` }),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "History…" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByTestId("vault-history-path")).toHaveTextContent(path);
    expect(within(dialog).getByRole("button", { name: "Copy git command" })).toBeInTheDocument();
    await waitFor(() => expect(vaultApi.historyHandoff).toHaveBeenCalledWith(path, null));
    // The dialog lists no versions and restores nothing itself.
    expect(within(dialog).queryByRole("list")).toBeNull();
    expect(within(dialog).queryByRole("button", { name: /^Restore/ })).toBeNull();
  });
});

describe("delete a document", () => {
  async function deleteIt() {
    api.deleteFile.mockResolvedValue(undefined);
    renderKnowledge(OPEN);
    fireEvent.click(
      await screen.findByRole("button", { name: `More actions for ${GATEWAY.path}` }),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete document" }));
  }

  test("runs at once, with no confirmation, and goes to the collection", async () => {
    await deleteIt();
    await waitFor(() => expect(api.deleteFile).toHaveBeenCalledWith(GATEWAY.path));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(await screen.findByText("Deleted gateway.md")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent(ROOT));
  });

  test("its toast's Undo restores the delete found in the changes feed", async () => {
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
    api.listChanges.mockResolvedValue({ changes: [deletion], next_cursor: null });
    api.restoreDeleted.mockResolvedValue(deletion);
    await deleteIt();
    fireEvent.click(await screen.findByRole("button", { name: "Undo" }));
    await waitFor(() => expect(api.restoreDeleted).toHaveBeenCalledWith("d3l3t3"));
  });

  test("a refused delete is an error toast and the pane stays on the document", async () => {
    api.deleteFile.mockRejectedValue(new ApiError("INTERNAL", "nope"));
    renderKnowledge(OPEN);
    fireEvent.click(
      await screen.findByRole("button", { name: `More actions for ${GATEWAY.path}` }),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete document" }));
    expect(await screen.findByText("Couldn’t delete gateway.md")).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent("file=");
  });
});
