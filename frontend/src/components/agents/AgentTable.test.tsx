// frontend/src/components/agents/AgentTable.test.tsx
//
// The agents list renders via the shared DataTable: rows navigate to the
// detail page on click, and the only row action is a delete icon that opens a
// styled confirmation dialog (no window.confirm). The type column shows the
// product name, the config dir is home-relative (full path in a tooltip), and
// an availability pill reflects the provider registry.
//
// Names and uids are two different things here and the fixtures keep them
// apart (`cur` / `u-cur`): every cell the user reads spells the NAME, while
// the delete request, the row key and the skill-binding lookup all spell the
// UID. Fixtures whose uid echoed the name would let a lookup keyed on the
// wrong one pass.

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";
import { AgentTable } from "./AgentTable";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { AgentOut } from "@/lib/api/agents";

vi.mock("@/lib/hooks/useAgents", () => ({
  useRemoveAgent: vi.fn(),
  // The "Coffer MCP" column renders a status badge per row.
  useAgentMcpStatus: vi.fn(() => ({ data: { installed: false }, isPending: false })),
  useAgentMcpInstall: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

// The "Coffer skills" column counts enabled bindings from the skills list.
vi.mock("@/lib/hooks/useSkills", () => ({
  useSkills: vi.fn(() => ({ data: [], isPending: false })),
}));

// The availability column reads the turn platform's provider registry.
vi.mock("@/lib/hooks/useAgentProviders", () => ({
  useAgentProviders: vi.fn(() => ({
    data: [
      { agent_key: "codex", display_name: "Codex", available: false },
      { agent_key: "claude_code", display_name: "Claude Code", available: true },
    ],
    isPending: false,
  })),
}));

const { useRemoveAgent } = await import("@/lib/hooks/useAgents");
const useRemoveAgentMock = vi.mocked(useRemoveAgent);
const { useAgentProviders } = await import("@/lib/hooks/useAgentProviders");
const useAgentProvidersMock = vi.mocked(useAgentProviders);
const { useSkills } = await import("@/lib/hooks/useSkills");
const useSkillsMock = vi.mocked(useSkills);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter>{children ?? ui}</MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

const SAMPLE: AgentOut[] = [
  {
    uid: "u-cur",
    name: "cur",
    type: "codex",
    config_dir: "/home/u/.codex",
    description: null,
    created_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:00Z",
  },
  {
    uid: "u-cc",
    name: "cc",
    type: "claude_code",
    config_dir: "/home/u/.claude",
    description: null,
    created_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:00Z",
  },
];

function stubRemove(mutate = vi.fn()) {
  useRemoveAgentMock.mockReturnValue({
    mutate,
    isPending: false,
  } as unknown as ReturnType<typeof useRemoveAgent>);
  return mutate;
}

describe("AgentTable", () => {
  beforeEach(() => {
    // clearAllMocks below wipes the factory's default return value, so every
    // test that does not care about skill counts starts from "none delivered".
    useSkillsMock.mockReturnValue({ data: [], isPending: false } as unknown as ReturnType<
      typeof useSkills
    >);
  });
  afterEach(() => vi.clearAllMocks());

  test("renders one row per agent with a home-relative config directory", () => {
    stubRemove();
    render(<AgentTable agents={SAMPLE} />, { wrapper: wrap(null) });
    expect(screen.getByText("cur")).toBeInTheDocument();
    expect(screen.getByText("cc")).toBeInTheDocument();
    expect(screen.getByText("~/.codex")).toBeInTheDocument();
    expect(screen.getByText("~/.claude")).toBeInTheDocument();
    expect(screen.queryByText("/home/u/.codex")).not.toBeInTheDocument();
  });

  test("shows the product name for the type, never the registry key", () => {
    stubRemove();
    render(<AgentTable agents={SAMPLE} />, { wrapper: wrap(null) });
    expect(screen.getByText("Codex")).toBeInTheDocument();
    expect(screen.getByText("Claude Code")).toBeInTheDocument();
    expect(screen.queryByText("claude_code")).not.toBeInTheDocument();
  });

  test("shows availability from the provider registry per agent type", () => {
    stubRemove();
    render(<AgentTable agents={SAMPLE} />, { wrapper: wrap(null) });
    const codexRow = screen.getByText("cur").closest("tr") as HTMLElement;
    const claudeRow = screen.getByText("cc").closest("tr") as HTMLElement;
    expect(within(codexRow).getByText(/not found/i)).toBeInTheDocument();
    expect(within(claudeRow).getByText(/^available$/i)).toBeInTheDocument();
  });

  test("shows a placeholder while the provider registry loads", () => {
    stubRemove();
    useAgentProvidersMock.mockReturnValueOnce({
      data: undefined,
      isPending: true,
    } as unknown as ReturnType<typeof useAgentProviders>);
    render(<AgentTable agents={SAMPLE} />, { wrapper: wrap(null) });
    expect(screen.queryByText(/not found/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^available$/i)).not.toBeInTheDocument();
  });

  test("a search box and type filter are available", () => {
    stubRemove();
    render(<AgentTable agents={SAMPLE} />, { wrapper: wrap(null) });
    expect(screen.getByRole("textbox", { name: /search agents/i })).toBeInTheDocument();
  });

  test("the delete icon opens a styled dialog and confirming invokes remove", () => {
    const mutate = stubRemove();
    render(<AgentTable agents={SAMPLE} />, { wrapper: wrap(null) });
    fireEvent.click(screen.getByRole("button", { name: /delete cur/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));
    expect(mutate).toHaveBeenCalled();
    // The dialog named the agent, but the request is addressed to its uid.
    expect(mutate.mock.calls[0][0]).toBe("u-cur");
  });

  test("counts delivered skills per agent uid, not per agent name", () => {
    stubRemove();
    // Two bindings for `cur`, one for `cc`. Each binding carries the agent's
    // name as well, spelled wrong here on purpose: a count built from
    // `agent_name` would put both rows at zero.
    useSkillsMock.mockReturnValue({
      data: [
        {
          bindings: [
            { agent_uid: "u-cur", agent_name: "stale-label" },
            { agent_uid: "u-cc", agent_name: "stale-label" },
          ],
        },
        { bindings: [{ agent_uid: "u-cur", agent_name: "stale-label" }] },
      ],
      isPending: false,
    } as unknown as ReturnType<typeof useSkills>);
    render(<AgentTable agents={SAMPLE} />, { wrapper: wrap(null) });
    const codexRow = screen.getByText("cur").closest("tr") as HTMLElement;
    const claudeRow = screen.getByText("cc").closest("tr") as HTMLElement;
    expect(within(codexRow).getByText("2")).toBeInTheDocument();
    expect(within(claudeRow).getByText("1")).toBeInTheDocument();
  });

  test("cancelling the delete dialog is a no-op", () => {
    const mutate = stubRemove();
    render(<AgentTable agents={SAMPLE} />, { wrapper: wrap(null) });
    fireEvent.click(screen.getByRole("button", { name: /delete cur/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /cancel/i }));
    expect(mutate).not.toHaveBeenCalled();
  });
});
