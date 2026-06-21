// frontend/src/components/agents/AgentConversationsTab.test.tsx
//
// The "Conversations" tab renders a table of transcript sessions for a
// registered agent — title, project, counts, start + last-activity times — with
// search / project + time filters / sortable columns, a "load more" pager, and
// per-row "reveal file" + "distill to memory" actions. We mock the hook module
// (per agents/frontend.md §8) and FileActions (covered by its own test) so the
// component renders deterministically without network, toast, or Tauri.

import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AgentConversationsTab } from "./AgentConversationsTab";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const distillMutate = vi.fn();
const fetchNextPage = vi.fn();

vi.mock("@/lib/hooks/useAgentChatHistory", () => ({
  TRANSCRIPTS_PAGE_SIZE: 100,
  transcriptsKey: (name: string) => ["agents", name, "conversations"],
  useAgentTranscripts: vi.fn(),
  useDistillTranscript: vi.fn(() => ({
    mutate: distillMutate,
    isPending: false,
    data: undefined,
  })),
}));

// FileActions pulls in Tauri + toast + preferences; it has its own test. Here we
// stub it so we can assert the session's source_path is wired through.
vi.mock("@/components/FileActions", () => ({
  FileActions: ({ filePath }: { filePath: string }) => (
    <div data-testid="file-actions">{filePath}</div>
  ),
}));

const hooks = await import("@/lib/hooks/useAgentChatHistory");

function wrap({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const SESSION = {
  session_id: "s1",
  title: "Fix the login redirect bug",
  project_path: "/home/u/repo",
  message_count: 5,
  started_at: "2026-06-01T10:00:00Z",
  last_activity_at: "2026-06-01T11:30:00Z",
  source_path: "/home/u/.codex/sessions/2026/06/rollout-s1.jsonl",
};

function stubTranscripts(
  sessions: (typeof SESSION)[] = [SESSION],
  opts: {
    isPending?: boolean;
    error?: Error | null;
    total?: number;
    hasNextPage?: boolean;
    isFetchingNextPage?: boolean;
  } = {},
) {
  vi.mocked(hooks.useAgentTranscripts).mockReturnValue({
    data: opts.isPending
      ? undefined
      : { pages: [{ sessions, total: opts.total ?? sessions.length, limit: 100, offset: 0 }] },
    isPending: opts.isPending ?? false,
    error: opts.error ?? null,
    fetchNextPage,
    hasNextPage: opts.hasNextPage ?? false,
    isFetchingNextPage: opts.isFetchingNextPage ?? false,
  } as unknown as ReturnType<typeof hooks.useAgentTranscripts>);
}

/** Last (name, filters) the component passed to the transcripts hook. */
function lastFilters(): Record<string, unknown> {
  const calls = vi.mocked(hooks.useAgentTranscripts).mock.calls;
  return calls[calls.length - 1]?.[1] ?? {};
}

afterEach(() => vi.clearAllMocks());

describe("AgentConversationsTab", () => {
  test("renders a session row with title, project, count, and times", () => {
    stubTranscripts();
    render(<AgentConversationsTab name="codex" />, { wrapper: wrap });
    expect(screen.getByText("Fix the login redirect bug")).toBeInTheDocument();
    expect(screen.getByText("/home/u/repo")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    // source_path is wired into the reveal affordance (FileActions stub).
    expect(screen.getByTestId("file-actions")).toHaveTextContent("rollout-s1.jsonl");
  });

  test("shows a loading state while sessions are pending", () => {
    stubTranscripts([], { isPending: true });
    render(<AgentConversationsTab name="codex" />, { wrapper: wrap });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  test("shows an error state when the query fails", () => {
    stubTranscripts([], { error: new Error("request failed: 500") });
    render(<AgentConversationsTab name="codex" />, { wrapper: wrap });
    expect(screen.getByText(/request failed/i)).toBeInTheDocument();
  });

  test("shows the empty message when there are no sessions", () => {
    stubTranscripts([]);
    render(<AgentConversationsTab name="codex" />, { wrapper: wrap });
    expect(screen.getByText(/no conversations found/i)).toBeInTheDocument();
  });

  test("typing in search forwards the query to the hook", () => {
    stubTranscripts();
    render(<AgentConversationsTab name="codex" />, { wrapper: wrap });
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "alpha" } });
    expect(lastFilters().q).toBe("alpha");
  });

  test("default sort is last_activity desc; clicking 'Started' header sorts by started_at", () => {
    stubTranscripts();
    render(<AgentConversationsTab name="codex" />, { wrapper: wrap });
    expect(lastFilters().sort).toBe("last_activity_at");
    expect(lastFilters().order).toBe("desc");
    fireEvent.click(screen.getByRole("button", { name: /sort by started/i }));
    expect(lastFilters().sort).toBe("started_at");
  });

  test("clicking 'Load more' fetches the next page", () => {
    stubTranscripts([SESSION], { total: 250, hasNextPage: true });
    render(<AgentConversationsTab name="codex" />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("button", { name: /load more/i }));
    expect(fetchNextPage).toHaveBeenCalled();
  });

  test("clicking 'Distill to memory' calls mutate with the session id", async () => {
    distillMutate.mockImplementation(
      (_args: unknown, callbacks: { onSuccess?: (r: unknown) => void }) => {
        callbacks?.onSuccess?.({ insights: [], fact_ids: [] });
      },
    );
    stubTranscripts();
    render(<AgentConversationsTab name="codex" />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("button", { name: /distill/i }));
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
    distillMutate.mockImplementation(
      (_args: unknown, callbacks: { onSuccess?: (r: unknown) => void }) => {
        callbacks?.onSuccess?.({ insights, fact_ids: ["fact-1"] });
      },
    );

    stubTranscripts();
    render(<AgentConversationsTab name="codex" />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("button", { name: /distill/i }));
    await waitFor(() => expect(screen.getByText("Use Redis")).toBeInTheDocument());
    expect(screen.getByText(/We chose Redis/i)).toBeInTheDocument();
    expect(screen.getByText("decision")).toBeInTheDocument();
  });
});
