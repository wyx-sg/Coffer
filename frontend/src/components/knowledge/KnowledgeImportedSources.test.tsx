// frontend/src/components/knowledge/KnowledgeImportedSources.test.tsx
//
// Files kept in place and readable imported sources (design §2, §7, §8): the
// reader previews a Confluence source's `display_body` while Source shows the
// file as it is, renders a document's HTML sanitized (tables, folds — never
// scripts, frames, comments or handlers), opens a standard relative link to
// another knowledge file in-app and leaves one outside the folder as text;
// To do names links that leave the knowledge folder; and an upload the import
// kept only in part says so, issue by issue. Mocked only at the network
// boundary, like the other Knowledge page tests.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { acceptance } from "@/test/acceptance";
import { answerFromFixtures, renderKnowledge } from "@/test/knowledgeHarness";

import { COLLECTION, GATEWAY, UID, file, ingested } from "./knowledgeTestData";

vi.mock("@/lib/api/knowledge", () => ({
  listCollections: vi.fn(),
  createCollection: vi.fn(),
  getTree: vi.fn(),
  getFile: vi.fn(),
  getAsset: vi.fn(),
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
  agentProvidersApi: { list: vi.fn().mockResolvedValue({ agents: [] }) },
}));
vi.mock("@/lib/api/fs", () => ({
  fsApi: {
    listTerminals: vi.fn().mockResolvedValue([]),
    listEditors: vi.fn().mockResolvedValue([]),
    openTerminal: vi.fn(),
    open: vi.fn().mockResolvedValue(undefined),
  },
}));

const api = vi.mocked(await import("@/lib/api/knowledge"));

const PICTURE = "data:image/png;base64,iVBORw0KGgo=";
const ASSET = `${COLLECTION.name}/assets/space-1a2b/diagram.png`;
const MARKER =
  "<!-- skynet-confluence-storage:v1\n&lt;ac:structured-macro ac:name=&quot;info&quot;&gt;Secret macro body&lt;/ac:structured-macro&gt;\n-->";
const CONFLUENCE = file(`${COLLECTION.name}/sources/space-page.md`, {
  kind: "source",
  title: "Space page",
  page_type: "",
  body: `Intro line.\n\n${MARKER}\n\nOutro line.\n`,
  display_body: "Intro line.\n\n> **Info:** Expanded macro body\n\nOutro line.\n",
});
const HTML = file(`${COLLECTION.name}/sources/html-page.md`, {
  kind: "source",
  title: "HTML page",
  page_type: "",
  body: [
    "Before.",
    "",
    "<!-- a comment nobody should read -->",
    '<table><tbody><tr><td colspan="2">Spanning cell</td></tr><tr><td>a</td><td>b</td></tr></tbody></table>',
    "",
    "<details><summary>More detail</summary>Folded text</details>",
    "",
    '<script>window.__pwned = true</script><style>body{display:none}</style><iframe src="https://evil.example"></iframe>',
    "",
    '<img src="../assets/space-1a2b/diagram.png" alt="Diagram" onerror="window.__pwned = true">',
    "",
    "After.",
  ].join("\n"),
});
const LINKS = file(`${COLLECTION.name}/sources/links.md`, {
  kind: "source",
  title: "Links",
  page_type: "",
  body: [
    "See [the gateway](../pages/gateway.md), [the escape](../../../etc/passwd)",
    "and [a ghost](ghost.md) and [the web](https://example.com).",
  ].join("\n"),
  links: [
    {
      target: "../pages/gateway.md",
      path: GATEWAY.path,
      kind: "markdown",
      outside: false,
      ambiguous: false,
    },
    {
      target: "../../../etc/passwd",
      path: null,
      kind: "markdown",
      outside: true,
      ambiguous: false,
    },
    { target: "ghost.md", path: null, kind: "markdown", outside: false, ambiguous: false },
  ],
});

beforeEach(() => {
  answerFromFixtures();
  const fixture = api.getFile.getMockImplementation()!;
  const extra: Record<string, typeof HTML> = {
    [CONFLUENCE.path]: CONFLUENCE,
    [HTML.path]: HTML,
    [LINKS.path]: LINKS,
  };
  api.getFile.mockImplementation(async (path: string) => extra[path] ?? fixture(path));
  api.getAsset.mockImplementation(async (path: string) => (path === ASSET ? PICTURE : null));
});
afterEach(() => {
  vi.clearAllMocks();
  cleanup();
  delete (window as { __pwned?: boolean }).__pwned;
});

const open = (path: string) =>
  renderKnowledge(`/knowledge/${UID}?file=${encodeURIComponent(path)}`);

describe("the reader", () => {
  acceptance("knowledge", "a source holding storage markers reads as Markdown", async () => {
    open(CONFLUENCE.path);
    const container = document.body;
    expect(await screen.findByText("Expanded macro body")).toBeVisible();
    expect(screen.getByText("Info:").tagName).toBe("STRONG");
    expect(container.textContent).not.toContain("skynet-confluence-storage");
    expect(container.textContent).not.toContain("Secret macro body");

    // Source still shows the file as it is, markers and all.
    fireEvent.click(screen.getByRole("button", { name: "Source" }));
    await waitFor(() => expect(container.textContent).toContain("skynet-confluence-storage:v1"));
    expect(container.textContent).not.toContain("Expanded macro body");
  });

  acceptance("knowledge", "the reader never runs a document's HTML", async () => {
    open(HTML.path);
    const container = document.body;
    // Tables (with spans) and folds render as HTML.
    const cell = await screen.findByText("Spanning cell");
    expect(cell.tagName).toBe("TD");
    expect(cell).toHaveAttribute("colspan", "2");
    expect(screen.getByText("More detail").tagName).toBe("SUMMARY");
    expect(screen.getByText("More detail").closest("details")).not.toBeNull();
    // A picture in raw HTML still goes through the asset route.
    const picture = await screen.findByRole("img", { name: "Diagram" });
    expect(picture).toHaveAttribute("src", PICTURE);
    expect(picture).not.toHaveAttribute("onerror");
    // Nothing that runs, styles or frames survives, nor the comment as text.
    for (const tag of ["script", "style", "iframe", "object", "embed", "form"]) {
      expect(container.querySelector(tag)).toBeNull();
    }
    expect(container.innerHTML).not.toMatch(/\son[a-z]+=/i);
    expect(container.textContent).not.toContain("a comment nobody should read");
    expect(container.textContent).not.toContain("__pwned");
    expect((window as { __pwned?: boolean }).__pwned).toBeUndefined();
  });

  test("a standard relative link opens the knowledge file it resolves to", async () => {
    open(LINKS.path);
    fireEvent.click(await screen.findByRole("link", { name: "the gateway" }));
    await waitFor(() =>
      expect(screen.getByTestId("where")).toHaveTextContent(
        `/knowledge/${UID}?file=${encodeURIComponent(GATEWAY.path)}`,
      ),
    );
    expect(await screen.findByRole("heading", { level: 1, name: GATEWAY.title })).toBeVisible();
  });

  test("a link outside the knowledge folder, or to no file, is text that says so", async () => {
    open(LINKS.path);
    const escape = await screen.findByText("the escape");
    expect(escape.closest("a")).toBeNull();
    expect(escape).toHaveAttribute("data-link", "outside");
    expect(escape).toHaveAttribute("title", "../../../etc/passwd is outside the knowledge folder");
    const ghost = screen.getByText("a ghost");
    expect(ghost.closest("a")).toBeNull();
    expect(ghost).toHaveAttribute("title", "No file at ghost.md");
    // An external link still opens in a new window.
    expect(screen.getByRole("link", { name: "the web" })).toHaveAttribute(
      "href",
      "https://example.com",
    );
  });
});

describe("To do", () => {
  test("names links that leave the knowledge folder", async () => {
    api.getCheck.mockResolvedValue({
      collection: COLLECTION,
      findings: [
        { kind: "outside_link", path: LINKS.path, target: "../../../etc/passwd", others: [] },
      ],
    });
    renderKnowledge(`/knowledge/${UID}`);
    const todo = await screen.findByRole("region", { name: "To do" });
    expect(await within(todo).findByText("Links leaving the knowledge folder")).toBeVisible();
    expect(within(todo).getByText("→ ../../../etc/passwd")).toBeInTheDocument();
  });
});

describe("Upload", () => {
  acceptance("knowledge", "an upload reports what it kept and what it could not", async () => {
    api.uploadFile.mockImplementation(async ({ file: f }: { file: File }) =>
      f.name === "page.html"
        ? ingested(`${COLLECTION.name}/sources/page.md`, {
            status: "partial",
            files: [`${COLLECTION.name}/assets/page/diagram.png`],
            issues: [
              { kind: "missing_attachment", name: "spec.pdf", reason: "not in the export" },
              { kind: "external_embed", name: "jira", reason: "kept as a link" },
            ],
          })
        : ingested(`${COLLECTION.name}/sources/notes.md`),
    );
    renderKnowledge(`/knowledge/${UID}`);
    fireEvent.click(await screen.findByRole("button", { name: "Add" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /^Upload documents…/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Drop files here, or choose them"), {
      target: {
        files: [
          new File(["<p>x</p>"], "page.html", { type: "text/html" }),
          new File(["hello"], "notes.md", { type: "text/markdown" }),
        ],
      },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Upload 2 files" }));

    const files = within(dialog).getByRole("list", { name: "Files to upload" });
    const row = (name: string) => within(files).getByText(name).closest("li") as HTMLElement;
    await waitFor(() => expect(row("notes.md")).toHaveAttribute("data-status", "saved"));
    // Kept in part: a warning, never a plain success, with each issue listed.
    expect(row("page.html")).toHaveAttribute("data-status", "partial");
    expect(row("page.html")).toHaveTextContent(
      `Imported as ${COLLECTION.name}/sources/page.md with 2 issues`,
    );
    const issues = within(row("page.html")).getByRole("list", {
      name: "What page.html could not keep",
    });
    const items = within(issues).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Missing attachment spec.pdf — not in the export");
    expect(items[1]).toHaveTextContent("External embed jira — kept as a link");
    // The dialog stays on the outcomes, with a toast that says there is more to see.
    expect(await screen.findByText("2 uploaded; 1 with issues to look at")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
