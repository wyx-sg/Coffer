// frontend/src/components/agents/AgentTable.test.tsx
//
// The agents list now renders via the shared DataTable: rows navigate to the
// detail page on click, and the only row action is a delete icon that opens a
// styled confirmation dialog (no window.confirm).

import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";
import { AgentTable } from "./AgentTable";
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

const { useRemoveAgent } = await import("@/lib/hooks/useAgents");
const useRemoveAgentMock = vi.mocked(useRemoveAgent);

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

describe("AgentTable", () => {
  afterEach(() => vi.clearAllMocks());

  test("renders one row per agent with its config directory", () => {
    useRemoveAgentMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveAgent>);
    render(<AgentTable agents={SAMPLE} />, { wrapper: wrap(null) });
    expect(screen.getByText("cur")).toBeInTheDocument();
    expect(screen.getByText("cc")).toBeInTheDocument();
    expect(screen.getByText("/home/u/.codex")).toBeInTheDocument();
    expect(screen.getByText("/home/u/.claude")).toBeInTheDocument();
  });

  test("a search box and type filter are available", () => {
    useRemoveAgentMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveAgent>);
    render(<AgentTable agents={SAMPLE} />, { wrapper: wrap(null) });
    expect(screen.getByRole("textbox", { name: /search agents/i })).toBeInTheDocument();
  });

  test("the delete icon opens a styled dialog and confirming invokes remove", () => {
    const mutate = vi.fn();
    useRemoveAgentMock.mockReturnValue({
      mutate,
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveAgent>);
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
    render(<AgentTable agents={SAMPLE} />, { wrapper: wrap(null) });
    fireEvent.click(screen.getByRole("button", { name: /delete cur/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /cancel/i }));
    expect(mutate).not.toHaveBeenCalled();
  });
});
