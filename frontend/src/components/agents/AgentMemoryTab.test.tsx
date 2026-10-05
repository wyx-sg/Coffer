// frontend/src/components/agents/AgentMemoryTab.test.tsx
//
// The Memory tab (boards 2.1.49–50): Coffer's memory first (Experimental; only
// with the memory feature on) with the hook, when it last fired and what it
// delivers, then the agent's own native stores as one bordered list whose row
// opens the store's page. No counts in headings, no row actions, a search only
// for a long list. Hooks are mocked at the hook boundary.
import type { PropsWithChildren } from "react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import { AgentMemoryTab } from "./AgentMemoryTab";
import type { AgentOut, CofferHook } from "@/lib/api/agents";
import type { NativeMemoryStore } from "@/lib/api/agentNativeMemory";

const navigateMock = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-router-dom")>()),
  useNavigate: () => navigateMock,
}));
vi.mock("@/lib/hooks/useAgentNativeMemory", () => ({ useAgentNativeMemory: vi.fn() }));
const nativeHooks = await import("@/lib/hooks/useAgentNativeMemory");
vi.mock("@/lib/hooks/useAgents", () => ({ useAgentHooks: vi.fn() }));
const agentHooks = await import("@/lib/hooks/useAgents");
vi.mock("@/lib/hooks/useFeatures", () => ({ useFeatureEnabled: vi.fn() }));
const features = await import("@/lib/hooks/useFeatures");

function wrap({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

const AGENT = {
  uid: "agt_01cc",
  name: "claude_code",
  type: "claude_code",
  config_dir: "/Users/xing/.claude",
  display_name: "Claude Code",
  model: null,
  tier_models: null,
  version: null,
  state: "installed_active",
  created_at: "2026-05-29T00:00:00Z",
  updated_at: "2026-05-29T00:00:00Z",
} as AgentOut;

const CODEX = {
  ...AGENT,
  uid: "agt_01cx",
  type: "codex",
  config_dir: "/Users/xing/.codex",
} as AgentOut;

const COFFER_STORE: NativeMemoryStore = {
  project: "Coffer",
  path: "/Users/xing/Coffer",
  memory_dir: "/Users/xing/.claude/projects/-Users-xing-Coffer/memory",
  item_count: 49,
};

const COFFER_HOOK: CofferHook = {
  event: "SessionStart,UserPromptSubmit",
  path: "/Users/xing/.claude/settings.json",
  health: "current",
  trust: "not_required",
  installed_command: "c",
  expected_command: "c",
  last_fired_at: new Date(Date.now() - 2 * 3_600_000).toISOString(),
};

function stubNative(items: NativeMemoryStore[] = [COFFER_STORE], extra: object = {}) {
  vi.mocked(nativeHooks.useAgentNativeMemory).mockReturnValue({
    data: { items },
    isPending: false,
    error: null,
    refetch: vi.fn(),
    ...extra,
  } as unknown as ReturnType<typeof nativeHooks.useAgentNativeMemory>);
}

function stubHook(hook: Partial<CofferHook> | null = {}) {
  vi.mocked(agentHooks.useAgentHooks).mockReturnValue({
    data: { items: [], parse_errors: [], coffer_hook: hook ? { ...COFFER_HOOK, ...hook } : null },
    isPending: false,
  } as unknown as ReturnType<typeof agentHooks.useAgentHooks>);
}

beforeEach(() => {
  vi.mocked(features.useFeatureEnabled).mockReturnValue(true);
  stubHook();
});
afterEach(() => vi.clearAllMocks());

describe("AgentMemoryTab", () => {
  test("Coffer's memory comes first: hook, last fired, delivers, and a link to the Memory page", () => {
    stubNative();
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    const section = within(screen.getByTestId("coffer-memory-section"));
    expect(section.getByRole("heading", { name: "Coffer’s memory" })).toBeInTheDocument();
    expect(section.getByText("Experimental")).toBeInTheDocument();
    expect(section.getByText("2 events in")).toBeInTheDocument();
    expect(section.getByText("~/.claude/settings.json")).toBeInTheDocument();
    expect(section.getByText("Current")).toBeInTheDocument();
    expect(section.getByText("2 hours ago")).toBeInTheDocument();
    expect(
      section.getByText(
        "The shared memory index, so Claude Code can look up what your agents learned",
      ),
    ).toBeInTheDocument();
    expect(section.getByRole("link", { name: "Open Memory" })).toHaveAttribute("href", "/memory");
    expect(section.queryByRole("button", { name: "Repair" })).not.toBeInTheDocument();
    // Coffer's section is above the agent's own.
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual(["Coffer’s memory", "Claude Code’s own memory"]);
  });

  acceptance("web-ui", "hook state appears only on the agent page", () => {
    stubNative();
    stubHook({ health: "stale" });
    render(<AgentMemoryTab agent={AGENT} onRepair={vi.fn()} />, { wrapper: wrap });
    const section = within(screen.getByTestId("coffer-memory-section"));
    expect(section.getByText("Out of date")).toBeInTheDocument();
    expect(section.getByRole("button", { name: "Repair" })).toBeInTheDocument();
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual(["Coffer’s memory", "Claude Code’s own memory"]);
  });

  test("a single-event hook names the event; an unhealthy one offers Repair", () => {
    stubNative();
    stubHook({ event: "SessionStart", health: "stale" });
    const onRepair = vi.fn();
    render(<AgentMemoryTab agent={CODEX} onRepair={onRepair} />, { wrapper: wrap });
    const section = within(screen.getByTestId("coffer-memory-section"));
    expect(section.getByText("SessionStart in")).toBeInTheDocument();
    expect(section.getByText("Out of date")).toBeInTheDocument();
    fireEvent.click(section.getByRole("button", { name: "Repair" }));
    expect(onRepair).toHaveBeenCalledTimes(1);
  });

  test("with the memory feature off, only the agent's own memory shows", () => {
    vi.mocked(features.useFeatureEnabled).mockReturnValue(false);
    stubNative();
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    expect(screen.queryByTestId("coffer-memory-section")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Claude Code’s own memory" })).toBeInTheDocument();
  });

  test("lists the native stores in one table under Project · Memory folder · Files", () => {
    stubNative();
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    expect(vi.mocked(nativeHooks.useAgentNativeMemory)).toHaveBeenCalledWith("agt_01cc");
    const own = within(screen.getByTestId("own-memory-section"));
    expect(
      own.getByText(
        "One store per project, written by Claude Code. Read-only: Coffer reads them and never writes them.",
      ),
    ).toBeInTheDocument();
    expect(own.getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "Project",
      "Memory folder",
      "Files",
    ]);
    expect(own.getAllByRole("row")).toHaveLength(2);
    expect(own.getByText("~/Coffer")).toBeInTheDocument();
    expect(own.getByText("~/.claude/projects/-Users-xing-Coffer/memory")).toBeInTheDocument();
    expect(own.getByText("49 files")).toBeInTheDocument();
    // No counts in the heading, no project search for a short list.
    expect(screen.queryByRole("textbox", { name: "Search projects" })).not.toBeInTheDocument();
  });

  test("a store with no memory is not listed; a long list gets a project search", () => {
    const stores: NativeMemoryStore[] = [
      { project: "scratch", path: "/tmp/work/hello", memory_dir: "/m/scratch", item_count: 0 },
      ...Array.from({ length: 9 }, (_, i) => ({
        project: `P${i}`,
        path: `/Users/xing/P${i}`,
        memory_dir: `/Users/xing/.claude/projects/p${i}/memory`,
        item_count: i + 1,
      })),
    ];
    stubNative(stores);
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    const own = within(screen.getByTestId("own-memory-section"));
    expect(own.queryByText(/work\/hello/)).not.toBeInTheDocument();
    expect(own.getAllByRole("row")).toHaveLength(10);
    fireEvent.change(own.getByRole("textbox", { name: "Search projects" }), {
      target: { value: "p3" },
    });
    expect(own.getAllByRole("row")).toHaveLength(2);
    expect(own.getByText("~/P3")).toBeInTheDocument();
  });

  test("falls back to the project label when the project path could not be resolved", () => {
    stubNative([{ ...COFFER_STORE, path: null }]);
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    expect(screen.getByText("Coffer")).toBeInTheDocument();
  });

  test("clicking a row opens that store's page, addressed by type and directory", () => {
    stubNative();
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    fireEvent.click(screen.getByText("~/Coffer"));
    const [path, query] = (navigateMock.mock.calls.at(-1)?.[0] as string).split("?");
    expect(path).toBe("/agents/claude_code/memory/store");
    const params = new URLSearchParams(query);
    expect(params.get("dir")).toBe(COFFER_STORE.memory_dir);
    expect(params.get("project")).toBe(COFFER_STORE.path);
  });

  test("no stores yet says where the agent will write them, inside its section", () => {
    stubNative([]);
    render(<AgentMemoryTab agent={CODEX} />, { wrapper: wrap });
    const own = within(screen.getByTestId("own-memory-section"));
    expect(own.getByText("No memory files from Codex yet")).toBeInTheDocument();
    expect(
      own.getByText(/codex writes ~\/\.codex\/memories\/MEMORY\.md as it learns/i),
    ).toBeInTheDocument();
  });

  test("a failed read shows the error with a retry", () => {
    const refetch = vi.fn();
    stubNative([], { data: undefined, error: new Error("boom"), refetch });
    render(<AgentMemoryTab agent={AGENT} />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(refetch).toHaveBeenCalled();
  });
});
