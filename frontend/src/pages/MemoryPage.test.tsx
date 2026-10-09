// frontend/src/pages/MemoryPage.test.tsx — the Memory sync page in each state it renders.
//
// Spec memory "Manage memory sync in the web UI and on the command line": the header's last-synced
// clock and Sync now, a first or large sync's preview with Write and Cancel,
// the hub's projects, this machine's agents with their own curation and Curate
// now, and Undo sync… behind a confirmation naming what it removes. Nothing on
// the page edits a memory's text. The request helpers (`@/lib/api/memory`)
// are mocked; the query hooks, the query cache and the toasts are real.
import type { ReactNode } from "react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { MemorySyncState, SyncAgent } from "@/lib/api/memoryTypes";
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
  memories: 4,
  agents: { claude_code: 3, codex: 1 },
};

function state(over: Partial<MemorySyncState> = {}): MemorySyncState {
  return {
    agents: [
      agent("claude_code", {
        copies: { written: 2, edited: 1 },
        curation: { memory: "on", curation: "off" },
      }),
      agent("codex", { copies: { written: 1 } }),
    ],
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

function Where() {
  return <span data-testid="where">{useLocation().pathname}</span>;
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui: ReactNode = (
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <ToastProvider>
          <MemoryRouter initialEntries={["/memory"]}>
            <Routes>
              <Route path="/memory" element={<MemoryPage />} />
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

/** The agents table once the state has been read (its section renders while loading). */
async function agentsTable(): Promise<HTMLElement> {
  const agents = await screen.findByTestId("memory-agents");
  await within(agents).findAllByRole("button", { name: /^Curate now: / });
  return agents;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getSyncState).mockResolvedValue(state());
});

describe("MemoryPage — state", () => {
  test("header, projects and agents render from the sync state; no memory text is editable", async () => {
    renderPage();
    expect(await screen.findByTestId("memory-sync-clock")).toHaveTextContent(/^Last synced 2h ago/);
    expect(screen.getByRole("heading", { name: "Memory", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sync now" })).toBeEnabled();

    const projects = screen.getByTestId("memory-projects");
    // Global memories lead, then each project with where it lives here.
    expect(within(projects).getAllByRole("row")[1]).toHaveTextContent("Global memories");
    expect(rowOf(projects, "github.com/me/app")).toHaveTextContent("~/src/app");
    expect(rowOf(projects, "github.com/me/elsewhere")).toHaveTextContent("Not checked out here");

    const agents = await agentsTable();
    expect(rowOf(agents, "Claude Code")).toHaveTextContent("2 copies");
    expect(rowOf(agents, "Claude Code")).toHaveTextContent("1 edited by the agent");
    expect(rowOf(agents, "Codex")).toHaveTextContent("1 copy");
    // Codex is here, so its import question is asked.
    expect(
      screen.getByRole("switch", { name: /Codex imports Claude Code’s memories itself/ }),
    ).toBeInTheDocument();

    expect(screen.queryByTestId("memory-preview")).toBeNull();
    expect(screen.queryByRole("textbox", { name: /memory/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Edit/ })).toBeNull();
  });

  test("a running sync reads Syncing… and a project row opens its memories", async () => {
    vi.mocked(api.getSyncState).mockResolvedValue(state({ running: true }));
    renderPage();
    expect(await screen.findByRole("button", { name: "Syncing…" })).toBeDisabled();
    expect(screen.getByTestId("memory-sync-clock")).toHaveTextContent("Syncing…");
    fireEvent.click(rowOf(screen.getByTestId("memory-projects"), "github.com/me/app"));
    expect(await screen.findByTestId("where")).toHaveTextContent(
      "/memory/projects/github.com--me--app",
    );
  });

  test("a writer that cannot write says so in place of the copies", async () => {
    vi.mocked(api.getSyncState).mockResolvedValue(
      state({
        agents: [
          agent("codex", {
            curation: { memory: "off", curation: "off" },
            writer: { state: "off", reason: "memories are off", path: "" },
          }),
        ],
      }),
    );
    renderPage();
    const row = rowOf(await agentsTable(), "Codex");
    expect(row).toHaveTextContent("Nothing written: its memory is off");
    expect(row).toHaveTextContent("memories are off");
    expect(row).toHaveTextContent(/memories = true under \[features\]/);
    // Its own memory is off: there is nothing to curate.
    expect(within(row).getByRole("button", { name: "Curate now: Codex" })).toBeDisabled();
  });

  test("no agent to sync: the page points to Agents and offers no Sync now", async () => {
    vi.mocked(api.getSyncState).mockResolvedValue(state({ agents: [] }));
    renderPage();
    expect(await screen.findByText("No agent to sync")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Agents" })).toHaveAttribute("href", "/agents");
    expect(screen.queryByRole("button", { name: "Sync now" })).toBeNull();
    expect(screen.queryByTestId("memory-projects")).toBeNull();
  });

  test("a failed read says so and retries", async () => {
    vi.mocked(api.getSyncState).mockRejectedValueOnce(new Error("boom"));
    renderPage();
    expect(await screen.findByText("Couldn't load memory sync")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByTestId("memory-projects")).toBeInTheDocument();
  });

  test("sources the last sync could not read, and withheld memories, are named", async () => {
    vi.mocked(api.getSyncState).mockResolvedValue(
      state({
        last_report: {
          failures: [{ agent: "codex", path: "/Users/me/.codex/memories", reason: "unreadable" }],
          withheld: [{ agent: "claude_code", path: "/m/token.md", reason: "secret" }],
        },
      }),
    );
    renderPage();
    const problems = await screen.findByTestId("memory-sync-problems");
    expect(problems).toHaveTextContent("Couldn't read 1 memory source");
    expect(problems).toHaveTextContent(
      "1 memory looks like it holds a secret and was not published",
    );
  });
});

describe("MemoryPage — preview", () => {
  const PREVIEW = {
    created_at: new Date().toISOString(),
    copies: 3,
    rows: [
      { agent: "codex", project: "github.com/me/app", write: 2, update: 1, remove: 0 },
      { agent: "claude_code", project: "", write: 0, update: 0, remove: 1 },
    ],
  };

  acceptance("memory", "the first sync waits for the person", async () => {
    vi.mocked(api.getSyncState).mockResolvedValue(state({ preview: PREVIEW }));
    vi.mocked(api.writePreview).mockResolvedValue({
      summary: { published: 0, written: 2, updated: 1, removed: 0 },
      details: {},
    });
    renderPage();
    const panel = await screen.findByTestId("memory-preview");
    expect(panel).toHaveTextContent("Review 3 copies before they are written");
    expect(rowOf(panel, "github.com/me/app")).toHaveTextContent(/Codex.*github\.com\/me\/app21–/);
    expect(rowOf(panel, "Global memories")).toHaveTextContent("Claude Code");
    expect(api.writePreview).not.toHaveBeenCalled();

    vi.mocked(api.getSyncState).mockResolvedValue(state());
    fireEvent.click(within(panel).getByRole("button", { name: "Write" }));
    await waitFor(() => expect(api.writePreview).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("Memory synced")).toBeInTheDocument();
    expect(api.cancelPreview).not.toHaveBeenCalled();
    // The page re-reads the state: the preview is gone.
    await waitFor(() => expect(screen.queryByTestId("memory-preview")).toBeNull());
  });

  test("Cancel drops the preview and writes nothing", async () => {
    vi.mocked(api.getSyncState).mockResolvedValue(state({ preview: PREVIEW }));
    vi.mocked(api.cancelPreview).mockResolvedValue(undefined);
    renderPage();
    const panel = await screen.findByTestId("memory-preview");
    vi.mocked(api.getSyncState).mockResolvedValue(state());
    fireEvent.click(within(panel).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(api.cancelPreview).toHaveBeenCalledTimes(1));
    expect(api.writePreview).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByTestId("memory-preview")).toBeNull());
  });

  test("a preview row opens that project's memories", async () => {
    vi.mocked(api.getSyncState).mockResolvedValue(state({ preview: PREVIEW }));
    renderPage();
    const panel = await screen.findByTestId("memory-preview");
    fireEvent.click(rowOf(panel, "Global memories"));
    expect(await screen.findByTestId("where")).toHaveTextContent("/memory/global");
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
    expect(dialog).toHaveTextContent("2 copies in Claude Code · 1 copy in Codex");
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

describe("MemoryPage — agents' own curation", () => {
  acceptance("memory", "an agent's curation state is shown", async () => {
    renderPage();
    const agents = await agentsTable();
    const claude = rowOf(agents, "Claude Code");
    expect(claude).toHaveTextContent("Auto memory on");
    expect(claude).toHaveTextContent("Auto Dream off");
    expect(claude).toHaveTextContent("Check Auto Dream in Claude Code’s /memory.");
    const codex = rowOf(agents, "Codex");
    expect(codex).toHaveTextContent("Memories on");
    expect(codex).not.toHaveTextContent("Turn memories on");
  });

  test("Curate now starts that agent and says so", async () => {
    vi.mocked(api.curate).mockResolvedValue({ started: true });
    renderPage();
    const agents = await agentsTable();
    fireEvent.click(within(agents).getByRole("button", { name: "Curate now: Claude Code" }));
    await waitFor(() => expect(api.curate).toHaveBeenCalledWith("claude_code"));
    expect(await screen.findByText("Claude Code is curating its memory")).toBeInTheDocument();
  });

  test("an agent that could not start is said to have failed", async () => {
    vi.mocked(api.curate).mockResolvedValue({ started: false });
    renderPage();
    const agents = await agentsTable();
    fireEvent.click(within(agents).getByRole("button", { name: "Curate now: Codex" }));
    expect(await screen.findByText("Couldn't start Codex")).toBeInTheDocument();
  });

  test("Codex's own import is a switch saved as it changes", async () => {
    vi.mocked(api.setCodexImport).mockResolvedValue(undefined);
    renderPage();
    fireEvent.click(
      await screen.findByRole("switch", { name: /Codex imports Claude Code’s memories itself/ }),
    );
    await waitFor(() => expect(api.setCodexImport).toHaveBeenCalledWith(true));
  });
});
