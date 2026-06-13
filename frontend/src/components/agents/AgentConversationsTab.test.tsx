// frontend/src/components/agents/AgentConversationsTab.test.tsx
//
// The "Conversations" tab renders a DataTable of transcript sessions for a
// registered agent, with a per-row "Distill to memory" action. After a
// successful distill the returned insights are shown below the table. We mock
// the hook module so the component renders deterministically without network.

import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AgentConversationsTab } from "./AgentConversationsTab";

// ---------------------------------------------------------------------------
// Mock the hook module — we test behaviour through the component/hook boundary
// not the real network, per agents/frontend.md §8.
// ---------------------------------------------------------------------------

const distillMutate = vi.fn();

vi.mock("@/lib/hooks/useAgentChatHistory", () => ({
  transcriptsKey: (name: string) => ["agents", name, "conversations"],
  useAgentTranscripts: vi.fn(),
  useDistillTranscript: vi.fn(() => ({
    mutate: distillMutate,
    isPending: false,
    data: undefined,
  })),
}));

const hooks = await import("@/lib/hooks/useAgentChatHistory");

function wrap({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const SESSION = {
  session_id: "s1",
  project_path: "/home/u/repo",
  message_count: 5,
  started_at: "2026-06-01T10:00:00Z",
};

function stubTranscripts(
  sessions: typeof SESSION[] = [SESSION],
  opts: { isPending?: boolean; error?: Error | null } = {},
) {
  vi.mocked(hooks.useAgentTranscripts).mockReturnValue({
    data: { sessions },
    isPending: opts.isPending ?? false,
    error: opts.error ?? null,
  } as unknown as ReturnType<typeof hooks.useAgentTranscripts>);
}

afterEach(() => vi.clearAllMocks());

describe("AgentConversationsTab", () => {
  test("renders a session row with project path and message count", () => {
    stubTranscripts();
    render(<AgentConversationsTab name="claude" />, { wrapper: wrap });
    expect(screen.getByText("/home/u/repo")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  test("shows a loading state while sessions are pending", () => {
    stubTranscripts([], { isPending: true });
    render(<AgentConversationsTab name="claude" />, { wrapper: wrap });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  test("shows an error state when the query fails", () => {
    stubTranscripts([], { error: new Error("request failed: 500") });
    render(<AgentConversationsTab name="claude" />, { wrapper: wrap });
    expect(screen.getByText(/request failed/i)).toBeInTheDocument();
  });

  test("shows the empty message when there are no sessions", () => {
    stubTranscripts([]);
    render(<AgentConversationsTab name="claude" />, { wrapper: wrap });
    // DataTable renders the emptyMessage; i18next resolves keys in the test env
    expect(screen.getByText(/no conversations found/i)).toBeInTheDocument();
  });

  test("clicking 'Distill to memory' calls mutate with the session id", async () => {
    distillMutate.mockImplementation((_args: unknown, callbacks: { onSuccess?: (r: unknown) => void }) => {
      callbacks?.onSuccess?.({ insights: [], fact_ids: [] });
    });
    stubTranscripts();
    render(<AgentConversationsTab name="claude" />, { wrapper: wrap });
    const btn = screen.getByRole("button", { name: /distill/i });
    fireEvent.click(btn);
    await waitFor(() =>
      expect(distillMutate).toHaveBeenCalledWith(
        { session_id: "s1" },
        expect.objectContaining({ onSuccess: expect.any(Function) }),
      ),
    );
  });

  test("renders returned insights inline after a successful distill click", async () => {
    const insights = [
      {
        name: "Use Redis",
        description: "cache layer",
        body: "We chose Redis for caching.",
        type: "decision",
      },
    ];
    distillMutate.mockImplementation((_args: unknown, callbacks: { onSuccess?: (r: unknown) => void }) => {
      callbacks?.onSuccess?.({ insights, fact_ids: ["fact-1"] });
    });

    stubTranscripts();
    render(<AgentConversationsTab name="claude" />, { wrapper: wrap });
    const btn = screen.getByRole("button", { name: /distill/i });
    fireEvent.click(btn);
    await waitFor(() => expect(screen.getByText("Use Redis")).toBeInTheDocument());
    expect(screen.getByText(/We chose Redis/i)).toBeInTheDocument();
    expect(screen.getByText("decision")).toBeInTheDocument();
  });
});
