// frontend/src/components/chat/HistoryPanel.test.tsx
// Plain unit test (no acceptance marker): the history search renders hits and
// selecting one browses that session's scrubbed turns read-only.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { HistoryPanel } from "./HistoryPanel";
import type { HistorySearchOut, HistorySessionOut } from "@/lib/api/history";

// Drive the panel through the API module so the hooks exercise their real
// query wiring (enabled gating, key shape) against a mocked transport.
const search = vi.fn();
const browseSession = vi.fn();
const reindex = vi.fn();
vi.mock("@/lib/api/history", () => ({
  historyApi: {
    search: (...a: unknown[]) => search(...a),
    browseSession: (...a: unknown[]) => browseSession(...a),
    reindex: (...a: unknown[]) => reindex(...a),
    reset: vi.fn(),
  },
}));

vi.mock("@/components/ui/toast", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/ui/toast")>();
  return {
    ...actual,
    useToast: () => ({
      toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
      dismiss: vi.fn(),
    }),
  };
});

const SEARCH_RESULT: HistorySearchOut = {
  query: "oauth",
  hits: [
    {
      agent_type: "claude-code",
      session_id: "s-1",
      project_path: "/repo/coffer",
      started_at: "2026-06-01T00:00:00Z",
      title: "OAuth token refresh",
      snippet: "we rotated the oauth refresh token",
      score: 0.9,
    },
  ],
};

const SESSION_RESULT: HistorySessionOut = {
  session: {
    agent_type: "claude-code",
    session_id: "s-1",
    project_path: "/repo/coffer",
    started_at: "2026-06-01T00:00:00Z",
    title: "OAuth token refresh",
    message_count: 2,
  },
  turns: [
    { role: "user", text: "how do we refresh the token?" },
    { role: "assistant", text: "rotate it via the channels API" },
  ],
};

function renderPanel() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={qc}>
      <HistoryPanel onClose={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe("HistoryPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    search.mockResolvedValue(SEARCH_RESULT);
    browseSession.mockResolvedValue(SESSION_RESULT);
  });

  test("does not search until the query box is non-empty", () => {
    renderPanel();
    expect(search).not.toHaveBeenCalled();
  });

  test("renders search hits and browses the selected session read-only", async () => {
    renderPanel();

    fireEvent.change(screen.getByRole("textbox", { name: /search history/i }), {
      target: { value: "oauth" },
    });

    const hit = await screen.findByText("OAuth token refresh");
    expect(search).toHaveBeenCalledWith("oauth", {});
    expect(screen.getByText("claude-code · /repo/coffer")).toBeInTheDocument();
    expect(screen.getByText(/rotated the oauth refresh token/i)).toBeInTheDocument();

    fireEvent.click(hit);

    await waitFor(() => expect(browseSession).toHaveBeenCalledWith("claude-code", "s-1"));
    expect(await screen.findByText("how do we refresh the token?")).toBeInTheDocument();
    expect(screen.getByText("rotate it via the channels API")).toBeInTheDocument();
    // Read-only: no composer / message input in the browse view.
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });
});
