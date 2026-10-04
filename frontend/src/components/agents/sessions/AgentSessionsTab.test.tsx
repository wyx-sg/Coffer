// src/components/agents/sessions/AgentSessionsTab.test.tsx
//
// The Sessions tab: the agent's own CLI session history beside the open
// session. The list searches the server (debounced), pages by cursor with
// "Load more", and opens a session into `?session=<source_path>` — the file,
// because session_id repeats across subagent sidechain files. The reader shows
// the session's header, a window of turns with the harness's blocks folded
// away, and pages the turns; a file that moved says so with a retry. Nothing
// here writes. The hooks are mocked at the network boundary.
import type { ReactNode } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";

import { AgentSessionsTab } from "./AgentSessionsTab";
import type { AgentOut } from "@/lib/api/agents";
import type {
  TranscriptListParams,
  TranscriptSessionDetail,
  TranscriptSessionSummary,
} from "@/lib/api/agentTranscripts";

vi.mock("@/lib/hooks/useAgentTranscripts", () => ({
  TRANSCRIPTS_PAGE_SIZE: 30,
  TRANSCRIPT_TURNS_PAGE_SIZE: 200,
  useAgentTranscripts: vi.fn(),
  useTranscriptSession: vi.fn(),
  useRefreshTranscripts: vi.fn(),
}));
const openMock = vi.fn(() => Promise.resolve());
const revealMock = vi.fn(() => Promise.resolve());
vi.mock("@/lib/fsActions", () => ({
  useFsActions: () => ({ open: openMock, reveal: revealMock }),
}));
const hooks = await import("@/lib/hooks/useAgentTranscripts");

const AGENT = {
  uid: "agt_01cx",
  type: "codex",
  name: "codex",
  display_name: "Codex",
  config_dir: "/Users/xing/.codex",
} as AgentOut;

const PATH_A = "/Users/xing/.codex/sessions/2026/06/rollout-a.jsonl";
const PATH_B = "/Users/xing/.codex/sessions/2026/06/rollout-b.jsonl";

const summary = (over: Partial<TranscriptSessionSummary>): TranscriptSessionSummary => ({
  session_id: "s1",
  title: "Fix the login redirect bug",
  project_path: "/Users/xing/repo",
  message_count: 5,
  started_at: "2026-06-01T10:00:00Z",
  last_activity_at: "2026-06-01T11:30:00Z",
  source_path: PATH_A,
  ...over,
});

const ROWS = [
  summary({}),
  // Same session_id, another file: a subagent sidechain — a distinct row.
  summary({ title: "Sidechain", source_path: PATH_B }),
];

const DETAIL: TranscriptSessionDetail = {
  ...summary({ message_count: 2 }),
  messages: [
    {
      role: "user",
      text: "<system-reminder>\nYou are in a git worktree.\n</system-reminder>\n\nwhy is the redirect looping",
      timestamp: "2026-06-01T10:00:00Z",
      truncated: false,
    },
    {
      role: "assistant",
      text: "Because the **guard** runs twice.",
      timestamp: "2026-06-01T10:00:05Z",
      truncated: true,
    },
  ],
  limit: 200,
  offset: 0,
};

const refreshMock = vi.fn();

function stubList(opts: { total?: number; rows?: TranscriptSessionSummary[]; next?: string } = {}) {
  const rows = opts.rows ?? ROWS;
  vi.mocked(hooks.useAgentTranscripts).mockImplementation(
    (_uid, params: TranscriptListParams = {}) =>
      ({
        data: {
          sessions: params.cursor
            ? [summary({ title: "Older one", source_path: "/x/c.jsonl" })]
            : rows,
          total: opts.total ?? rows.length,
          limit: params.limit ?? 30,
          next_cursor: params.cursor ? null : (opts.next ?? null),
        },
        isPending: false,
        isPlaceholderData: false,
        error: null,
      }) as unknown as ReturnType<typeof hooks.useAgentTranscripts>,
  );
  vi.mocked(hooks.useRefreshTranscripts).mockReturnValue(refreshMock);
}

function stubSession(detail: Partial<TranscriptSessionDetail> | null = {}, error?: Error) {
  const refetch = vi.fn();
  vi.mocked(hooks.useTranscriptSession).mockReturnValue({
    data: detail === null ? undefined : { ...DETAIL, ...detail },
    isPending: false,
    error: error ?? null,
    refetch,
  } as unknown as ReturnType<typeof hooks.useTranscriptSession>);
  return refetch;
}

function Location() {
  return <output data-testid="location">{useLocation().search}</output>;
}

function renderTab(search = "") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui: ReactNode = (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/agents/codex/sessions${search}`]}>
        <AgentSessionsTab agent={AGENT} />
        <Location />
      </MemoryRouter>
    </QueryClientProvider>
  );
  return render(ui);
}

const openParam = () =>
  new URLSearchParams(screen.getByTestId("location").textContent ?? "").get("session");
const listCalls = () => vi.mocked(hooks.useAgentTranscripts).mock.calls.map((c) => c[1] ?? {});

afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe("AgentSessionsTab", () => {
  test("lists sessions by title, project and count, and opens none until one is picked", () => {
    stubList();
    stubSession();
    renderTab();
    const list = within(screen.getByTestId("session-list"));
    expect(list.getByText("Fix the login redirect bug")).toBeInTheDocument();
    expect(list.getAllByText("repo · 5 messages")).toHaveLength(2);
    // Keyed by file: both rows of the shared session_id are there.
    expect(list.getByText("Sidechain")).toBeInTheDocument();
    expect(screen.getByText(/pick a session/i)).toBeInTheDocument();
    expect(vi.mocked(hooks.useTranscriptSession)).not.toHaveBeenCalled();
  });

  test("the first page asks for one page, newest activity first, with no cursor", () => {
    stubList();
    renderTab();
    expect(listCalls()).toContainEqual(
      expect.objectContaining({
        limit: 30,
        sort: "last_activity_at",
        order: "desc",
        cursor: undefined,
      }),
    );
  });

  test("clicking a row opens it into ?session=, addressed by its file", () => {
    stubList();
    stubSession();
    renderTab();
    fireEvent.click(screen.getByText("Sidechain"));
    expect(openParam()).toBe(PATH_B);
    expect(vi.mocked(hooks.useTranscriptSession)).toHaveBeenCalledWith("agt_01cx", PATH_B, 0);
  });

  test("the list leads with a search and a Project pill; no count, sort or refresh", () => {
    stubList();
    renderTab();
    expect(screen.getByRole("textbox", { name: "Search sessions" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^project$/i })).toBeInTheDocument();
    expect(screen.queryByText("2 sessions")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /refresh$/i })).not.toBeInTheDocument();
  });

  test("searching asks the listing for matches, starting the pages over", async () => {
    stubList();
    renderTab();
    fireEvent.change(screen.getByRole("textbox", { name: "Search sessions" }), {
      target: { value: "login" },
    });
    await waitFor(() =>
      expect(listCalls()).toContainEqual(expect.objectContaining({ q: "login" })),
    );
  });

  test("the Project pill lists the projects and filters to the one chosen", () => {
    stubList({
      rows: [
        summary({}),
        summary({ title: "Other", project_path: "/Users/xing/scratch", source_path: PATH_B }),
      ],
    });
    renderTab();
    fireEvent.click(screen.getByRole("button", { name: /^project$/i }));
    const options = screen.getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["All projects", "repo", "scratch"]);
    fireEvent.click(screen.getByRole("option", { name: "scratch" }));
    expect(screen.getByRole("button", { name: "Project: scratch" })).toBeInTheDocument();
    expect(listCalls()).toContainEqual(expect.objectContaining({ project: "/Users/xing/scratch" }));
  });

  test("the Project pill searches the projects by their full path", () => {
    stubList({
      rows: [
        summary({}),
        summary({ title: "Other", project_path: "/Users/xing/scratch", source_path: PATH_B }),
      ],
    });
    renderTab();
    fireEvent.click(screen.getByRole("button", { name: /^project$/i }));
    const search = screen.getByRole("textbox", { name: "Search projects" });
    fireEvent.change(search, { target: { value: "USERS/XING/SCR" } });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      "All projects",
      "scratch",
    ]);
    fireEvent.change(search, { target: { value: "nothing-like-this" } });
    expect(screen.getByText("No matching project")).toBeInTheDocument();
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["All projects"]);
  });

  test("the divider between the list and the reader can be dragged", () => {
    stubList();
    renderTab();
    expect(screen.getByRole("separator", { name: /resize the list/i })).toBeInTheDocument();
  });

  test("Load more reads the next page with the cursor the last one returned", () => {
    stubList({ next: "cursor-2", total: 3 });
    renderTab();
    fireEvent.click(screen.getByRole("button", { name: /load more/i }));
    expect(listCalls()).toContainEqual(expect.objectContaining({ cursor: "cursor-2" }));
    expect(screen.getByText("Older one")).toBeInTheDocument();
  });

  test("the open session shows its header, the turns and the file actions", () => {
    stubList();
    stubSession();
    renderTab(`?session=${encodeURIComponent(PATH_A)}`);
    expect(screen.getByRole("heading", { name: "Fix the login redirect bug" })).toBeInTheDocument();
    expect(screen.getByText("~/repo")).toBeInTheDocument();
    expect(screen.getByText("2 messages")).toBeInTheDocument();
    // "Read-only" lives in the meta line; there is no footer note and no prompts pane.
    expect(screen.getByText("Read-only")).toBeInTheDocument();
    expect(screen.queryByText(/coffer never writes transcripts/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/your prompts/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^turns /i)).not.toBeInTheDocument();
    const turns = within(screen.getByTestId("transcript-turns"));
    expect(turns.getByText("Codex")).toBeInTheDocument();
    expect(turns.getByText("You")).toBeInTheDocument();
    // The harness's blocks are folded behind a disclosure, the question leads.
    expect(turns.getByText("why is the redirect looping")).toBeInTheDocument();
    expect(turns.getByText(/harness context/i).tagName).toBe("SUMMARY");
    expect(turns.getByText(/too long to show in full/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /open in editor/i }));
    expect(openMock).toHaveBeenCalledWith(PATH_A, expect.anything());
    fireEvent.click(screen.getByRole("button", { name: /reveal in finder/i }));
    expect(revealMock).toHaveBeenCalledWith(PATH_A);
    expect(screen.queryByRole("button", { name: /^(save|edit|delete)$/i })).toBeNull();
  });

  test("a long session pages its turns; a short one offers no paging", () => {
    stubList();
    stubSession({ message_count: 500 });
    renderTab(`?session=${encodeURIComponent(PATH_A)}`);
    expect(screen.getByText("Turns 1–2 of 500")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /earlier turns/i })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /later turns/i }));
    expect(vi.mocked(hooks.useTranscriptSession).mock.calls.at(-1)).toEqual([
      "agt_01cx",
      PATH_A,
      200,
    ]);
  });

  test("a session that fails to load says the file moved, with Retry and Refresh list", () => {
    stubList();
    const refetch = stubSession(null, new Error("gone"));
    renderTab(`?session=${encodeURIComponent(PATH_A)}`);
    expect(screen.getByText(/couldn’t load this session/i)).toBeInTheDocument();
    expect(screen.getByText(/was moved or deleted after the list was read/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(refetch).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /refresh list/i }));
    expect(refreshMock).toHaveBeenCalled();
  });

  test("no sessions at all says where the agent keeps them, in a bordered box", () => {
    stubList({ rows: [], total: 0 });
    renderTab();
    expect(screen.getByText("No sessions yet")).toBeInTheDocument();
    expect(
      screen.getByText(
        /codex keeps its sessions in ~\/\.codex\/sessions\. run codex in a project/i,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
