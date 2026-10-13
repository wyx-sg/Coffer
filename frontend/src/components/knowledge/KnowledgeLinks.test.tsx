// frontend/src/components/knowledge/KnowledgeLinks.test.tsx
//
// Every link in an open knowledge file opens where it points (spec knowledge
// "Link pages by slug or relative path and check every link"), and an
// imported Confluence page reads as the page, not its markup (spec knowledge
// "Import a Confluence page as a readable source with its attachments"):
// a web link in a table the import kept as HTML is a link, opened by the
// daemon in the desktop app; a relative path opens the file it names, in its
// own collection; a dead or outside one is marked; a fidelity comment never
// shows; an older source with markers reads converted, with a note.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { answerFromFixtures, renderKnowledge } from "@/test/knowledgeHarness";
import { acceptance } from "@/test/acceptance";

import { NAME, OTHER, RELEASE, UID, file } from "./knowledgeTestData";

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
vi.mock("@/lib/api/vault", () => ({
  vaultApi: { history: vi.fn(), diff: vi.fn(), restore: vi.fn() },
}));
vi.mock("@/lib/api/agentProviders", () => ({
  agentProvidersApi: { list: vi.fn().mockResolvedValue({ agents: [] }) },
}));
vi.mock("@/lib/api/fs", () => ({
  fsApi: { open: vi.fn(), reveal: vi.fn(), openUrl: vi.fn().mockResolvedValue(undefined) },
}));
vi.mock("@/lib/tauri", async (original) => ({
  ...(await original<typeof import("@/lib/tauri")>()),
  inDesktopShell: vi.fn(() => false),
}));
vi.mock("@/lib/hooks/useDaemonEvents", () => ({ useDaemonEvents: () => undefined }));

const api = vi.mocked(await import("@/lib/api/knowledge"));
const { fsApi } = await import("@/lib/api/fs");
const tauri = vi.mocked(await import("@/lib/tauri"));

const CONFLUENCE = file(`${NAME}/sources/account-core.md`, {
  kind: "source",
  title: "Account Core",
  page_type: "",
  body: [
    "# Account Core",
    "",
    "<!-- skynet-confluence-storage:v1 kind=structured-macro",
    '<ac:structured-macro ac:name="toc" />',
    "-->",
    "",
    '<table><tbody><tr><th>CMDB</th><td><a href="https://cmdb.example/x">CMDB link</a></td></tr>',
    '<tr><th>Doc</th><td><a href="../pages/gateway.md">gateway</a></td></tr></tbody></table>',
    "",
    "<script>window.hacked = true</script>",
    "",
    "See [the runbook](../../runbooks/on-call.md), [a gap](../pages/gone.md) and [far](../../../x.md).",
  ].join("\n"),
  links: [
    {
      target: "../../runbooks/on-call.md",
      path: `${OTHER.name}/on-call.md`,
      ambiguous: false,
      kind: "path",
      outside: false,
    },
    { target: "../pages/gone.md", path: null, ambiguous: false, kind: "path", outside: false },
    { target: "../../../x.md", path: null, ambiguous: false, kind: "path", outside: true },
  ],
  origin: {
    system: "confluence",
    title: "Account Core",
    url: "https://confluence.example/pages/viewpage.action?pageId=42",
    page_id: "42",
    version: "7",
    fetched_at: "2026-10-13T00:00:00+00:00",
  },
  import_report: {
    body: "converted",
    complete: false,
    missing: ["gone.png: not downloaded with the page"],
  },
});
const OPEN = `/knowledge/${UID}?file=${encodeURIComponent(CONFLUENCE.path)}`;

beforeEach(() => {
  answerFromFixtures();
  api.getFile.mockImplementation(async (path: string) =>
    path === CONFLUENCE.path ? CONFLUENCE : RELEASE,
  );
});
afterEach(() => {
  vi.clearAllMocks();
  tauri.inDesktopShell.mockReturnValue(false);
});

describe("links in an imported page", () => {
  acceptance(
    "knowledge",
    "a Confluence page is imported with its macros read and its pictures kept",
    async () => {
      renderKnowledge(OPEN);
      expect(await screen.findByRole("heading", { level: 1, name: "Account Core" })).toBeVisible();
      // The table kept as HTML is a table, its links links; the comment and the
      // script are gone.
      expect(screen.getByRole("link", { name: "CMDB link" })).toHaveAttribute(
        "href",
        "https://cmdb.example/x",
      );
      expect(screen.queryByText(/skynet-confluence-storage/)).toBeNull();
      expect(screen.queryByText(/ac:structured-macro/)).toBeNull();
      expect(document.querySelector("script")).toBeNull();
      expect((window as { hacked?: boolean }).hacked).toBeUndefined();

      // Where it came from, and that the import left something behind.
      const line = screen.getByTestId("file-line");
      expect(within(line).getByTestId("source-origin")).toHaveTextContent("From confluence");
      expect(within(line).getByRole("link", { name: "Account Core" })).toHaveAttribute(
        "href",
        CONFLUENCE.origin?.url,
      );
      expect(within(line).getByTestId("import-partial")).toHaveTextContent("Partial import");
    },
  );

  test("in the desktop app a web link opens in the default browser through the daemon", async () => {
    tauri.inDesktopShell.mockReturnValue(true);
    renderKnowledge(OPEN);
    fireEvent.click(await screen.findByRole("link", { name: "CMDB link" }));
    await waitFor(() => expect(fsApi.openUrl).toHaveBeenCalledWith("https://cmdb.example/x"));
  });

  test("in a browser a web link opens in a new tab", async () => {
    renderKnowledge(OPEN);
    const link = await screen.findByRole("link", { name: "CMDB link" });
    expect(link).toHaveAttribute("target", "_blank");
    fireEvent.click(link);
    expect(fsApi.openUrl).not.toHaveBeenCalled();
  });

  acceptance("knowledge", "a relative link is followed and checked", async () => {
    renderKnowledge(OPEN);
    // Into another collection, by that collection's uid.
    expect(await screen.findByRole("link", { name: "the runbook" })).toHaveAttribute(
      "href",
      `/knowledge/${OTHER.uid}?file=${encodeURIComponent(`${OTHER.name}/on-call.md`)}`,
    );
    // A link inside the HTML table, read relative to the file.
    expect(screen.getByRole("link", { name: "gateway" })).toHaveAttribute(
      "href",
      `/knowledge/${UID}?file=${encodeURIComponent(`${NAME}/pages/gateway.md`)}`,
    );
    expect(screen.getByText("a gap")).toHaveAttribute("data-link", "dead");
    expect(screen.getByText("far")).toHaveAttribute("data-link", "outside");
  });

  test("a source that still carries an export's markup reads converted, with a note", async () => {
    api.getFile.mockResolvedValue({
      ...CONFLUENCE,
      body: "<!-- skynet-confluence-storage:v1 kind=structured-macro\n<h1>Hidden</h1>\n-->\n",
      readable_body: "# Account Core\n\n## Kept Heading\n",
    });
    renderKnowledge(OPEN);
    expect(await screen.findByTestId("readable-body-note")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Kept Heading" })).toBeVisible();
  });
});
