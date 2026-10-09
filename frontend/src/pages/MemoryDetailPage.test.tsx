// frontend/src/pages/MemoryDetailPage.test.tsx — one project's memories and where each was written.
//
// Spec memory "Manage memory sync in the web UI": choosing a project lists its
// memories with their origin agent and machine and, per agent on this machine,
// what became of the copy — the origin itself, written, in the rules file,
// waiting for the next sync, held back, left to Codex's own import, or edited
// or removed by the agent. Global memories have their own address. The request
// helpers (`@/lib/api/memory`) are mocked; the query hooks are real.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { HubEntry, MemorySyncState } from "@/lib/api/memoryTypes";
import { acceptance } from "@/test/acceptance";

import { MemoryDetailPage } from "./MemoryDetailPage";

vi.mock("@/lib/api/memory", () => ({
  getSyncState: vi.fn(),
  listEntries: vi.fn(),
}));
const api = await import("@/lib/api/memory");

const AGENT = {
  copies: { written: 0 },
  curation: { memory: "on", curation: "on" },
  writer: { state: "ok", reason: "", path: "" },
};

const STATE: MemorySyncState = {
  agents: [
    { ...AGENT, agent: "codex", agent_type: "codex" },
    { ...AGENT, agent: "claude-code", agent_type: "claude_code" },
  ],
  codex_imports_claude: null,
  global_memories: 3,
  last_report: {},
  last_synced_at: "",
  machine: "mac-mini",
  preview: null,
  projects: [
    {
      key: "github.com/me/app",
      folder: "github.com--me--app",
      checked_out: "/Users/me/src/app",
      memories: 8,
      agents: { claude_code: 5, codex: 3 },
    },
    {
      key: "github.com/me/elsewhere",
      folder: "github.com--me--elsewhere",
      checked_out: null,
      memories: 1,
      agents: { codex: 1 },
    },
  ],
  running: false,
};

function entry(id: string, over: Partial<HubEntry> = {}): HubEntry {
  return {
    id,
    title: id,
    description: "",
    type: "feedback",
    origin_agent: "codex",
    origin_machine: "laptop",
    project: "github.com/me/app",
    copies: {},
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
    ...over,
  };
}

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/memory/global" element={<MemoryDetailPage />} />
            <Route path="/memory/projects/:folder" element={<MemoryDetailPage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

const rowOf = async (title: string) =>
  (await screen.findByText(title)).closest("tr") as HTMLElement;

/** The cell under the "In <agent>" column of a row. */
function copyCell(row: HTMLElement, agent: string): HTMLElement {
  const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
  const index = headers.indexOf(`In ${agent}`);
  expect(index).toBeGreaterThan(-1);
  return within(row).getAllByRole("cell")[index];
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getSyncState).mockResolvedValue(STATE);
});

describe("MemoryDetailPage", () => {
  acceptance("memory", "a project's memories show where each was written", async () => {
    vi.mocked(api.listEntries).mockResolvedValue({
      project: "github.com/me/app",
      entries: [
        entry("Prefers pnpm", { copies: { codex: "origin", claude_code: "written" } }),
        entry("Old build notes", { copies: { codex: "origin", claude_code: "removed" } }),
      ],
    });
    renderAt("/memory/projects/github.com--me--app");
    const written = await rowOf("Prefers pnpm");
    expect(api.listEntries).toHaveBeenCalledWith("github.com/me/app");
    // The origin agent and machine.
    expect(within(written).getByRole("img", { name: /Codex/ })).toBeInTheDocument();
    expect(written).toHaveTextContent("laptop");
    expect(copyCell(written, "Claude Code")).toHaveTextContent("Written");
    expect(copyCell(written, "Codex")).toHaveTextContent("Its own");
    const removed = await rowOf("Old build notes");
    expect(copyCell(removed, "Claude Code")).toHaveTextContent("Removed by agent");

    // The header: the project's key, where it lives here, how many memories.
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("github.com/me/app");
    expect(screen.getByText("~/src/app")).toBeInTheDocument();
    expect(screen.getByText(/8 memories/)).toBeInTheDocument();
  });

  test("every copy state reads as its own word", async () => {
    const states = [
      ["origin", "Its own"],
      ["written", "Written"],
      ["held_back", "Held back"],
      ["deferred", "Codex imports it"],
      ["rules", "In rules file"],
      ["pending", "Next sync"],
      ["edited", "Edited by agent"],
      ["removed", "Removed by agent"],
    ] as const;
    vi.mocked(api.listEntries).mockResolvedValue({
      project: "github.com/me/app",
      entries: states.map(([state]) =>
        entry(`m-${state}`, { origin_machine: "mac-mini", copies: { claude_code: state } }),
      ),
    });
    renderAt("/memory/projects/github.com--me--app");
    for (const [state, word] of states) {
      const row = await rowOf(`m-${state}`);
      expect(copyCell(row, "Claude Code")).toHaveTextContent(word);
      // This machine's own memories read "This machine", not its id.
      expect(row).toHaveTextContent("This machine");
    }
    // Read only: nothing on the page edits a memory.
    expect(screen.queryByRole("button", { name: /^Edit/ })).toBeNull();
  });

  test("a project not checked out here says its memories wait in the hub", async () => {
    vi.mocked(api.listEntries).mockResolvedValue({
      project: "github.com/me/elsewhere",
      entries: [entry("Deploy on Fridays", { copies: { claude_code: "held_back" } })],
    });
    renderAt("/memory/projects/github.com--me--elsewhere");
    expect(
      await screen.findByText(/Not checked out on this machine: its memories wait in the hub/),
    ).toBeInTheDocument();
    expect(copyCell(await rowOf("Deploy on Fridays"), "Claude Code")).toHaveTextContent(
      "Held back",
    );
  });

  test('global memories are asked for as project ""', async () => {
    vi.mocked(api.listEntries).mockResolvedValue({ project: "", entries: [] });
    renderAt("/memory/global");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Global memories" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Written into every agent on every machine · 3 memories/),
    ).toBeInTheDocument();
    await waitFor(() => expect(api.listEntries).toHaveBeenCalledWith(""));
  });

  test("an unknown project is not found and lists nothing", async () => {
    renderAt("/memory/projects/nope");
    expect(await screen.findByRole("link", { name: /back/i })).toHaveAttribute("href", "/memory");
    expect(api.listEntries).not.toHaveBeenCalled();
  });
});
