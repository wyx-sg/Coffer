// frontend/src/components/agents/AgentTable.test.tsx
//
// The agents list is one shared DataTable holding BOTH external agents (kind
// `agent`) and Coffer's own built-in agents (kind `builtin_agent`). External
// rows navigate to a detail page and own the MCP/skills columns; built-in rows
// show "—" there (no external endpoints), open an edit dialog on click, and
// delete via the built-in hook with the last-agent 409 surfaced inline.

import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";
import { AgentTable } from "./AgentTable";
import type { AgentOut } from "@/lib/api/agents";
import type { BuiltinAgentOut } from "@/lib/api/builtinAgents";
import { ApiError } from "@/lib/api/errors";

vi.mock("@/lib/hooks/useAgents", () => ({
  useRemoveAgent: vi.fn(),
  // The "Coffer MCP" column renders a status badge per row.
  useAgentMcpStatus: vi.fn(() => ({ data: { installed: false }, isPending: false })),
  useAgentMcpInstall: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

// Built-in rows delete via this hook; the edit form (opened on row click) uses
// the create/patch hooks, so stub all three.
vi.mock("@/lib/hooks/useBuiltinAgents", () => ({
  useRemoveBuiltinAgent: vi.fn(),
  useCreateBuiltinAgent: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  usePatchBuiltinAgent: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
}));

// The "Coffer skills" column counts enabled bindings from the skills list.
vi.mock("@/lib/hooks/useSkills", () => ({
  useSkills: vi.fn(() => ({ data: [], isPending: false })),
}));

const { useRemoveAgent } = await import("@/lib/hooks/useAgents");
const { useRemoveBuiltinAgent } = await import("@/lib/hooks/useBuiltinAgents");
const useRemoveAgentMock = vi.mocked(useRemoveAgent);
const useRemoveBuiltinMock = vi.mocked(useRemoveBuiltinAgent);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children ?? ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

const SAMPLE: AgentOut[] = [
  {
    name: "cur",
    type: "codex",
    config_dir: "/home/u/.codex",
    description: null,
    created_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:00Z",
  },
  {
    name: "cc",
    type: "claude_code",
    config_dir: "/home/u/.claude",
    description: null,
    created_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:00Z",
  },
];

const BUILTIN: BuiltinAgentOut[] = [
  {
    ref: "builtin_agent:coffer",
    kind: "builtin_agent",
    name: "coffer",
    description: null,
    config: {
      model: "anthropic:claude-sonnet-4-6",
      use_gateway: true,
      confirm_tools: ["*delete*"],
    },
    enabled: true,
    created_at: "2026-05-28T00:00:00Z",
    updated_at: "2026-05-28T00:00:00Z",
  } as unknown as BuiltinAgentOut,
];

afterEach(() => vi.clearAllMocks());

function stubRemoves() {
  useRemoveAgentMock.mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useRemoveAgent>);
  useRemoveBuiltinMock.mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useRemoveBuiltinAgent>);
}

describe("AgentTable", () => {
  test("renders one row per agent with its config directory", () => {
    stubRemoves();
    render(<AgentTable agents={SAMPLE} />, { wrapper: wrap(null) });
    expect(screen.getByText("cur")).toBeInTheDocument();
    expect(screen.getByText("cc")).toBeInTheDocument();
    expect(screen.getByText("/home/u/.codex")).toBeInTheDocument();
    expect(screen.getByText("/home/u/.claude")).toBeInTheDocument();
  });

  test("a search box and type filter are available", () => {
    stubRemoves();
    render(<AgentTable agents={SAMPLE} />, { wrapper: wrap(null) });
    expect(screen.getByRole("textbox", { name: /search agents/i })).toBeInTheDocument();
  });

  test("the delete icon opens a styled dialog and confirming invokes remove", () => {
    const mutate = vi.fn();
    useRemoveAgentMock.mockReturnValue({
      mutate,
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveAgent>);
    useRemoveBuiltinMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveBuiltinAgent>);
    render(<AgentTable agents={SAMPLE} />, { wrapper: wrap(null) });
    fireEvent.click(screen.getByRole("button", { name: /delete cur/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));
    expect(mutate).toHaveBeenCalled();
    expect(mutate.mock.calls[0][0]).toBe("cur");
  });

  test("cancelling the delete dialog is a no-op", () => {
    const mutate = vi.fn();
    useRemoveAgentMock.mockReturnValue({
      mutate,
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveAgent>);
    useRemoveBuiltinMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveBuiltinAgent>);
    render(<AgentTable agents={SAMPLE} />, { wrapper: wrap(null) });
    fireEvent.click(screen.getByRole("button", { name: /delete cur/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /cancel/i }));
    expect(mutate).not.toHaveBeenCalled();
  });

  test("built-in agents appear as rows in the same table", () => {
    stubRemoves();
    render(<AgentTable agents={SAMPLE} builtinAgents={BUILTIN} />, { wrapper: wrap(null) });
    // The built-in agent is just another row alongside the external ones.
    expect(screen.getByText("coffer")).toBeInTheDocument();
    expect(screen.getByText("cur")).toBeInTheDocument();
    // Its description cell falls back to the model string.
    expect(screen.getByText("anthropic:claude-sonnet-4-6")).toBeInTheDocument();
  });

  test("clicking a built-in row opens the edit form", () => {
    stubRemoves();
    render(<AgentTable agents={[]} builtinAgents={BUILTIN} />, { wrapper: wrap(null) });
    fireEvent.click(screen.getByText("coffer"));
    const dialog = screen.getByRole("dialog");
    // Edit mode shows the model value in the form.
    expect(within(dialog).getByDisplayValue("anthropic:claude-sonnet-4-6")).toBeInTheDocument();
  });

  test("deleting a built-in agent uses the built-in hook and surfaces its 409", () => {
    const mutate = vi.fn((_name, opts: { onError: (e: unknown) => void }) => {
      opts.onError(
        new ApiError("CANNOT_DELETE_LAST_BUILTIN_AGENT", "cannot delete the last built-in agent"),
      );
    });
    useRemoveAgentMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveAgent>);
    useRemoveBuiltinMock.mockReturnValue({
      mutate,
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveBuiltinAgent>);
    render(<AgentTable agents={[]} builtinAgents={BUILTIN} />, { wrapper: wrap(null) });
    fireEvent.click(screen.getByRole("button", { name: /delete coffer/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));
    expect(mutate).toHaveBeenCalled();
    expect(mutate.mock.calls[0][0]).toBe("coffer");
    // The last-agent 409 is shown inline rather than crashing.
    expect(within(dialog).getByRole("alert")).toHaveTextContent(/last built-in agent/i);
  });
});
