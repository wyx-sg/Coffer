// frontend/src/components/agents/AgentConversationsTab.test.tsx
//
// The "Conversations" tab renders transcript sessions for a registered agent
// through the shared DataTable — title, project, counts, start + last-activity
// times — with a search box, sortable headers, page-based (server) pagination,
// and a per-row "⋯" menu of file actions. The tab is read-only: nothing in it
// writes. We mock the hook module (per agents/frontend.md §8) and the file
// actions (covered by their own test) so the component renders deterministically
// without network or toast.

import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AgentConversationsTab } from "./AgentConversationsTab";
import type { TranscriptListParams } from "@/lib/api/agentTranscripts";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("@/lib/hooks/useAgentTranscripts", () => ({
  TRANSCRIPTS_PAGE_SIZE: 10,
  transcriptsKey: (name: string) => ["agents", name, "conversations"],
  useAgentTranscripts: vi.fn(),
}));

// The row's file actions pull in toast + preferences; they have their own test.
// Here we stub the useFileActionItems hook the row uses so the source path can
// be asserted as wired through without driving the real fs actions.
const openItem = { key: "open", label: "Open in editor", onClick: vi.fn() };
vi.mock("@/lib/fileActionItems", () => ({
  useFileActionItems: vi.fn(() => [openItem]),
}));

const hooks = await import("@/lib/hooks/useAgentTranscripts");
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

  test("offers open/reveal through the row's ⋯ menu and nothing that writes", () => {
    stubTranscripts();
    render(<AgentConversationsTab name="codex" />, { wrapper: wrap });
    const menu = screen.getByRole("button", { name: /more actions/i });
    fireEvent.click(menu);
    expect(screen.getByText("Open in editor")).toBeInTheDocument();
    // Read-only surface: no checkboxes (bulk select) anywhere in the table.
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
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

  test("re-clicking the active sort header flips the order", () => {
    stubTranscripts();
    render(<AgentConversationsTab name="codex" />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("button", { name: /sort by last activity/i }));
    expect(lastParams().sort).toBe("last_activity_at");
    expect(lastParams().order).toBe("asc");
  });

  test("keys rows by source_path so duplicate session_ids stay distinct rows", () => {
    // Two rows share a session_id (subagent sidechain) but have distinct files.
    const dup = { ...SESSION, source_path: "/home/u/.codex/sessions/2026/06/rollout-s1b.jsonl" };
    stubTranscripts([SESSION, dup]);
    render(<AgentConversationsTab name="codex" />, { wrapper: wrap });
    expect(screen.getAllByRole("button", { name: /more actions/i })).toHaveLength(2);
    expect(vi.mocked(fa.useFileActionItems)).toHaveBeenCalledWith(dup.source_path);
  });

  test("stepping to the next page advances the offset by the page size", () => {
    stubTranscripts([SESSION], { total: 250 });
    render(<AgentConversationsTab name="codex" />, { wrapper: wrap });
    const limit = lastParams().limit as number;
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(lastParams().offset).toBe(limit);
  });

  test("searching from a later page goes back to the first one", () => {
    // Otherwise the stale offset outruns the narrower result set and the table
    // reads "no conversations" while matches exist.
    stubTranscripts([SESSION], { total: 250 });
    render(<AgentConversationsTab name="codex" />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(lastParams().offset).toBeGreaterThan(0);

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "alpha" } });
    expect(lastParams().q).toBe("alpha");
    expect(lastParams().offset).toBe(0);
  });
});
