// frontend/src/pages/MemoryPage.test.tsx — the Memory page in each state it renders.
//
// Spec memory "Manage memory sync in the web UI and on the command line": the
// header's last-synced clock and Sync now, the scopes beside the open scope's
// memories (a copy state only when it is worth a look), a memory opening in the
// drawer with where each agent holds it and its text, the one banner and drawer
// for what needs the person (a preview folded to counts, unreadable sources,
// withheld memories, an agent Coffer cannot write into), and Undo sync… behind
// a confirmation. Nothing on the page edits a memory's text. The request
// helpers (`@/lib/api/memory`) are mocked; the query hooks, the query cache
// and the toasts are real.
import type { ReactNode } from "react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { HubEntry, MemorySyncState, SyncAgent } from "@/lib/api/memoryTypes";
import { acceptance } from "@/test/acceptance";

import { MemoryPage } from "./MemoryPage";

vi.mock("@/lib/api/memory", () => ({
  getSyncState: vi.fn(),
  runSync: vi.fn(),
  writePreview: vi.fn(),
  cancelPreview: vi.fn(),
  undoSync: vi.fn(),
  setCodexImport: vi.fn(),
  listEntries: vi.fn(),
  getEntry: vi.fn(),
  curate: vi.fn(),
}));
const api = await import("@/lib/api/memory");

vi.mock("@/lib/hooks/useInternalEngine", () => ({
  useInternalEngineConfig: () => ({ data: undefined }),
  useSetUpkeep: () => ({ isPending: false, mutate: vi.fn() }),
}));

const HOUR = 3600_000;

function agent(type: string, over: Partial<SyncAgent> = {}): SyncAgent {
  return {
    agent: type === "codex" ? "codex" : "claude-code",
    agent_type: type,
    copies: { written: 0 },
    curation: { memory: "on", curation: "on" },
    writer: { state: "ok", reason: "", path: "" },
    ...over,
  };
}

const PROJECT = {
  key: "github.com/me/app",
  folder: "github.com--me--app",
  checked_out: "/Users/me/src/app",
  memories: 2,
  agents: { claude_code: 1, codex: 1 },
};

function state(over: Partial<MemorySyncState> = {}): MemorySyncState {
  return {
    agents: [agent("claude_code", { copies: { written: 2, edited: 1 } }), agent("codex")],
    codex_imports_claude: null,
    global_memories: 2,
    last_report: {},
    last_synced_at: new Date(Date.now() - 2 * HOUR).toISOString(),
    machine: "mac-mini",
    preview: null,
    projects: [
      PROJECT,
      {
        key: "github.com/me/elsewhere",
        folder: "github.com--me--elsewhere",
        checked_out: null,
        memories: 1,
        agents: { codex: 1 },
      },
    ],
    running: false,
    ...over,
  };
}

function entry(over: Partial<HubEntry>): HubEntry {
  return {
    id: "e1",
    title: "Run make verify",
    description: "Before every push",
    type: "feedback",
    project: PROJECT.key,
    origin_agent: "claude_code",
    origin_machine: "mac-mini",
    created_at: new Date(Date.now() - 3 * HOUR).toISOString(),
    updated_at: new Date(Date.now() - HOUR).toISOString(),
    copies: { claude_code: "origin", codex: "written" },
    ...over,
  };
}

const ENTRIES = [
  entry({}),
  entry({
    id: "e2",
    title: "Use uv",
    description: "Not pip",
    origin_agent: "codex",
    origin_machine: "work-imac",
    copies: { claude_code: "removed", codex: "written" },
  }),
];

function Where() {
  const { pathname, search } = useLocation();
  return <span data-testid="where">{pathname + search}</span>;
}

function renderPage(at = "/memory") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui: ReactNode = (
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <ToastProvider>
          <MemoryRouter initialEntries={[at]}>
            <Routes>
              <Route
                path="/memory"
                element={
                  <>
                    <MemoryPage />
                    <Where />
                  </>
                }
              />
              <Route path="*" element={<Where />} />
            </Routes>
          </MemoryRouter>
        </ToastProvider>
      </TooltipProvider>
    </QueryClientProvider>
  );
  return render(ui);
}

const rowOf = (scope: HTMLElement, text: string) =>
  within(scope)
    .getAllByRole("row")
    .find((r) => r.textContent?.includes(text)) as HTMLElement;

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getSyncState).mockResolvedValue(state());
  vi.mocked(api.listEntries).mockResolvedValue({ project: "", entries: ENTRIES });
});

describe("MemoryPage — scopes and memories", () => {
  test("header, scopes and the default scope render; no memory text is editable", async () => {
    renderPage();
    expect(await screen.findByTestId("memory-sync-clock")).toHaveTextContent(/^Last synced 2h ago/);
    expect(screen.getByRole("heading", { name: "Memory", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sync now" })).toBeEnabled();

    const scopes = screen.getByRole("navigation", { name: "Memory scopes" });
    const links = within(scopes).getAllByRole("link");
    // Global memories lead, then projects by short name, the one not here apart.
    expect(links.map((l) => l.textContent)).toEqual(["Global memories2", "app2", "elsewhere1"]);
    expect(within(scopes).getByText("Not checked out here")).toBeInTheDocument();
    // With global memories, the page opens on them.
    await waitFor(() => expect(api.listEntries).toHaveBeenCalledWith(""));
    expect(links[0]).toHaveAttribute("aria-current", "page");

    // The page lists no agent and edits no memory.
    expect(screen.queryByTestId("memory-agents")).toBeNull();
    expect(screen.queryByTestId("memory-needs-you")).toBeNull();
    expect(screen.queryByRole("textbox", { name: /memory text/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Edit/ })).toBeNull();
  });

  acceptance("memory", "a project's memories show where each was written", async () => {
    renderPage(`/memory?scope=${PROJECT.folder}`);
    const list = await screen.findByTestId("memory-list");
    expect(list).toHaveTextContent("github.com/me/app");
    expect(list).toHaveTextContent("~/src/app");
    await waitFor(() => expect(api.listEntries).toHaveBeenCalledWith(PROJECT.key));
    const own = rowOf(list, "Run make verify");
    expect(own).toHaveTextContent("This machine");
    // A written copy says nothing; a copy the agent's curation removed says so.
    expect(own).not.toHaveTextContent(/Written|Removed/);
    const other = rowOf(list, "Use uv");
    expect(other).toHaveTextContent("work-imac");
    expect(other).toHaveTextContent("Removed by Claude Code");
  });

  test("a project not checked out here says when its memories are written", async () => {
    renderPage("/memory?scope=github.com--me--elsewhere");
    const list = await screen.findByTestId("memory-list");
    expect(list).toHaveTextContent("Not checked out on this machine: written here once it is");
  });

  test("a scope link keeps the page and switches the list", async () => {
    renderPage();
    const scopes = await screen.findByRole("navigation", { name: "Memory scopes" });
    fireEvent.click(await within(scopes).findByRole("link", { name: /^app/ }));
    await waitFor(() =>
      expect(screen.getByTestId("where")).toHaveTextContent(`/memory?scope=${PROJECT.folder}`),
    );
    await waitFor(() => expect(api.listEntries).toHaveBeenCalledWith(PROJECT.key));
  });

  test("a memory opens in the drawer with where each agent holds it, then its text", async () => {
    vi.mocked(api.getEntry).mockResolvedValue({
      ...ENTRIES[0],
      body: "# Run make verify\n\nThe pre-push check runs **ruff**.",
      copies: [
        { agent_type: "claude_code", state: "origin", path: "/Users/me/.claude/m/verify.md" },
        { agent_type: "codex", state: "written", path: "/Users/me/.codex/x/verify.md" },
      ],
    });
    renderPage(`/memory?scope=${PROJECT.folder}`);
    const list = await screen.findByTestId("memory-list");
    fireEvent.click(await within(list).findByText("Run make verify"));
    const drawer = await screen.findByRole("dialog");
    await waitFor(() => expect(api.getEntry).toHaveBeenCalledWith("e1"));
    const locations = await within(drawer).findByTestId("memory-locations");
    expect(locations).toHaveTextContent(/Claude Code.*Its own.*~\/\.claude\/m\/verify\.md/);
    expect(locations).toHaveTextContent(/Codex.*Written.*~\/\.codex\/x\/verify\.md/);
    expect(within(locations).getAllByRole("button", { name: "Reveal in Finder" })).toHaveLength(2);
    // The text follows, without a heading that only repeats the title.
    expect(drawer).toHaveTextContent("The pre-push check runs ruff.");
    expect(within(drawer).queryByRole("heading", { name: "Run make verify", level: 1 })).toBeNull();
    expect(screen.getByTestId("where")).toHaveTextContent("memory=e1");
    // The drawer maximizes and steps to the next memory.
    expect(within(drawer).getByRole("button", { name: "Maximize" })).toBeInTheDocument();
    fireEvent.click(within(drawer).getByRole("button", { name: "Next" }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("memory=e2"));
  });

  test("an old project address opens that scope", async () => {
    // The redirect itself is the router's; the page reads the scope it lands on.
    renderPage("/memory?scope=global");
    await waitFor(() => expect(api.listEntries).toHaveBeenCalledWith(""));
  });

  test("an agent's Memory tab link filters the list to that agent", async () => {
    renderPage(`/memory?scope=${PROJECT.folder}&source=codex`);
    const list = await screen.findByTestId("memory-list");
    await within(list).findByText("Use uv");
    expect(within(list).queryByText("Run make verify")).toBeNull();
  });

  test("a running sync reads Syncing…", async () => {
    vi.mocked(api.getSyncState).mockResolvedValue(state({ running: true }));
    renderPage();
    expect(await screen.findByRole("button", { name: "Syncing…" })).toBeDisabled();
    expect(screen.getByTestId("memory-sync-clock")).toHaveTextContent("Syncing…");
  });

  test("no agent to sync: the page points to Agents and offers no Sync now", async () => {
    vi.mocked(api.getSyncState).mockResolvedValue(state({ agents: [] }));
    renderPage();
    expect(await screen.findByText("No agent to sync")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Agents" })).toHaveAttribute("href", "/agents");
    expect(screen.queryByRole("button", { name: "Sync now" })).toBeNull();
    expect(screen.queryByRole("navigation", { name: "Memory scopes" })).toBeNull();
  });

  test("a failed read says so and retries", async () => {
    vi.mocked(api.getSyncState).mockRejectedValueOnce(new Error("boom"));
    renderPage();
    expect(await screen.findByText("Couldn't load memory sync")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("navigation", { name: "Memory scopes" })).toBeInTheDocument();
  });
});

describe("MemoryPage — what needs the person", () => {
  const PREVIEW = {
    created_at: new Date().toISOString(),
    copies: 4,
    rows: [
      {
        agent: "codex",
        project: "github.com/me/app",
        write: 2,
        update: 1,
        remove: 0,
        items: [
          { entry: "e1", title: "Run make verify", action: "write" },
          { entry: "e3", title: "Docs in two languages", action: "write" },
          { entry: "e4", title: "Release key", action: "update" },
        ],
      },
      {
        agent: "claude_code",
        project: "",
        write: 0,
        update: 0,
        remove: 1,
        items: [{ entry: "e9", title: "coffer_old-note", action: "remove" }],
      },
    ],
  };

  async function openNeedsYou(): Promise<HTMLElement> {
    const banner = await screen.findByTestId("memory-needs-you");
    fireEvent.click(within(banner).getByRole("button", { name: "Review" }));
    return screen.findByRole("dialog");
  }

  acceptance("memory", "the first sync waits for the person", async () => {
    vi.mocked(api.getSyncState).mockResolvedValue(state({ preview: PREVIEW }));
    vi.mocked(api.writePreview).mockResolvedValue({
      summary: { published: 0, written: 2, updated: 1, removed: 1 },
      details: {},
    });
    renderPage();
    const banner = await screen.findByTestId("memory-needs-you");
    expect(banner).toHaveTextContent("4 copies wait for you to write them");
    const drawer = await openNeedsYou();
    expect(drawer).toHaveTextContent("Review 4 copies before they are written");
    // Each group is folded to its counts; one that removes anything starts open.
    const groups = drawer.querySelectorAll("details");
    expect(groups).toHaveLength(2);
    const [app, global] = [...groups];
    expect(app.querySelector("summary")).toHaveTextContent(/Codex.*app.*2 new · 1 updated/);
    expect(app).not.toHaveAttribute("open");
    expect(global.querySelector("summary")).toHaveTextContent(/Global memories.*1 removed/);
    expect(global).toHaveAttribute("open");
    expect(global).toHaveTextContent("Removecoffer_old-note");
    expect(api.writePreview).not.toHaveBeenCalled();

    vi.mocked(api.getSyncState).mockResolvedValue(state());
    fireEvent.click(within(drawer).getByRole("button", { name: "Write 4 copies" }));
    await waitFor(() => expect(api.writePreview).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("Memory synced")).toBeInTheDocument();
    expect(api.cancelPreview).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByTestId("memory-needs-you")).toBeNull());
  });

  test("Cancel drops the preview and writes nothing", async () => {
    vi.mocked(api.getSyncState).mockResolvedValue(state({ preview: PREVIEW }));
    vi.mocked(api.cancelPreview).mockResolvedValue(undefined);
    renderPage();
    const drawer = await openNeedsYou();
    vi.mocked(api.getSyncState).mockResolvedValue(state());
    fireEvent.click(within(drawer).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(api.cancelPreview).toHaveBeenCalledTimes(1));
    expect(api.writePreview).not.toHaveBeenCalled();
  });

  test("a memory in the preview opens in the memory drawer", async () => {
    vi.mocked(api.getSyncState).mockResolvedValue(state({ preview: PREVIEW }));
    renderPage();
    const drawer = await openNeedsYou();
    fireEvent.click(within(drawer).getByRole("button", { name: "Run make verify" }));
    await waitFor(() =>
      expect(screen.getByTestId("where")).toHaveTextContent(
        `/memory?scope=${PROJECT.folder}&memory=e1`,
      ),
    );
  });

  test("unreadable sources, withheld memories and an agent Coffer cannot write into", async () => {
    vi.mocked(api.getSyncState).mockResolvedValue(
      state({
        agents: [
          agent("claude_code"),
          agent("codex", {
            curation: { memory: "off", curation: "off" },
            writer: { state: "off", reason: "", path: "" },
          }),
        ],
        last_report: {
          failures: [
            { agent: "codex", path: "/Users/me/.codex/memories/MEMORY.md", reason: "unreadable" },
          ],
          withheld: [{ agent: "claude_code", path: "/m/token.md", reason: "secret" }],
        },
      }),
    );
    renderPage();
    const banner = await screen.findByTestId("memory-needs-you");
    expect(banner).toHaveTextContent("3 things need you");
    expect(banner).toHaveTextContent(
      "1 source could not be read · 1 memory looked like a secret · 1 agent cannot be written into",
    );
    const drawer = await openNeedsYou();
    expect(drawer).toHaveTextContent("Couldn't read 1 memory source");
    expect(drawer).toHaveTextContent("unreadable");
    expect(drawer).toHaveTextContent("1 memory looks like it holds a secret and was not published");
    // The withheld memory names its file, never its text.
    expect(drawer).not.toHaveTextContent("secret)");
    expect(drawer).toHaveTextContent("Codex's own memory is off, so nothing is written into it");
    expect(within(drawer).getByRole("link", { name: /Open Codex's memory/ })).toHaveAttribute(
      "href",
      "/agents/codex/memory",
    );
  });
});

describe("MemoryPage — undo", () => {
  acceptance("memory", "undo removes Coffer's copies and nothing else", async () => {
    vi.mocked(api.undoSync).mockResolvedValue({ summary: { removed: 3 }, details: {} });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "More memory actions" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /Undo sync…/ }));
    const dialog = await screen.findByRole("dialog", { name: "Undo memory sync on this machine?" });
    // The confirmation names what it removes, what it turns off and what it keeps.
    expect(dialog).toHaveTextContent("2 copies in Claude Code · 0 copies in Codex");
    expect(dialog).toHaveTextContent("Coffer’s block in each MEMORY.md");
    expect(dialog).toHaveTextContent("Automatic sync");
    expect(dialog).toHaveTextContent("every copy an agent edited");
    expect(api.undoSync).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole("button", { name: "Undo sync" }));
    await waitFor(() => expect(api.undoSync).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("Removed 3 copies. Automatic sync is off.")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  test("a failed undo stays in the dialog with its error", async () => {
    vi.mocked(api.undoSync).mockRejectedValue(new Error("disk full"));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "More memory actions" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /Undo sync…/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Undo sync" }));
    expect(await within(dialog).findByText("Couldn't undo the sync")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
