// frontend/src/components/agents/AgentConversationsTab.test.tsx
//
// The "Conversations" tab renders transcript sessions for a registered agent
// through the shared DataTable — title, project, counts, start + last-activity
// times — with a search box, page-based (server) pagination, bulk select, and
// per-row "distill to memory" + a "⋯" menu of file actions. We mock the hook
// module (per agents/frontend.md §8) and FileActions (covered by its own test)
// so the component renders deterministically without network, toast, or Tauri.

import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AgentConversationsTab } from "./AgentConversationsTab";
import type { TranscriptListParams } from "@/lib/api/agentChat";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Both the per-row button and the bulk bar use useDistillBatch: the per-row
// button calls .mutate({ session_ids:[id] }); the bulk bar calls .mutateAsync().
const distillMutate = vi.fn();
const distillMutateAsync = vi.fn().mockResolvedValue({ queued: 0, skipped: 0, total: 0 });

vi.mock("@/lib/hooks/useAgentChatHistory", () => ({
  TRANSCRIPTS_PAGE_SIZE: 10,
  transcriptsKey: (name: string) => ["agents", name, "conversations"],
  useAgentTranscripts: vi.fn(),
  useDistillBatch: vi.fn(() => ({
    mutate: distillMutate,
    mutateAsync: distillMutateAsync,
    isPending: false,
  })),
}));

// The row's file actions pull in Tauri + toast + preferences; they have their
// own test. Here we stub the useFileActionItems hook the row uses so the source
// path can be asserted as wired through without driving the real fs actions.
const fileItems = [{ key: "open", label: "Open in editor", onClick: vi.fn() }];
vi.mock("@/lib/fileActionItems", () => ({
  useFileActionItems: vi.fn(() => fileItems),
}));

const hooks = await import("@/lib/hooks/useAgentChatHistory");
const fa = await import("@/lib/fileActionItems");

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
  opts: { isPending?: boolean; error?: Error | null; total?: number } = {},
) {
  vi.mocked(hooks.useAgentTranscripts).mockReturnValue({
    data: opts.isPending
      ? undefined
      : { sessions, total: opts.total ?? sessions.length, limit: 10, offset: 0 },
    isPending: opts.isPending ?? false,
    error: opts.error ?? null,
  } as unknown as ReturnType<typeof hooks.useAgentTranscripts>);
}

/** Last (name, params) the component passed to the transcripts hook. */
function lastParams(): TranscriptListParams {
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
    // source_path is wired into the row's file actions (folded into the ⋯ menu).
    expect(vi.mocked(fa.useFileActionItems)).toHaveBeenCalledWith(SESSION.source_path);
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

  test("first page request carries limit/offset (paged on demand)", () => {
    stubTranscripts([SESSION], { total: 250 });
    render(<AgentConversationsTab name="codex" />, { wrapper: wrap });
    expect(typeof lastParams().limit).toBe("number");
    expect(lastParams().offset).toBe(0);
  });

  test("typing in search forwards the query to the hook", () => {
    stubTranscripts();
    render(<AgentConversationsTab name="codex" />, { wrapper: wrap });
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "alpha" } });
    expect(lastParams().q).toBe("alpha");
  });

  test("default sort is last_activity desc; clicking 'Started' header sorts by started_at", () => {
    stubTranscripts();
    render(<AgentConversationsTab name="codex" />, { wrapper: wrap });
    expect(lastParams().sort).toBe("last_activity_at");
    expect(lastParams().order).toBe("desc");
    fireEvent.click(screen.getByRole("button", { name: /sort by started/i }));
    expect(lastParams().sort).toBe("started_at");
  });

  test("keys rows by source_path so duplicate session_ids stay independently selectable", () => {
    // Two rows share a session_id (subagent sidechain) but have distinct files.
    const dup = { ...SESSION, source_path: "/home/u/.codex/sessions/2026/06/rollout-s1b.jsonl" };
    stubTranscripts([SESSION, dup]);
    render(<AgentConversationsTab name="codex" />, { wrapper: wrap });
    const checkboxes = screen.getAllByRole("checkbox");
    // select-all + 2 rows = 3 checkboxes (no rowKey collision collapsing them).
    expect(checkboxes).toHaveLength(3);
  });

  test("stepping to the next page advances the offset by the page size", () => {
    stubTranscripts([SESSION], { total: 250 });
    render(<AgentConversationsTab name="codex" />, { wrapper: wrap });
    const limit = lastParams().limit as number;
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(lastParams().offset).toBe(limit);
  });

  test("clicking the per-row 'Distill' enqueues a single-session async batch", async () => {
    stubTranscripts();
    render(<AgentConversationsTab name="codex" />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("button", { name: /distill session s1 to memory/i }));
    await waitFor(() =>
      expect(distillMutate).toHaveBeenCalledWith(
        { session_ids: ["s1"] },
        expect.objectContaining({ onSuccess: expect.any(Function) }),
      ),
    );
  });

  test("per-row distill does NOT render the distilled result inline in the table", async () => {
    // Guard against re-introducing the old inline-insights cell: even if the
    // success payload carried insight cards, the per-row button must not render
    // them — progress shows only in the status column; the result goes to memory.
    distillMutate.mockImplementation(
      (_args: unknown, callbacks: { onSuccess?: (r: unknown) => void }) => {
        callbacks?.onSuccess?.({
          queued: 1,
          skipped: 0,
          total: 1,
          insights: [{ name: "Use Redis", description: "cache", body: "We chose Redis for caching." }],
        });
      },
    );
    stubTranscripts();
    render(<AgentConversationsTab name="codex" />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("button", { name: /distill session s1 to memory/i }));
    await waitFor(() => expect(distillMutate).toHaveBeenCalled());
    expect(screen.queryByText("Use Redis")).not.toBeInTheDocument();
    expect(screen.queryByText(/We chose Redis/i)).not.toBeInTheDocument();
  });

  test("selecting a row reveals the bulk distill action", () => {
    stubTranscripts();
    render(<AgentConversationsTab name="codex" />, { wrapper: wrap });
    // Tick the row checkbox (the first checkbox is select-all).
    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[checkboxes.length - 1]);
    // Bulk bar shows the selected-count label + a distill action button.
    expect(screen.getByText(/1 selected/i)).toBeInTheDocument();
  });
});
