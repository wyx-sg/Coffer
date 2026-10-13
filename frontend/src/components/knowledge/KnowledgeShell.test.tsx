// frontend/src/components/knowledge/KnowledgeShell.test.tsx
//
// The Knowledge page's shell (boards 5.1.01, 5.1.03, 5.1.09, 5.1.11, 5.1.12,
// 5.1.13, 5.1.26–28; Foundations 0.6.04): the header (title, Experimental tag,
// one subtitle, Tidy all and the one primary Add menu, each entry saying what
// it keeps in Coffer), the landing with no collection open, the first-run
// empty state, the tree (a Collections strip with New collection, each page
// with its type's icon) and the Upload dialog — several files at once, each
// with its own outcome, and Cancel. Mocked only at the network boundary, like the page tests.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import {
  COLLECTION,
  GATEWAY,
  OTHER,
  TREES,
  UID,
  ingested,
} from "@/components/knowledge/knowledgeTestData";
import { answerFromFixtures, renderKnowledge } from "@/test/knowledgeHarness";

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
vi.mock("@/lib/hooks/useDaemonEvents", () => ({ useDaemonEvents: () => undefined }));
vi.mock("@/lib/api/agentProviders", () => ({
  agentProvidersApi: {
    list: vi.fn().mockResolvedValue({
      agents: [{ agent_key: "claude_code", display_name: "Claude Code", available: true }],
    }),
  },
}));

vi.mock("@/lib/api/fs", () => ({
  fsApi: { listTerminals: vi.fn().mockResolvedValue([]), openTerminal: vi.fn() },
}));

const api = vi.mocked(await import("@/lib/api/knowledge"));

const SUBTITLE = "Pages your agents write from the sources you keep. Every agent can read them.";

beforeEach(() => {
  answerFromFixtures();
});
afterEach(() => {
  vi.clearAllMocks();
});

function tree() {
  return screen.getByRole("navigation", { name: "Collections and documents" });
}

describe("the header", () => {
  acceptance("knowledge", "the Add menu says what each entry keeps in Coffer", async () => {
    renderKnowledge(`/knowledge/${UID}?file=${encodeURIComponent(GATEWAY.path)}`);
    const tidyAll = await within(screen.getByRole("banner")).findByRole("button", {
      name: "Tidy all",
    });
    expect(within(screen.getByRole("banner")).getByRole("heading")).toHaveTextContent("Knowledge");
    expect(screen.getByText("Experimental")).toBeInTheDocument();
    expect(screen.getByText(SUBTITLE)).toBeInTheDocument();
    expect(tidyAll.className).not.toMatch(/bg-accent/);
    // No curation control any more: no Automatic button, no engine link.
    expect(screen.queryByTestId("knowledge-automatic")).toBeNull();
    // One primary Add, right of Tidy all, and no separate Upload button.
    const add = screen.getByRole("button", { name: "Add" });
    expect(add.className).toMatch(/bg-accent/);
    expect(tidyAll.compareDocumentPosition(add) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Upload" })).toBeNull();
    fireEvent.click(add);
    const items = await screen.findAllByRole("menuitem");
    expect(items.map((i) => i.textContent)).toEqual([
      "Upload documents…Converted to Markdown and kept in the collection you pick, synced with it.",
      "New collection…Kept in Coffer: synced to your other Macs, with history, tidied by your agent.",
      "Link an external folder…Files stay where they are and are only shared with agents. Nothing is copied into Coffer, synced or tidied.",
    ]);
    // "Add a document" no longer exists.
    expect(screen.queryByRole("button", { name: "Add a document" })).toBeNull();
    // 16 top / 32 sides / 12 bottom, no divider.
    const header = screen.getByRole("banner");
    expect(header.parentElement?.className).toMatch(/px-8/);
    expect(header.parentElement?.className).not.toMatch(/border-b/);
    // The pane offers no Edit: a document is changed in the person's own editor.
    expect(await screen.findByRole("button", { name: "Open in editor" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  test("New collection… in the Add menu opens the New collection dialog", async () => {
    renderKnowledge(`/knowledge/${UID}`);
    fireEvent.click(await screen.findByRole("button", { name: "Add" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /^New collection…/ }));
    expect(await screen.findByRole("dialog")).toHaveTextContent("New collection");
  });
});

describe("with no collection open", () => {
  test("the tree lists the collections, the pane says to pick one, and Tidy all stays", async () => {
    renderKnowledge("/knowledge");
    expect(await screen.findByText("Pick a collection")).toBeInTheDocument();
    expect(
      await within(tree()).findByRole("button", { name: new RegExp(`^${COLLECTION.name}$`) }),
    ).toBeInTheDocument();
    expect(
      await within(screen.getByRole("banner")).findByRole("button", { name: "Tidy all" }),
    ).toBeInTheDocument();
    // There is no Recent changes view: a file's history opens from its pane bar.
    expect(screen.queryByText("Recent changes")).toBeNull();
    expect(screen.queryByRole("link", { name: /Recent changes/ })).toBeNull();
  });

  test("an address naming an unknown tab opens the document", async () => {
    renderKnowledge(`/knowledge/${UID}/changes?file=${encodeURIComponent(GATEWAY.path)}`);
    await waitFor(() =>
      expect(screen.getByTestId("where")).toHaveTextContent(
        `/knowledge/${UID}?file=${encodeURIComponent(GATEWAY.path)}`,
      ),
    );
    expect(await screen.findByRole("heading", { level: 1, name: "Account Gateway" })).toBeVisible();
  });
});

describe("first run", () => {
  test("no collections: the standard empty state with New collection, no Upload or Tidy all", async () => {
    api.listCollections.mockResolvedValue({ collections: [] });
    renderKnowledge("/knowledge");
    expect(await screen.findByText("No collections yet")).toBeInTheDocument();
    expect(screen.getByText(/A collection is a folder of Markdown documents/)).toBeInTheDocument();
    expect(screen.getByText(SUBTITLE)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Tidy all" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "New collection" }));
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText("Every agent sees it through the coffer-guide skill."),
    ).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Cancel" }).className).toMatch(
      /bg-transparent/,
    );
  });
});

describe("the tree", () => {
  test("no node shows a count and no Inbox node is listed; Collections strip holds New collection", async () => {
    renderKnowledge(`/knowledge/${UID}`);
    const nav = tree();
    await within(nav).findByRole("button", { name: "Pages" });
    expect(within(nav).queryByRole("button", { name: /^Inbox/ })).toBeNull();
    // The collection rows carry no number.
    const row = within(nav).getByRole("button", { name: new RegExp(`^${COLLECTION.name}$`) });
    expect(row).not.toHaveTextContent(/\d/);
    // A collection with no documents shows no "0".
    fireEvent.click(within(nav).getByRole("button", { name: `Expand ${OTHER.name}` }));
    expect(nav.textContent).not.toMatch(/(^|\s)0(\s|$)/);
    // New collection is the strip's icon button; there is no bottom "+ New collection".
    expect(within(nav).getAllByRole("button", { name: "New collection" })).toHaveLength(1);
    fireEvent.click(within(nav).getByRole("button", { name: "New collection" }));
    expect(await screen.findByRole("dialog")).toHaveTextContent("New collection");
  });

  acceptance("knowledge", "the tree marks each page with its type's icon", async () => {
    const page = (slug: string, page_type: string) => ({
      path: `${COLLECTION.name}/pages/${slug}.md`,
      kind: "page" as const,
      title: slug,
      description: "",
      page_type,
      waiting: false,
      stale: false,
      superseded_by: "",
      summary: "",
      cited_count: 0,
      skipped: false,
      actor: "user",
      updated_at: "2026-09-20T00:00:00Z",
    });
    api.getTree.mockImplementation(async (path: string) => {
      if (path === `${COLLECTION.name}/pages`) {
        return {
          path,
          directories: [],
          files: [page("map", "overview"), page("runbook", "playbook"), page("loose", "")],
        };
      }
      return TREES[path] ?? { path, directories: [], files: [] };
    });
    renderKnowledge(`/knowledge/${UID}`);
    const nav = tree();
    fireEvent.click(await within(nav).findByRole("button", { name: "Pages" }));
    fireEvent.click(within(nav).getByRole("button", { name: "Sources" }));
    const icon = async (name: RegExp) =>
      (await within(nav).findByRole("button", { name })).querySelector("svg[data-icon]");
    expect(await icon(/^map\.md/)).toHaveAttribute("data-icon", "overview");
    expect(await icon(/^map\.md/)).toHaveClass("lucide-compass");
    // A type the README defines has no icon of its own: the generic page icon.
    expect(await icon(/^runbook\.md/)).toHaveClass("lucide-file-text");
    expect(await icon(/^loose\.md/)).toHaveAttribute("data-icon", "untyped");
    expect(await icon(/^loose\.md/)).toHaveClass("lucide-file-question-mark");
    const source = await within(nav).findByRole("button", { name: /^release-notes\.md/ });
    expect(source.querySelector("svg[data-icon]")).toHaveAttribute("data-icon", "source");
    expect(source.querySelector("svg[data-icon]")).toHaveClass("lucide-scroll-text");
    expect(source).toHaveTextContent("Waiting");
  });

  acceptance("knowledge", "the tree comes back as the person left it", async () => {
    renderKnowledge("/knowledge");
    let nav = tree();
    // Open a collection, then its Sources folder, and open a second collection.
    fireEvent.click(await within(nav).findByRole("button", { name: `Expand ${COLLECTION.name}` }));
    fireEvent.click(await within(nav).findByRole("button", { name: "Sources" }));
    expect(await within(nav).findByRole("button", { name: /^release-notes\.md/ })).toBeVisible();
    fireEvent.click(within(nav).getByRole("button", { name: `Expand ${OTHER.name}` }));
    cleanup();

    // Coming back to the page finds the same collections and folder open.
    renderKnowledge("/knowledge");
    nav = tree();
    expect(
      await within(nav).findByRole("button", { name: `Collapse ${COLLECTION.name}` }),
    ).toHaveAttribute("aria-expanded", "true");
    expect(within(nav).getByRole("button", { name: `Collapse ${OTHER.name}` })).toBeVisible();
    expect(await within(nav).findByRole("button", { name: "Sources" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(await within(nav).findByRole("button", { name: /^release-notes\.md/ })).toBeVisible();
    expect(within(nav).getByRole("button", { name: "Pages" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );

    // Closing them is remembered too.
    fireEvent.click(within(nav).getByRole("button", { name: `Collapse ${COLLECTION.name}` }));
    cleanup();
    renderKnowledge("/knowledge");
    expect(
      await within(tree()).findByRole("button", { name: `Expand ${COLLECTION.name}` }),
    ).toHaveAttribute("aria-expanded", "false");
  });
});

describe("the Upload dialog", () => {
  async function openUpload() {
    fireEvent.click(await screen.findByRole("button", { name: "Add" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /^Upload documents…/ }));
    return screen.findByRole("dialog");
  }

  acceptance("knowledge", "upload several files at once, each with its own outcome", async () => {
    api.uploadFile.mockImplementation(async ({ file }: { file: File }) => {
      if (file.name === "scan.pdf") {
        throw new ApiError("KNOWLEDGE_INGEST_FAILED", "no text", { reason: "scanned_pdf" });
      }
      return ingested(`${COLLECTION.name}/sources/notes.md`, { title: "notes" });
    });
    renderKnowledge(`/knowledge/${UID}`);
    const dialog = await openUpload();
    expect(
      within(dialog).getByText(
        "Coffer converts each to Markdown and keeps it, with its pictures, as a source of the collection. The uploaded file itself stays on this Mac only.",
      ),
    ).toBeInTheDocument();
    const big = new File(["x"], "huge.pdf", { type: "application/pdf" });
    Object.defineProperty(big, "size", { value: 21 * 1024 * 1024 });
    fireEvent.change(within(dialog).getByLabelText("Drop files here, or choose them"), {
      target: {
        files: [
          new File(["hello"], "notes.md", { type: "text/markdown" }),
          new File(["%PDF"], "scan.pdf", { type: "application/pdf" }),
          new File(["PK"], "bundle.zip", { type: "application/zip" }),
          big,
        ],
      },
    });
    // The ZIP and the large file are refused before anything is sent.
    const files = within(dialog).getByRole("list", { name: "Files to upload" });
    const row = (name: string) => within(files).getByText(name).closest("li") as HTMLElement;
    expect(row("bundle.zip")).toHaveTextContent("ZIP files can't be converted");
    expect(row("huge.pdf")).toHaveTextContent("Larger than 20 MB");
    fireEvent.click(within(dialog).getByRole("button", { name: "Upload 2 files" }));

    // The other two go one after another, each with its own outcome.
    await waitFor(() => expect(row("scan.pdf")).toHaveAttribute("data-status", "refused"));
    expect(api.uploadFile).toHaveBeenCalledTimes(2);
    expect(api.uploadFile.mock.calls.map(([p]) => p.file.name)).toEqual(["notes.md", "scan.pdf"]);
    expect(row("notes.md")).toHaveAttribute("data-status", "saved");
    expect(row("notes.md")).toHaveTextContent(`Saved as ${COLLECTION.name}/sources/notes.md`);
    expect(row("scan.pdf")).toHaveTextContent("No text in this PDF");
    // One toast sums it up; the dialog stays on the outcomes.
    expect(await screen.findByText("1 uploaded; 3 couldn’t be")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    // The refused PDF stays to be tried again.
    fireEvent.click(within(dialog).getByRole("button", { name: "Retry" }));
    expect(row("scan.pdf")).toHaveAttribute("data-status", "ready");
    expect(within(dialog).getByRole("button", { name: "Upload" })).toBeEnabled();
  });

  test("when every file is saved the dialog closes with one toast", async () => {
    api.uploadFile.mockImplementation(async ({ file }: { file: File }) =>
      ingested(`${COLLECTION.name}/sources/${file.name}`, { title: file.name }),
    );
    renderKnowledge(`/knowledge/${UID}`);
    const dialog = await openUpload();
    fireEvent.change(within(dialog).getByLabelText("Drop files here, or choose them"), {
      target: {
        files: [new File(["a"], "a.md"), new File(["b"], "b.md")],
      },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Upload 2 files" }));
    expect(await screen.findByText(`Uploaded 2 files to ${COLLECTION.name}`)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  test("Cancel stays live while converting and aborts the upload", async () => {
    let signal: AbortSignal | undefined;
    api.uploadFile.mockImplementation(
      (params: { signal?: AbortSignal }) =>
        new Promise((_resolve, reject) => {
          signal = params.signal;
          params.signal?.addEventListener("abort", () =>
            reject(new DOMException("x", "AbortError")),
          );
        }),
    );
    renderKnowledge(`/knowledge/${UID}`);
    const dialog = await openUpload();
    const input = within(dialog).getByLabelText("Drop files here, or choose them");
    fireEvent.change(input, {
      target: {
        files: [
          new File(["hello"], "notes.md", { type: "text/markdown" }),
          new File(["more"], "more.md", { type: "text/markdown" }),
        ],
      },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Upload 2 files" }));
    await waitFor(() => expect(api.uploadFile).toHaveBeenCalled());
    const cancel = within(dialog).getByRole("button", { name: "Cancel" });
    expect(cancel).toBeEnabled();
    fireEvent.click(cancel);
    expect(signal?.aborted).toBe(true);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    // The second file is never sent.
    expect(api.uploadFile).toHaveBeenCalledTimes(1);
  });
});
