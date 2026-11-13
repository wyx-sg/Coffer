// frontend/src/components/agents/AgentMemorySync.test.tsx
//
// The Memory sync section on an agent's Memory tab (spec memory "Show on each
// agent what Coffer wrote into it"): the copies Coffer wrote into it, or why
// it cannot write there and how to turn the agent's own memory on, Codex's
// import switch, and Open Memory narrowed to the agent. Nothing about the
// agent's own curation. Shown only while the memory feature is on. The request
// helpers are mocked; the query hooks and toasts are real.
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
}));
const api = await import("@/lib/api/memory");

const feature = { on: true };
vi.mock("@/lib/hooks/useFeatures", () => ({ useFeatureEnabled: () => feature.on }));

function agent(type: string, over: Partial<SyncAgent> = {}): SyncAgent {
  return {
    agent: type,
    agent_type: type,
    copies: { written: 0 },
    writer: { state: "ok", reason: "", path: "" },
    locations: [],
    ...over,
  };
}

function state(agents: SyncAgent[]): MemorySyncState {
  return {
    agents,
    codex_imports_claude: null,
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
    state([agent("claude_code"), agent("codex", { copies: { written: 2, edited: 1 } })]),
  );
});

describe("AgentMemorySync", () => {
  acceptance("memory", "an agent's tab shows what Coffer wrote into it", async () => {
    renderSection("codex");
    const codex = await screen.findByTestId("memory-sync-section");
    expect(codex).toHaveTextContent("2 copies");
    expect(codex).toHaveTextContent("1 edited by the agent");
    expect(within(codex).getByRole("link", { name: /Open Memory/ })).toHaveAttribute(
      "href",
      "/memory?source=codex",
    );
    expect(within(codex).queryByRole("button")).toBeNull();
    expect(codex).not.toHaveTextContent(/curat|consolidat/i);
  });

  test("Claude Code says its memories arrive as text and offers no curation", async () => {
    renderSection("claude_code");
    const section = await screen.findByTestId("memory-sync-section");
    expect(section).toHaveTextContent("As text in each project's MEMORY.md");
    expect(section).not.toHaveTextContent("rules file");
    expect(section).not.toHaveTextContent(/Auto Dream|Curate/);
    expect(within(section).queryByRole("button")).toBeNull();
    // Claude Code is not asked Codex's import question.
    expect(screen.queryByRole("switch")).toBeNull();
  });

  test("Codex's section asks its import question", async () => {
    vi.mocked(api.setCodexImport).mockResolvedValue(undefined);
    renderSection("codex");
    const section = await screen.findByTestId("memory-sync-section");
    fireEvent.click(
      within(section).getByRole("switch", {
        name: /Codex imports Claude Code’s memories itself/,
      }),
    );
    await waitFor(() => expect(api.setCodexImport).toHaveBeenCalledWith(true));
  });

  test("a writer whose agent has memory off says so and how to turn it on", async () => {
    vi.mocked(api.getSyncState).mockResolvedValue(
      state([agent("codex", { writer: { state: "off", reason: "memories are off", path: "" } })]),
    );
    renderSection("codex");
    const section = await screen.findByTestId("memory-sync-section");
    expect(section).toHaveTextContent("Nothing written: its memory is off");
    expect(section).toHaveTextContent("memories are off");
    expect(section).toHaveTextContent(/memories = true under \[features\]/);
  });

  test("Codex shows each memory folder, a newer one it cannot write into among them", async () => {
    const blocked = {
      state: "unrecognised",
      reason: "a Codex memory folder newer than this Coffer knows: update Coffer",
      path: "/Users/me/.codex/memories_v3",
    };
    vi.mocked(api.getSyncState).mockResolvedValue(
      state([
        agent("codex", {
          copies: { written: 6 },
          writer: blocked,
          locations: [
            {
              name: "",
              path: "/Users/me/.codex/memories",
              writer: { state: "ok", reason: "", path: "" },
              copies: { written: 3 },
            },
            {
              name: "memories_v2",
              path: "/Users/me/.codex/memories_v2",
              writer: { state: "ok", reason: "", path: "" },
              copies: { written: 3 },
            },
            { name: "memories_v3", path: blocked.path, writer: blocked, copies: {} },
          ],
        }),
      ]),
    );
    renderSection("codex");
    const list = await screen.findByTestId("memory-sync-locations");
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(rows[1]).toHaveTextContent("memories_v2");
    expect(rows[1]).toHaveTextContent("3");
    expect(rows[2]).toHaveTextContent("newer than this Coffer knows");
  });

  test("nothing shows while the memory feature is off", async () => {
    feature.on = false;
    renderSection("claude_code");
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByTestId("memory-sync-section")).toBeNull();
  });
});
