// frontend/src/pages/AgentConversationPage.test.tsx
//
// One conversation's page: the session header, the turns rendered as a
// dialogue, the open / reveal actions that used to sit in the table's "⋯" menu,
// and the turn paging that keeps a multi-megabyte transcript from arriving at
// once. The session is read from `?path=` — the transcript FILE — because
// session_id repeats across subagent sidechain files.
//
// We mock the hook at the network boundary and the fs actions (their own suite
// covers the transport), so this asserts what the page asks for and shows.

import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AgentConversationPage } from "./AgentConversationPage";
import type { TranscriptSessionDetail } from "@/lib/api/agentTranscripts";

vi.mock("@/lib/hooks/useAgentTranscripts", () => ({
  TRANSCRIPT_TURNS_PAGE_SIZE: 200,
  useTranscriptSession: vi.fn(),
}));

const openMock = vi.fn(() => Promise.resolve());
const revealMock = vi.fn(() => Promise.resolve());
vi.mock("@/lib/fsActions", () => ({
  useFsActions: () => ({ open: openMock, reveal: revealMock }),
}));

const hooks = await import("@/lib/hooks/useAgentTranscripts");

const SOURCE_PATH = "/home/u/.codex/sessions/2026/06/rollout-s1.jsonl";

const SESSION: TranscriptSessionDetail = {
  session_id: "s1",
  title: "Fix the login redirect bug",
  project_path: "/home/u/repo",
  message_count: 2,
  started_at: "2026-06-01T10:00:00Z",
  last_activity_at: "2026-06-01T11:30:00Z",
  source_path: SOURCE_PATH,
  messages: [
    {
      role: "user",
      text: "why is the redirect looping",
      timestamp: "2026-06-01T10:00:00Z",
      truncated: false,
    },
    {
      role: "assistant",
      text: "Because the **guard** runs twice.",
      timestamp: "2026-06-01T10:00:05Z",
      truncated: false,
    },
  ],
  limit: 200,
  offset: 0,
};

function stub(
  session: Partial<TranscriptSessionDetail> | null = {},
  opts: { isPending?: boolean; error?: Error | null } = {},
) {
  vi.mocked(hooks.useTranscriptSession).mockReturnValue({
    data: session === null || opts.isPending ? undefined : { ...SESSION, ...session },
    isPending: opts.isPending ?? false,
    error: opts.error ?? null,
  } as unknown as ReturnType<typeof hooks.useTranscriptSession>);
}

function renderAt(search = `?path=${encodeURIComponent(SOURCE_PATH)}`) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/agents/codex/conversations${search}`]}>
        <Routes>
          <Route path="/agents/:name/conversations" element={<AgentConversationPage />} />
          <Route path="/agents/:name" element={<div>agent detail</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("AgentConversationPage", () => {
  test("reads the session named by ?path= — the file, not the session id", () => {
    stub();
    renderAt();
    expect(vi.mocked(hooks.useTranscriptSession)).toHaveBeenCalledWith("codex", SOURCE_PATH, 0);
  });

  test("renders the header and the turns as a dialogue", () => {
    stub();
    renderAt();
    expect(screen.getByRole("heading", { name: "Fix the login redirect bug" })).toBeInTheDocument();
    expect(screen.getByText("/home/u/repo")).toBeInTheDocument();
    // Scoped to the dialogue: the same prompt is also the outline's first
    // entry, so an unscoped query now matches the index as well as the turn.
    expect(
      within(screen.getByTestId("transcript-turns")).getByText("why is the redirect looping"),
    ).toBeInTheDocument();
    // The assistant's markdown is rendered, not shown with its asterisks.
    expect(screen.getByText("guard").tagName).toBe("STRONG");
  });

  test("folds the harness's blocks away and leads with the question", () => {
    // "Like a real back-and-forth" (what this page was asked for) cannot mean
    // opening every other turn with eight lines of machinery the person did
    // not type. It is folded, not dropped: the record stays complete.
    stub({
      messages: [
        {
          role: "user",
          text: "<system-reminder>\nYou are in a git worktree.\n</system-reminder>\n\nwhy is the redirect looping",
          timestamp: null,
          truncated: false,
        },
      ],
    });
    renderAt();

    const turns = within(screen.getByTestId("transcript-turns"));
    expect(turns.getByText("why is the redirect looping")).toBeInTheDocument();
    // Present but behind a disclosure, not inline in the bubble.
    const disclosure = turns.getByText(/harness context/i);
    expect(disclosure.tagName).toBe("SUMMARY");
    expect(turns.getByText(/You are in a git worktree/)).toBeInTheDocument();
  });

  test("says how much of the conversation is on screen", () => {
    // A reader looking at the first 200 turns of 812 must be told so, or a
    // short page reads as a short conversation.
    stub({ message_count: 812, offset: 0 });
    renderAt();
    expect(screen.getByText(/turns 1–2 of 812/i)).toBeInTheDocument();
  });

  test("offers open-in-editor and reveal on the transcript file", () => {
    // These are the affordances that left the table's ⋯ menu; they must exist
    // here or the change removed them from the product.
    stub();
    renderAt();
    fireEvent.click(screen.getByRole("button", { name: /open in editor/i }));
    expect(openMock).toHaveBeenCalledWith(SOURCE_PATH, expect.anything());
    fireEvent.click(screen.getByRole("button", { name: /reveal in finder/i }));
    expect(revealMock).toHaveBeenCalledWith(SOURCE_PATH);
  });

  test("paging forward asks for the next window of turns", () => {
    stub({ message_count: 500 });
    renderAt();
    fireEvent.click(screen.getByRole("button", { name: /later turns/i }));
    expect(vi.mocked(hooks.useTranscriptSession).mock.calls.at(-1)).toEqual([
      "codex",
      SOURCE_PATH,
      200,
    ]);
  });

  test("does not offer paging when the whole conversation is on screen", () => {
    stub();
    renderAt();
    expect(screen.queryByRole("button", { name: /later turns/i })).not.toBeInTheDocument();
  });

  test("a truncated turn says so rather than showing a silently short one", () => {
    stub({
      messages: [{ role: "user", text: "xxx", timestamp: null, truncated: true }],
    });
    renderAt();
    expect(screen.getByText(/too long to show in full/i)).toBeInTheDocument();
  });

  test("a failed read shows the error and still offers the way back", () => {
    stub(null, { error: new Error("request failed: 404") });
    renderAt();
    expect(screen.getByRole("alert")).toHaveTextContent(/request failed/i);
    expect(screen.getByRole("button", { name: /back to/i })).toBeInTheDocument();
  });

  test("back returns to the tab the row was on, not to the agent's overview", () => {
    stub();
    renderAt();
    fireEvent.click(screen.getByRole("button", { name: /back to/i }));
    expect(screen.getByText("agent detail")).toBeInTheDocument();
  });
});
