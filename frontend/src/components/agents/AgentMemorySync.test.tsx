// frontend/src/components/agents/AgentMemorySync.test.tsx
//
// The Memory sync section on an agent's Memory tab (spec memory "Show each
// agent's own curation and ask it to curate now"): the agent's own memory and
// curation switches with a hint when off, the copies Coffer wrote into it,
// Curate now, Codex's import switch, and Open Memory narrowed to the agent.
// Shown only while the memory feature is on. The request helpers are mocked;
// the query hooks and toasts are real.
import type { ReactNode } from "react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { MemorySyncState, SyncAgent } from "@/lib/api/memoryTypes";
import { acceptance } from "@/test/acceptance";

import { AgentMemorySync } from "./AgentMemorySync";

vi.mock("@/lib/api/memory", () => ({
  getSyncState: vi.fn(),
  setCodexImport: vi.fn(),
  curate: vi.fn(),
}));
const api = await import("@/lib/api/memory");

const feature = { on: true };
vi.mock("@/lib/hooks/useFeatures", () => ({ useFeatureEnabled: () => feature.on }));

function agent(type: string, over: Partial<SyncAgent> = {}): SyncAgent {
  return {
    agent: type,
    agent_type: type,
    copies: { written: 0 },
    curation: { memory: "on", curation: "on" },
    writer: { state: "ok", reason: "", path: "" },
    ...over,
  };
}

function state(agents: SyncAgent[]): MemorySyncState {
  return {
    agents,
    codex_imports_claude: null,
    global_memories: 0,
    last_report: {},
    last_synced_at: "",
    machine: "m",
    preview: null,
    projects: [],
    running: false,
  };
}

function renderSection(type: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui: ReactNode = (
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <ToastProvider>
          <MemoryRouter>
            <AgentMemorySync agentType={type} />
          </MemoryRouter>
        </ToastProvider>
      </TooltipProvider>
    </QueryClientProvider>
  );
  return render(ui);
}

beforeEach(() => {
  vi.clearAllMocks();
  feature.on = true;
  vi.mocked(api.getSyncState).mockResolvedValue(
    state([
      agent("claude_code", {
        copies: { written: 2, edited: 1 },
        curation: { memory: "on", curation: "off" },
      }),
      agent("codex", { copies: { written: 1 } }),
    ]),
  );
});

describe("AgentMemorySync", () => {
  acceptance("memory", "an agent's curation state is shown", async () => {
    renderSection("claude_code");
    const section = await screen.findByTestId("memory-sync-section");
    expect(section).toHaveTextContent("Auto memory on");
    expect(section).toHaveTextContent("Auto Dream off");
    expect(section).toHaveTextContent("Check Auto Dream in Claude Code’s /memory.");
    expect(section).toHaveTextContent("2 copies");
    expect(section).toHaveTextContent("1 edited by the agent");
    expect(within(section).getByRole("link", { name: /Open Memory/ })).toHaveAttribute(
      "href",
      "/memory?source=claude_code",
    );
    // Claude Code is not asked Codex's import question.
    expect(screen.queryByRole("switch")).toBeNull();
  });

  test("Codex's section says its memories are on and asks its import question", async () => {
    vi.mocked(api.setCodexImport).mockResolvedValue(undefined);
    renderSection("codex");
    const section = await screen.findByTestId("memory-sync-section");
    expect(section).toHaveTextContent("Memories on");
    expect(section).not.toHaveTextContent("Turn memories on");
    fireEvent.click(
      within(section).getByRole("switch", {
        name: /Codex imports Claude Code’s memories itself/,
      }),
    );
    await waitFor(() => expect(api.setCodexImport).toHaveBeenCalledWith(true));
  });

  test("Curate now starts that agent and says so", async () => {
    vi.mocked(api.curate).mockResolvedValue({ started: true });
    renderSection("claude_code");
    fireEvent.click(await screen.findByRole("button", { name: "Curate now: Claude Code" }));
    await waitFor(() => expect(api.curate).toHaveBeenCalledWith("claude_code"));
    expect(await screen.findByText("Claude Code is curating its memory")).toBeInTheDocument();
  });

  test("an agent that could not start is said to have failed", async () => {
    vi.mocked(api.curate).mockResolvedValue({ started: false });
    renderSection("codex");
    fireEvent.click(await screen.findByRole("button", { name: "Curate now: Codex" }));
    expect(await screen.findByText("Couldn't start Codex")).toBeInTheDocument();
  });

  test("a writer that cannot write says so, and there is nothing to curate", async () => {
    vi.mocked(api.getSyncState).mockResolvedValue(
      state([
        agent("codex", {
          curation: { memory: "off", curation: "off" },
          writer: { state: "off", reason: "memories are off", path: "" },
        }),
      ]),
    );
    renderSection("codex");
    const section = await screen.findByTestId("memory-sync-section");
    expect(section).toHaveTextContent("Nothing written: its memory is off");
    expect(section).toHaveTextContent("memories are off");
    expect(section).toHaveTextContent(/memories = true under \[features\]/);
    expect(within(section).getByRole("button", { name: "Curate now: Codex" })).toBeDisabled();
  });

  test("nothing shows while the memory feature is off", async () => {
    feature.on = false;
    renderSection("claude_code");
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByTestId("memory-sync-section")).toBeNull();
  });
});
