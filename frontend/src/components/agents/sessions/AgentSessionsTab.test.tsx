// components/agents/sessions/AgentSessionsTab.test.tsx — the agent's Sessions
// tab: the agent's own sessions as the same rows the Conversations page uses,
// asked of the agent through /agents/{uid}/sessions; the fake daemon answers at
// the network boundary so the request functions, hooks and cache are real.
import { beforeEach, describe, expect, test } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { fakeApi } from "@/test/fakeApi";
import { acceptance } from "@/test/acceptance";
import { makeBinding, makeSession } from "@/test/conversationFixtures";
import { makeAgent } from "@/test/skillsPageKit";
import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { AgentSession } from "@/lib/api/agentSessions";
import { AgentSessionsTab } from "./AgentSessionsTab";

const call = fakeApi();
const agent = makeAgent({ uid: "ag-cc" });

let sessions: AgentSession[] = [];
const page = (rows: AgentSession[], next: string | null = null) => ({
  sessions: rows,
  next_cursor: next,
  total: next ? null : rows.length,
});

function renderTab() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <TooltipProvider>
            <AgentSessionsTab agent={agent} />
          </TooltipProvider>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const row = (title: string) => screen.getByText(title).closest("li") as HTMLElement;
/** A row by its session id: it stays findable while its title is an input. */
const rowOf = (id: string) => document.querySelector(`li[data-session="${id}"]`) as HTMLElement;
const sessionCalls = (method: string) =>
  call.mock.calls.filter(([, o]) => o.method === method).map(([path, o]) => ({ path, ...o }));

beforeEach(() => {
  call.mockReset();
  sessions = [
    makeSession({ session_id: "abc-123", title: "Alpha rollout", cwd: "/work/api" }),
    makeSession({
      session_id: "def-456",
      title: "Gamma",
      cwd: "/work/alpha-api",
      last_activity_at: "2026-01-02T00:00:00Z",
    }),
  ];
  call.mockImplementation(async (path, opts) => {
    if (opts.method === "GET" && path.startsWith("/agents/ag-cc/sessions")) {
      const q = new URL(`http://x${path}`).searchParams.get("q")?.toLowerCase() ?? "";
      return page(
        sessions.filter(
          (s) => !q || s.title.toLowerCase().includes(q) || (s.cwd ?? "").toLowerCase().includes(q),
        ),
      );
    }
    return undefined;
  });
});

describe("AgentSessionsTab", () => {
  test("lists the agent's sessions with title, directory and no agent column", async () => {
    renderTab();
    await screen.findByText("Alpha rollout");
    expect(row("Alpha rollout")).toHaveTextContent("/work/api");
    expect(row("Gamma")).toHaveTextContent("/work/alpha-api");
    expect(row("Alpha rollout")).not.toHaveTextContent("Claude Code");
    expect(sessionCalls("GET")[0].path).toContain("/agents/ag-cc/sessions?limit=30");
    expect(screen.queryByRole("heading")).toBeNull();
  });

  acceptance(
    "agent-registry",
    "a session that is a channel conversation shows its channel",
    async () => {
      sessions = [
        makeSession({
          session_id: "s-chan",
          title: "From SeaTalk",
          conversation_id: "conv-1",
          running: true,
          channel_binding: makeBinding(),
        }),
        makeSession({ session_id: "s-plain", title: "Plain one" }),
      ];
      call.mockImplementation(async (_path, opts) =>
        opts.method === "GET" ? page(sessions) : undefined,
      );
      renderTab();
      await screen.findByText("From SeaTalk");
      expect(row("From SeaTalk")).toHaveTextContent("SeaTalk · DM");
      expect(row("From SeaTalk")).toHaveTextContent("Running");
      expect(within(row("From SeaTalk")).getByRole("button", { name: /^Stop/ })).toBeVisible();
      expect(row("Plain one")).not.toHaveTextContent("SeaTalk");
      expect(row("Plain one")).not.toHaveTextContent("Running");
      expect(within(row("Plain one")).queryByRole("button", { name: /^Stop/ })).toBeNull();
    },
  );

  acceptance("agent-registry", "the sessions list searches title and directory", async () => {
    renderTab();
    await screen.findByText("Alpha rollout");
    fireEvent.change(screen.getByRole("textbox", { name: "Search titles and directories" }), {
      target: { value: "alpha" },
    });
    await waitFor(() => expect(sessionCalls("GET").at(-1)?.path).toContain("q=alpha"));
    // "Alpha rollout" matches by title, "Gamma" by its directory.
    expect(await screen.findByText("Gamma")).toBeInTheDocument();
    expect(screen.getByText("Alpha rollout")).toBeInTheDocument();
  });

  test("a search that matches nothing says so and keeps the query", async () => {
    renderTab();
    await screen.findByText("Alpha rollout");
    fireEvent.change(screen.getByRole("textbox", { name: "Search titles and directories" }), {
      target: { value: "zzz" },
    });
    expect(await screen.findByText("No sessions match.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Search titles and directories" })).toHaveValue(
      "zzz",
    );
  });

  test("an agent with no sessions says where it keeps them", async () => {
    sessions = [];
    renderTab();
    expect(await screen.findByText("No sessions yet")).toBeInTheDocument();
    expect(screen.getByText(/Run claude in a project/)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  test("pages by cursor as it is scrolled", async () => {
    call.mockImplementation(async (path, opts) => {
      if (opts.method !== "GET") return undefined;
      return new URL(`http://x${path}`).searchParams.get("cursor") === "c1"
        ? page([makeSession({ session_id: "s2", title: "Second page" })])
        : page([makeSession({ session_id: "s1", title: "First page" })], "c1");
    });
    renderTab();
    await screen.findByText("First page");
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Second page")).toBeInTheDocument();
    expect(sessionCalls("GET").at(-1)?.path).toContain("cursor=c1");
  });

  test("a list that fails to load says so, with Retry", async () => {
    const { ApiError } = await import("@/lib/api/errors");
    call.mockImplementationOnce(async () => {
      throw new ApiError("INTERNAL_ERROR", "boom");
    });
    renderTab();
    expect(await screen.findByText("Couldn’t read the sessions")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Alpha rollout")).toBeInTheDocument();
  });

  acceptance("agent-registry", "deleting a session asks first", async () => {
    renderTab();
    await screen.findByText("Alpha rollout");
    fireEvent.click(
      within(row("Alpha rollout")).getByRole("button", { name: "More actions for Alpha rollout" }),
    );
    fireEvent.click(await screen.findByRole("menuitem", { name: "Delete…" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("deleted from the agent and cannot be recovered");
    expect(sessionCalls("DELETE")).toEqual([]);
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(sessionCalls("DELETE")).toEqual([]);
  });

  acceptance("agent-registry", "the Sessions tab calls the session routes", async () => {
    renderTab();
    await screen.findByText("Alpha rollout");
    // Rename from the row's ⋯ menu, in place.
    fireEvent.click(
      within(row("Alpha rollout")).getByRole("button", { name: "More actions for Alpha rollout" }),
    );
    fireEvent.click(await screen.findByRole("menuitem", { name: "Rename" }));
    const input = await within(rowOf("abc-123")).findByRole("textbox", { name: "Title" });
    fireEvent.change(input, { target: { value: "Beta rollout" } });
    sessions = [{ ...sessions[0], title: "Beta rollout" }, sessions[1]];
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(sessionCalls("PATCH")).toHaveLength(1));
    expect(sessionCalls("PATCH")[0]).toMatchObject({
      path: "/agents/ag-cc/sessions/abc-123",
      body: { title: "Beta rollout" },
    });
    await screen.findByText("Beta rollout");
    // Then delete it.
    fireEvent.click(
      within(row("Beta rollout")).getByRole("button", { name: "More actions for Beta rollout" }),
    );
    fireEvent.click(await screen.findByRole("menuitem", { name: "Delete…" }));
    sessions = [sessions[1]];
    fireEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete session" }),
    );
    await waitFor(() => expect(sessionCalls("DELETE")).toHaveLength(1));
    expect(sessionCalls("DELETE")[0].path).toBe("/agents/ag-cc/sessions/abc-123");
    await waitFor(() => expect(screen.queryByText("Beta rollout")).toBeNull());
  });
});
