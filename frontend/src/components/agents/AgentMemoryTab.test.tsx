// frontend/src/components/agents/AgentMemoryTab.test.tsx
//
// The "Memory" tab on the agent detail page lists each memory store and toggles
// whether it is projected into this agent. We mock the projection hooks so the
// component renders deterministically and assert the establish/remove wiring +
// the projection status display.

import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { AgentMemoryTab } from "./AgentMemoryTab";
import type { AgentOut } from "@/lib/api/agents";

const establishMutate = vi.fn();
const removeMutate = vi.fn();

vi.mock("@/lib/hooks/useMemoryProjections", () => ({
  useMemoryStores: vi.fn(),
  useMemoryProjections: vi.fn(),
  useEstablishProjection: vi.fn(() => ({ mutate: establishMutate, isPending: false, error: null })),
  useRemoveProjection: vi.fn(() => ({ mutate: removeMutate, isPending: false, error: null })),
}));
const hooks = await import("@/lib/hooks/useMemoryProjections");

const AGENT: AgentOut = {
  name: "claude",
  type: "claude_code",
  config_dir: "/home/u/.claude",
  description: null,
  created_at: "2026-05-29T00:00:00Z",
  updated_at: "2026-05-29T00:00:00Z",
};

const STORE = {
  ref: "memory:global",
  kind: "memory",
  name: "global",
  scope: "global" as const,
  project_id: "0".repeat(26),
  description: null,
  config: { retrieval_modes: ["grep", "keyword"], default_mode: "keyword", max_fact_chars: 8192 },
  enabled: true,
  created_at: "2026-05-29T00:00:00Z",
  updated_at: "2026-05-29T00:00:00Z",
};

const PROJECT_STORE = {
  ...STORE,
  ref: "memory:project-x",
  name: "project-x",
  scope: "project" as const,
  project_id: "01HXYZPROJECTULID0000000000",
  project_root: "/home/u/code/project-x",
};

function stubStores(stores: unknown[] = [STORE]) {
  vi.mocked(hooks.useMemoryStores).mockReturnValue({
    data: stores,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof hooks.useMemoryStores>);
}

afterEach(() => vi.clearAllMocks());

describe("AgentMemoryTab", () => {
  test("lists stores and shows 'not projected' when no projection exists", () => {
    stubStores();
    vi.mocked(hooks.useMemoryProjections).mockReturnValue({
      data: [],
      isPending: false,
    } as unknown as ReturnType<typeof hooks.useMemoryProjections>);

    render(<AgentMemoryTab agent={AGENT} />);
    // "global" appears twice (store name + scope badge).
    expect(screen.getAllByText("global").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/not projected/i)).toBeInTheDocument();
    expect(screen.getByRole("switch")).not.toBeChecked();
  });

  test("toggling on establishes a projection for this agent", () => {
    stubStores();
    vi.mocked(hooks.useMemoryProjections).mockReturnValue({
      data: [],
      isPending: false,
    } as unknown as ReturnType<typeof hooks.useMemoryProjections>);

    render(<AgentMemoryTab agent={AGENT} />);
    fireEvent.click(screen.getByRole("switch"));
    expect(establishMutate).toHaveBeenCalledWith({ agentRef: "claude" });
  });

  test("shows projection status and toggling off removes it", () => {
    stubStores();
    vi.mocked(hooks.useMemoryProjections).mockReturnValue({
      data: [
        {
          agent_ref: "claude",
          projection_mode: "SYMLINK",
          target_path: "/home/u/.claude/projects/x/memory",
          native_memory_disabled: false,
        },
      ],
      isPending: false,
    } as unknown as ReturnType<typeof hooks.useMemoryProjections>);

    render(<AgentMemoryTab agent={AGENT} />);
    expect(screen.getByText("SYMLINK")).toBeInTheDocument();
    expect(screen.getByText("/home/u/.claude/projects/x/memory")).toBeInTheDocument();

    const sw = screen.getByRole("switch");
    expect(sw).toBeChecked();
    fireEvent.click(sw);
    expect(removeMutate).toHaveBeenCalledWith("claude");
  });

  test("project-scoped store passes its project_root when establishing", () => {
    stubStores([PROJECT_STORE]);
    vi.mocked(hooks.useMemoryProjections).mockReturnValue({
      data: [],
      isPending: false,
    } as unknown as ReturnType<typeof hooks.useMemoryProjections>);

    render(<AgentMemoryTab agent={AGENT} />);
    fireEvent.click(screen.getByRole("switch"));
    expect(establishMutate).toHaveBeenCalledWith({
      agentRef: "claude",
      projectRoot: "/home/u/code/project-x",
    });
  });

  test("project store with no known root disables the toggle and does not establish", () => {
    stubStores([{ ...PROJECT_STORE, project_root: null }]);
    vi.mocked(hooks.useMemoryProjections).mockReturnValue({
      data: [],
      isPending: false,
    } as unknown as ReturnType<typeof hooks.useMemoryProjections>);

    render(<AgentMemoryTab agent={AGENT} />);
    const sw = screen.getByRole("switch");
    expect(sw).toBeDisabled();
    fireEvent.click(sw);
    expect(establishMutate).not.toHaveBeenCalled();
    expect(screen.getByText(/no known root/i)).toBeInTheDocument();
  });
});
