// frontend/src/components/agents/AgentConversationsTab.test.tsx
//
// The "Conversations" tab renders transcript sessions for a registered agent
// through the shared DataTable — title, project, counts, start + last-activity
// times — with a search box, sortable headers and page-based (server)
// pagination. The tab is read-only: nothing in it writes. Clicking a row opens
// that conversation's own page, which is where the open / reveal actions moved
// to from the old per-row "⋯" menu, so what this suite pins about a row is the
// URL it navigates to — keyed by source_path, because session_id repeats across
// subagent sidechain files. We mock the hook module (per .agents/frontend.md §8)
// and useNavigate so the component renders deterministically without network.
//
// The tab is given the agent's `uid` and nothing else: it renders no part of
// the agent, and every transcript query and sub-page link it builds is
// addressed by the uid. The fixture uid (`u-codex`) is not the agent's name.

import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { AgentConversationsTab } from "./AgentConversationsTab";
import type { TranscriptListParams } from "@/lib/api/agentTranscripts";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("@/lib/hooks/useAgentTranscripts", () => ({
  TRANSCRIPTS_PAGE_SIZE: 10,
  transcriptsKey: (uid: string) => ["agents", uid, "conversations"],
  useAgentTranscripts: vi.fn(),
}));

const navigateMock = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-router-dom")>()),
  useNavigate: () => navigateMock,
}));

const hooks = await import("@/lib/hooks/useAgentTranscripts");

function wrap({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

/** The path + parsed query of the last navigation the table performed. */
function lastNavigation(): { path: string; params: URLSearchParams } {
  const [path, query] = (navigateMock.mock.calls.at(-1)?.[0] as string).split("?");
  return { path, params: new URLSearchParams(query) };
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

/** Every params object the component has passed to the transcripts hook. */
function queries(): TranscriptListParams[] {
  return vi.mocked(hooks.useAgentTranscripts).mock.calls.map((c) => c[1] ?? {});
}

/** Last (name, params) the component passed to the transcripts hook. */
function lastParams(): TranscriptListParams {
  const all = queries();
  return all[all.length - 1] ?? {};
}

afterEach(() => vi.clearAllMocks());

describe("AgentConversationsTab", () => {
  test("renders a session row with title, project, count, and times", () => {
    stubTranscripts();
    render(<AgentConversationsTab uid="u-codex" />, { wrapper: wrap });
    expect(screen.getByText("Fix the login redirect bug")).toBeInTheDocument();
    expect(screen.getByText("/home/u/repo")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  test("clicking a row opens that conversation's page, addressed by its file", () => {
    stubTranscripts();
    render(<AgentConversationsTab uid="u-codex" />, { wrapper: wrap });

    fireEvent.click(screen.getByText("Fix the login redirect bug"));

    const { path, params } = lastNavigation();
    // Addressed by the agent's uid, so the link survives a rename.
    expect(path).toBe("/agents/u-codex/conversations");
    expect(params.get("path")).toBe(SESSION.source_path);
  });

  test("the table carries no per-row menu and nothing that writes", () => {
    // Open / reveal moved to the conversation's own page — a list of a thousand
    // sessions is for finding one, not for acting on each.
    stubTranscripts();
    render(<AgentConversationsTab uid="u-codex" />, { wrapper: wrap });
    expect(screen.queryByRole("button", { name: /more actions/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/open in editor/i)).not.toBeInTheDocument();
    // Read-only surface: no checkboxes (bulk select) anywhere in the table.
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
  });

  test("shows a loading state while sessions are pending", () => {
    stubTranscripts([], { isPending: true });
    render(<AgentConversationsTab uid="u-codex" />, { wrapper: wrap });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  test("shows an error state when the query fails", () => {
    stubTranscripts([], { error: new Error("request failed: 500") });
    render(<AgentConversationsTab uid="u-codex" />, { wrapper: wrap });
    expect(screen.getByText(/request failed/i)).toBeInTheDocument();
  });

  test("shows the empty message when there are no sessions", () => {
    stubTranscripts([]);
    render(<AgentConversationsTab uid="u-codex" />, { wrapper: wrap });
    expect(screen.getByText(/no conversations found/i)).toBeInTheDocument();
  });

  test("first page request carries limit/offset (paged on demand)", () => {
    stubTranscripts([SESSION], { total: 250 });
    render(<AgentConversationsTab uid="u-codex" />, { wrapper: wrap });
    expect(typeof lastParams().limit).toBe("number");
    expect(lastParams().offset).toBe(0);
  });

  test("typing in search forwards the query to the hook, once it settles", async () => {
    stubTranscripts();
    render(<AgentConversationsTab uid="u-codex" />, { wrapper: wrap });
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "alpha" } });
    await waitFor(() => expect(lastParams().q).toBe("alpha"));
  });

  test("a burst of keystrokes queries once, for the value the user stopped on", async () => {
    // On a cold reader one query is one full transcript parse, so a request per
    // keystroke is the difference between a pause and five of them.
    stubTranscripts();
    render(<AgentConversationsTab uid="u-codex" />, { wrapper: wrap });
    const box = screen.getByRole("textbox");
    for (const value of ["a", "al", "alp", "alph", "alpha"]) {
      fireEvent.change(box, { target: { value } });
    }
    // Every render so far still asks for the unfiltered list…
    expect(queries().every((p) => p.q === undefined)).toBe(true);
    await waitFor(() => expect(lastParams().q).toBe("alpha"));
    // …and no intermediate prefix was ever asked for.
    expect(
      queries()
        .filter((p) => p.q !== undefined)
        .every((p) => p.q === "alpha"),
    ).toBe(true);
  });

  test("default sort is last_activity desc; clicking 'Started' header sorts by started_at", () => {
    stubTranscripts();
    render(<AgentConversationsTab uid="u-codex" />, { wrapper: wrap });
    expect(lastParams().sort).toBe("last_activity_at");
    expect(lastParams().order).toBe("desc");
    fireEvent.click(screen.getByRole("button", { name: /sort by started/i }));
    expect(lastParams().sort).toBe("started_at");
  });

  test("re-clicking the active sort header flips the order", () => {
    stubTranscripts();
    render(<AgentConversationsTab uid="u-codex" />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("button", { name: /sort by last activity/i }));
    expect(lastParams().sort).toBe("last_activity_at");
    expect(lastParams().order).toBe("asc");
  });

  test("keys rows by source_path so duplicate session_ids stay distinct rows", () => {
    // Two rows share a session_id (subagent sidechain) but have distinct files,
    // so both the row key and the page each row opens must be the FILE.
    const dup = {
      ...SESSION,
      title: "Sidechain of the same session",
      source_path: "/home/u/.codex/sessions/2026/06/rollout-s1b.jsonl",
    };
    stubTranscripts([SESSION, dup]);
    render(<AgentConversationsTab uid="u-codex" />, { wrapper: wrap });

    fireEvent.click(screen.getByText("Fix the login redirect bug"));
    expect(lastNavigation().params.get("path")).toBe(SESSION.source_path);

    fireEvent.click(screen.getByText("Sidechain of the same session"));
    expect(lastNavigation().params.get("path")).toBe(dup.source_path);
  });

  test("stepping to the next page advances the offset by the page size", () => {
    stubTranscripts([SESSION], { total: 250 });
    render(<AgentConversationsTab uid="u-codex" />, { wrapper: wrap });
    const limit = lastParams().limit as number;
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(lastParams().offset).toBe(limit);
  });

  test("searching from a later page goes back to the first one", async () => {
    // Otherwise the stale offset outruns the narrower result set and the table
    // reads "no conversations" while matches exist.
    stubTranscripts([SESSION], { total: 250 });
    render(<AgentConversationsTab uid="u-codex" />, { wrapper: wrap });
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(lastParams().offset).toBeGreaterThan(0);

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "alpha" } });
    expect(lastParams().offset).toBe(0); // the page resets on the keystroke…
    await waitFor(() => expect(lastParams().q).toBe("alpha")); // …the query waits
    expect(lastParams().offset).toBe(0);
  });
});
