// frontend/src/pages/AgentsPage.test.tsx
//
// TEST25-206: AgentsPage renders the table + the add-form toggle. We mock
// the agents hooks so the page doesn't depend on a running daemon.
//
// Carries the acceptance marker for spec scenario "desktop app agents
// page" — the surface that spec 004 §US 4 requires.

import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";
import { AgentsPage } from "./AgentsPage";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: vi.fn(),
  useAgentCandidates: vi.fn(),
  useRegisterAgent: vi.fn(),
  useRemoveAgent: vi.fn(),
  // The agents table's "Coffer MCP" column renders a per-row status badge.
  useAgentMcpStatus: vi.fn(() => ({ data: { installed: false }, isPending: false })),
  useAgentMcpInstall: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));
vi.mock("@/lib/hooks/useChatAgents", () => ({
  useChatAgents: vi.fn(),
}));
const hooks = await import("@/lib/hooks/useAgents");
const useAgentsMock = vi.mocked(hooks.useAgents);
const useAgentCandidatesMock = vi.mocked(hooks.useAgentCandidates);
const useRegisterAgentMock = vi.mocked(hooks.useRegisterAgent);
const useRemoveAgentMock = vi.mocked(hooks.useRemoveAgent);
const chatHooks = await import("@/lib/hooks/useChatAgents");
const useChatAgentsMock = vi.mocked(chatHooks.useChatAgents);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children ?? ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function stubHooks(opts: { data?: unknown; isPending?: boolean; error?: unknown }) {
  useAgentsMock.mockReturnValue({
    data: opts.data,
    isPending: opts.isPending ?? false,
    error: opts.error ?? null,
    refetch: vi.fn().mockResolvedValue({}),
  } as unknown as ReturnType<typeof hooks.useAgents>);
  useAgentCandidatesMock.mockReturnValue({
    data: [],
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof hooks.useAgentCandidates>);
  useRegisterAgentMock.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue({}),
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof hooks.useRegisterAgent>);
  useRemoveAgentMock.mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof hooks.useRemoveAgent>);
  // By default the chat-agents call surfaces the built-in assistant.
  useChatAgentsMock.mockReturnValue({
    data: [{ agent_key: "builtin", display_name: "Coffer Assistant", available: true }],
  } as unknown as ReturnType<typeof chatHooks.useChatAgents>);
}

afterEach(() => vi.clearAllMocks());

acceptance("004-agent-registry", "desktop app agents page", async () => {
  stubHooks({
    data: [
      {
        name: "cur",
        type: "codex",
        config_dir: "/home/u/.codex",
        description: null,
        created_at: "2026-05-22T00:00:00Z",
        updated_at: "2026-05-22T00:00:00Z",
      },
    ],
  });
  render(<AgentsPage />, { wrapper: wrap(null) });
  // Title + table cell render.
  expect(screen.getByRole("heading", { name: /agents/i })).toBeInTheDocument();
  expect(screen.getByText("cur")).toBeInTheDocument();
  // There's a single "Add agent" button (no standalone Detect button).
  expect(screen.queryByRole("button", { name: /detect/i })).not.toBeInTheDocument();
  // Clicking "Add agent" opens the combined dialog; revealing "Add manually"
  // exposes the registration form.
  fireEvent.click(screen.getByRole("button", { name: /add agent/i }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: /add manually/i })).toBeInTheDocument(),
  );
  fireEvent.click(screen.getByRole("button", { name: /add manually/i }));
  expect(screen.getByRole("button", { name: /^register$/i })).toBeInTheDocument();
});

describe("AgentsPage", () => {
  afterEach(() => vi.clearAllMocks());

  test("renders the loading state when the query is pending", () => {
    stubHooks({ isPending: true });
    render(<AgentsPage />, { wrapper: wrap(null) });
    // The card body shows the loading copy.
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  test("renders the welcome panel when no agents and no built-in exist", () => {
    stubHooks({ data: [] });
    // Welcome panel only when truly empty — no registry agents AND no built-in.
    useChatAgentsMock.mockReturnValue({
      data: undefined,
    } as unknown as ReturnType<typeof chatHooks.useChatAgents>);
    render(<AgentsPage />, { wrapper: wrap(null) });
    expect(screen.getByText(/manage your local ai agents/i)).toBeInTheDocument();
    // The welcome panel offers the single "Add agent" next step (no standalone
    // Detect button — detection lives inside the Add dialog now).
    expect(screen.getByRole("button", { name: /add agent/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /detect/i })).not.toBeInTheDocument();
  });

  test("renders the error card when the query errors", () => {
    stubHooks({
      error: { code: "BOOM", message: "kaboom" },
    });
    render(<AgentsPage />, { wrapper: wrap(null) });
    expect(screen.getByText(/failed to load agents/i)).toBeInTheDocument();
  });

  test("surfaces the built-in Coffer Assistant as a pinned table row (no start-chat)", () => {
    stubHooks({ data: [] });
    render(<AgentsPage />, { wrapper: wrap(null) });
    // Built-in now rides the agents table as a row, marked Built-in, with no
    // delete and no standalone "start chatting" launcher.
    expect(screen.getByText("Coffer Assistant")).toBeInTheDocument();
    expect(screen.getByText(/built-in/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /start chatting/i })).not.toBeInTheDocument();
  });

  test("omits the built-in section when the chat-agents call fails", () => {
    stubHooks({ data: [] });
    useChatAgentsMock.mockReturnValue({
      data: undefined,
    } as unknown as ReturnType<typeof chatHooks.useChatAgents>);
    render(<AgentsPage />, { wrapper: wrap(null) });
    expect(screen.queryByText("Coffer Assistant")).not.toBeInTheDocument();
    // The rest of the page still renders.
    expect(screen.getByRole("heading", { name: /^agents$/i })).toBeInTheDocument();
  });
});
