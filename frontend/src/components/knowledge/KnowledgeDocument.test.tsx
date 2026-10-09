// frontend/src/components/knowledge/KnowledgeDocument.test.tsx
//
// One open knowledge file (boards 5.1.01, 5.1.29): the read-only reader with
// its single line under the title (a page's type and sources, a source's
// citing pages or Waiting mark and original) and no side rail, a page's
// resolved `[[links]]`, the pane bar (full path, no tabs, History, Preview /
// Source, Open in editor, ⋯), the history drawer beside the file reading its
// path in the vault, and delete at once with an Undo toast. Mocked only at the
// network boundary, like the Knowledge page tests.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { ApiError } from "@/lib/api/errors";
import { answerFromFixtures, renderKnowledge } from "@/test/knowledgeHarness";

import { acceptance } from "@/test/acceptance";

import { GATEWAY, NAME, RELEASE, UID, file } from "./knowledgeTestData";

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
vi.mock("@/lib/api/vault", () => ({
  vaultApi: { history: vi.fn(), diff: vi.fn(), restore: vi.fn() },
}));
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

  test("a body whose own heading differs from the title shows one title, the heading", async () => {
    api.getFile.mockResolvedValue({
      ...GATEWAY,
      title: "Gateway",
      body: "# Gateway — one door, no database\n\nThe text.\n",
    });
    renderKnowledge(OPEN);
    expect(
      await screen.findByRole("heading", { level: 1, name: "Gateway — one door, no database" }),
    ).toBeVisible();
    expect(screen.getAllByRole("heading", { name: /^Gateway/ })).toHaveLength(1);
    expect(screen.getByText("The text.")).toBeVisible();
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

  test("the bar names the full path, carries no tabs, and offers History, Preview / Source and Open in editor", async () => {
    renderKnowledge(OPEN);
    const where = await screen.findByRole("navigation", { name: "Where this file is" });
    expect(where).toHaveTextContent(NAME);
    expect(where).toHaveTextContent("gateway.md");
    expect(screen.queryByRole("navigation", { name: "Document views" })).toBeNull();
    expect(screen.queryByRole("link", { name: "History" })).toBeNull();
    expect(await screen.findByRole("button", { name: "History" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(await screen.findByRole("button", { name: "Open in editor" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();

    const preview = await screen.findByRole("button", { name: "Preview" });
    expect(preview).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Source" }));
    expect(screen.getByRole("button", { name: "Source" })).toHaveAttribute("aria-pressed", "true");
    // Source is the raw text: the heading is shown as written, not rendered.
    expect(screen.queryByRole("heading", { name: GATEWAY.title })).toBeNull();
  });

  test("the ⋯ menu holds Reveal in Finder and Delete after a separator", async () => {
    renderKnowledge(OPEN);
    fireEvent.click(
      await screen.findByRole("button", { name: `More actions for ${GATEWAY.path}` }),
    );
    const items = screen.getAllByRole("menuitem").map((i) => i.textContent);
    expect(items).toEqual(["Reveal in Finder", "Delete"]);
  });
});

const VAULT_PATH = `knowledge/${GATEWAY.path}`;

function answerHistory() {
  const row = (version: string, display_writer: string, status: string) => ({
    version,
    time: "2026-09-20T10:00:00Z",
    writer: display_writer.split(":")[0],
    display_writer,
    actor: null,
    machine: null,
    summary: "",
    operation: "edit",
    restored_from: null,
    removed: false,
    paths: [{ path: VAULT_PATH, status, added: 2, removed: 1 }],
  });
  vi.mocked(vaultApi.history).mockResolvedValue({
    path: VAULT_PATH,
    versions: [
      row("b".repeat(40), "agent:claude-code", "modified"),
      row("a".repeat(40), "user", "added"),
    ],
    next_cursor: null,
  });
  vi.mocked(vaultApi.diff).mockResolvedValue({
    path: VAULT_PATH,
    version: "b".repeat(40),
    against: "previous",
    files: [],
  });
}

describe("the history drawer", () => {
  acceptance("knowledge", "a document's history opens in a drawer beside it", async () => {
    answerHistory();
    renderKnowledge(OPEN);
    fireEvent.click(await screen.findByRole("button", { name: "History" }));

    // A drawer with the page's versions, read from its path in the vault.
    const drawer = await screen.findByRole("complementary", { name: "History of gateway.md" });
    const list = await within(drawer).findByRole("list", { name: "Versions" });
    expect(vaultApi.history).toHaveBeenCalledWith(VAULT_PATH);
    expect(
      within(list)
        .getAllByRole("button")
        .map((b) => b.textContent),
    ).toEqual([expect.stringContaining("Claude Code"), expect.stringContaining("You")]);
    // The address carries history=1, and the page is still shown beside the drawer.
    expect(screen.getByTestId("where")).toHaveTextContent("history=1");
    expect(screen.getByRole("heading", { level: 1, name: GATEWAY.title })).toBeVisible();
    expect(screen.getByText("The orchestration layer.")).toBeVisible();
    expect(screen.getByRole("button", { name: "History" })).toHaveAttribute("aria-pressed", "true");

    // Closing it leaves the page as it was and drops history=1.
    fireEvent.click(within(drawer).getByRole("button", { name: "Close history" }));
    await waitFor(() => expect(screen.queryByRole("complementary")).toBeNull());
    expect(screen.getByTestId("where")).not.toHaveTextContent("history=1");
    expect(screen.getByTestId("where")).toHaveTextContent(
      `?file=${encodeURIComponent(GATEWAY.path)}`,
    );
    expect(screen.getByRole("heading", { level: 1, name: GATEWAY.title })).toBeVisible();
  });

  test("the old History tab address opens the drawer", async () => {
    answerHistory();
    renderKnowledge(`/knowledge/${UID}/history?file=${encodeURIComponent(GATEWAY.path)}`);
    await waitFor(() =>
      expect(screen.getByTestId("where")).toHaveTextContent(
        `/knowledge/${UID}?file=${encodeURIComponent(GATEWAY.path)}&history=1`,
      ),
    );
    expect(
      await screen.findByRole("complementary", { name: "History of gateway.md" }),
    ).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 1, name: GATEWAY.title })).toBeVisible();
  });

  test("Esc closes the drawer", async () => {
    answerHistory();
    renderKnowledge(`${OPEN}&history=1`);
    const drawer = await screen.findByRole("complementary", { name: "History of gateway.md" });
    fireEvent.keyDown(within(drawer).getByRole("button", { name: "Close history" }), {
      key: "Escape",
    });
    await waitFor(() => expect(screen.queryByRole("complementary")).toBeNull());
  });
});

describe("a page's line and links", () => {
  const CACHE = file(`${NAME}/pages/cache-ttl.md`, { title: "Cache TTL" });
  const PAGE = file(`${NAME}/pages/session-ownership.md`, {
    title: "Session ownership",
    page_type: "decision",
    body: [
      "# Session ownership",
      "",
      "See [[cache-ttl|the cache]] and [[gone]].",
      "",
      "```",
      "[[cache-ttl]]",
      "```",
    ].join("\n"),
    sources: [
      { slug: "release-notes", path: RELEASE.path, title: "Release notes" },
      { slug: "old-spec", path: null, title: "" },
    ],
    links: [
      { target: "cache-ttl", path: CACHE.path, ambiguous: false },
      { target: "gone", path: null, ambiguous: false },
    ],
  });

  acceptance("knowledge", "a page shows its sources and resolves its links", async () => {
    api.getFile.mockImplementation(async (path: string) =>
      path === PAGE.path ? PAGE : path === CACHE.path ? CACHE : RELEASE,
    );
    renderKnowledge(`/knowledge/${UID}?file=${encodeURIComponent(PAGE.path)}`);
    expect(await screen.findByRole("heading", { level: 1, name: PAGE.title })).toBeVisible();

    // The line under the title: its type, then both sources — the existing one
    // opening it, the missing one struck through.
    const line = screen.getByTestId("file-line");
    expect(within(line).getByTestId("page-type")).toHaveTextContent("decision");
    expect(within(line).getByRole("link", { name: "Release notes" })).toHaveAttribute(
      "href",
      `/knowledge/${UID}?file=${encodeURIComponent(RELEASE.path)}`,
    );
    const missing = within(line).getByText("old-spec");
    expect(missing.tagName).toBe("S");
    expect(within(line).queryByRole("link", { name: "old-spec" })).toBeNull();

    // The existing link opens the page it names; the dead one is in the danger tone.
    const link = screen.getByRole("link", { name: "the cache" });
    expect(link).toHaveAttribute(
      "href",
      `/knowledge/${UID}?file=${encodeURIComponent(CACHE.path)}`,
    );
    const dead = screen.getByText("gone");
    expect(dead.closest("a")).toBeNull();
    expect(dead).toHaveAttribute("data-link", "dead");
    expect(dead.className).toMatch(/text-danger/);
    // The one inside a code block is text, not a link.
    expect(screen.getByText("[[cache-ttl]]")).toBeInTheDocument();

    fireEvent.click(link);
    expect(await screen.findByRole("heading", { level: 1, name: CACHE.title })).toBeVisible();
    expect(screen.getByTestId("where")).toHaveTextContent(encodeURIComponent(CACHE.path));
  });

  test("a waiting source shows the Waiting mark and its original's name", async () => {
    renderKnowledge(`/knowledge/${UID}?file=${encodeURIComponent(RELEASE.path)}`);
    const line = await screen.findByTestId("file-line");
    expect(within(line).getByText("Waiting")).toBeInTheDocument();
    expect(within(line).getByText("Original: release-notes.pdf")).toBeInTheDocument();
    expect(within(line).queryByText(/Cited by/)).toBeNull();
  });

  test("a cited source names the pages that cite it, each opening the page", async () => {
    api.getFile.mockResolvedValue({
      ...RELEASE,
      waiting: false,
      original_path: null,
      cited_by: [{ path: GATEWAY.path, title: GATEWAY.title }],
    });
    renderKnowledge(`/knowledge/${UID}?file=${encodeURIComponent(RELEASE.path)}`);
    const line = await screen.findByTestId("file-line");
    expect(within(line).getByText(/Cited by 1 page/)).toBeInTheDocument();
    expect(within(line).getByRole("link", { name: GATEWAY.title })).toHaveAttribute(
      "href",
      `/knowledge/${UID}?file=${encodeURIComponent(GATEWAY.path)}`,
    );
    expect(within(line).queryByText("Waiting")).toBeNull();
  });
});

describe("delete a document", () => {
  async function deleteIt() {
    api.deleteFile.mockResolvedValue(undefined);
    renderKnowledge(OPEN);
    fireEvent.click(
      await screen.findByRole("button", { name: `More actions for ${GATEWAY.path}` }),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete" }));
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
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete" }));
    expect(await screen.findByText("Couldn’t delete gateway.md")).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent("file=");
  });
});
