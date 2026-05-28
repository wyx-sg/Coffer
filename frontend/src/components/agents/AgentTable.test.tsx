// frontend/src/components/agents/AgentTable.test.tsx
//
// TEST25-206: render assertions for the agents table — row content + the
// destructive "Delete" path. We mock the remove mutation rather than
// `fetch` directly because the component routes the click through
// `useRemoveAgent`.

import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { AgentTable } from "./AgentTable";
import type { AgentOut } from "@/lib/api/agents";

vi.mock("@/lib/hooks/useAgents", () => ({
  useRemoveAgent: vi.fn(),
}));

const { useRemoveAgent } = await import("@/lib/hooks/useAgents");
const useRemoveAgentMock = vi.mocked(useRemoveAgent);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children ?? ui}</QueryClientProvider>
  );
}

const SAMPLE: AgentOut[] = [
  {
    name: "cur",
    type: "cursor",
    skill_dir: "/home/u/.cursor/skills",
    skill_dir_override: null,
    auto_detected: true,
    enabled: true,
    description: null,
    created_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:00Z",
  },
  {
    name: "cc",
    type: "claude_code",
    skill_dir: "/home/u/.claude/skills",
    skill_dir_override: null,
    auto_detected: false,
    enabled: false,
    description: null,
    created_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:00Z",
  },
];

describe("AgentTable", () => {
  afterEach(() => vi.clearAllMocks());

  test("renders one row per agent", () => {
    useRemoveAgentMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveAgent>);
    render(<AgentTable agents={SAMPLE} />, { wrapper: wrap(null) });
    expect(screen.getByText("cur")).toBeInTheDocument();
    expect(screen.getByText("cc")).toBeInTheDocument();
    expect(screen.getByText("cursor")).toBeInTheDocument();
    expect(screen.getByText("claude_code")).toBeInTheDocument();
  });

  test("auto-detected agents show a check mark cell", () => {
    useRemoveAgentMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveAgent>);
    render(<AgentTable agents={SAMPLE} />, { wrapper: wrap(null) });
    // The check character appears for the auto-detected row.
    expect(screen.getByText("✓")).toBeInTheDocument();
  });

  test("clicking Delete invokes the remove mutation on confirm", () => {
    const mutate = vi.fn();
    useRemoveAgentMock.mockReturnValue({
      mutate,
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveAgent>);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<AgentTable agents={SAMPLE} />, { wrapper: wrap(null) });
    const deletes = screen.getAllByRole("button", { name: /delete/i });
    fireEvent.click(deletes[0]);
    expect(confirmSpy).toHaveBeenCalled();
    expect(mutate).toHaveBeenCalledWith("cur");
    confirmSpy.mockRestore();
  });

  test("clicking Delete is a no-op when the user cancels confirm", () => {
    const mutate = vi.fn();
    useRemoveAgentMock.mockReturnValue({
      mutate,
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveAgent>);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<AgentTable agents={SAMPLE} />, { wrapper: wrap(null) });
    const deletes = screen.getAllByRole("button", { name: /delete/i });
    fireEvent.click(deletes[0]);
    expect(mutate).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});
