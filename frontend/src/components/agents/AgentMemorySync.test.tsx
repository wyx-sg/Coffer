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
  curationHandoff: vi.fn(),
  enableCuration: vi.fn(),
}));
const api = await import("@/lib/api/memory");

const openTerminal = vi.fn();
vi.mock("@/lib/hooks/useTerminals", () => ({ useOpenInTerminal: () => openTerminal }));

const feature = { on: true };
vi.mock("@/lib/hooks/useFeatures", () => ({ useFeatureEnabled: () => feature.on }));

function agent(type: string, over: Partial<SyncAgent> = {}): SyncAgent {
  return {
    agent: type,
    agent_type: type,
    copies: { written: 0 },
    curation: { memory: "on", curation: "on", source: "", last_curated_at: "" },
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
        curation: { memory: "on", curation: "off", source: "", last_curated_at: "" },
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
    expect(section).toHaveTextContent("Auto Dream is a Claude Code preview");
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

  acceptance("memory", "Curate now opens Claude Code in a terminal", async () => {
    vi.mocked(api.curationHandoff).mockResolvedValue({ handoff: { prompt: "Please consolidate" } });
    openTerminal.mockResolvedValue(true);
    renderSection("claude_code");
    fireEvent.click(await screen.findByRole("button", { name: "Curate now: Claude Code" }));
    await waitFor(() =>
      expect(openTerminal).toHaveBeenCalledWith(
        { agent: "claude_code", prompt: "Please consolidate" },
        expect.objectContaining({ label: "Copy prompt" }),
      ),
    );
    expect(api.curationHandoff).toHaveBeenCalledWith("claude_code");
  });

  test("Codex is not offered Curate now: it consolidates on its own", async () => {
    renderSection("codex");
    const section = await screen.findByTestId("memory-sync-section");
    expect(within(section).queryByRole("button", { name: /Curate now/ })).toBeNull();
  });

  acceptance("memory", "the person turns Claude Code's Auto Dream on", async () => {
    vi.mocked(api.getSyncState).mockResolvedValue(
      state([
        agent("claude_code", {
          curation: { memory: "on", curation: "off", source: "default", last_curated_at: "" },
          writer: { state: "ok", reason: "", path: "/Users/me/.claude" },
        }),
      ]),
    );
    vi.mocked(api.enableCuration).mockResolvedValue({ changed: true });
    renderSection("claude_code");
    const section = await screen.findByTestId("memory-sync-section");
    expect(section).toHaveTextContent("Auto Dream off · account default");
    expect(section).toHaveTextContent("Has not run on this machine yet");
    fireEvent.click(within(section).getByRole("button", { name: "Turn on" }));
    const dialog = await screen.findByRole("dialog", { name: "Turn on Auto Dream?" });
    expect(dialog).toHaveTextContent('"autoDreamEnabled": true');
    fireEvent.click(within(dialog).getByRole("button", { name: "Turn on" }));
    await waitFor(() => expect(api.enableCuration).toHaveBeenCalledWith("claude_code"));
    expect(
      await screen.findByText("Auto Dream is on for new Claude Code sessions"),
    ).toBeInTheDocument();
  });

  test("Auto Dream that is on says when it last ran and offers no switch", async () => {
    vi.mocked(api.getSyncState).mockResolvedValue(
      state([
        agent("claude_code", {
          curation: {
            memory: "on",
            curation: "on",
            source: "setting",
            last_curated_at: "2026-10-15T03:00:00Z",
          },
        }),
      ]),
    );
    renderSection("claude_code");
    const section = await screen.findByTestId("memory-sync-section");
    expect(section).toHaveTextContent("Auto Dream on · set in settings.json");
    expect(section).toHaveTextContent("Last ran");
    expect(within(section).queryByRole("button", { name: "Turn on" })).toBeNull();
  });

  test("a writer that cannot write says so, and there is nothing to curate", async () => {
    vi.mocked(api.getSyncState).mockResolvedValue(
      state([
        agent("codex", {
          curation: { memory: "off", curation: "off", source: "", last_curated_at: "" },
          writer: { state: "off", reason: "memories are off", path: "" },
        }),
      ]),
    );
    renderSection("codex");
    const section = await screen.findByTestId("memory-sync-section");
    expect(section).toHaveTextContent("Nothing written: its memory is off");
    expect(section).toHaveTextContent("memories are off");
    expect(section).toHaveTextContent(/memories = true under \[features\]/);
    expect(within(section).queryByRole("button", { name: /Curate now/ })).toBeNull();
  });

  test("nothing shows while the memory feature is off", async () => {
    feature.on = false;
    renderSection("claude_code");
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByTestId("memory-sync-section")).toBeNull();
  });
});
