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

// The page now also renders a built-in agents section; stub its hooks so the
// page test doesn't reach the network (those hooks hit getApiClient directly).
vi.mock("@/lib/hooks/useBuiltinAgents", () => ({
  useBuiltinAgents: vi.fn(() => ({ data: [], isPending: false, error: null })),
  useCreateBuiltinAgent: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  usePatchBuiltinAgent: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useRemoveBuiltinAgent: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));
const hooks = await import("@/lib/hooks/useAgents");
const useAgentsMock = vi.mocked(hooks.useAgents);
const useAgentCandidatesMock = vi.mocked(hooks.useAgentCandidates);
const useRegisterAgentMock = vi.mocked(hooks.useRegisterAgent);
const useRemoveAgentMock = vi.mocked(hooks.useRemoveAgent);

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
  // Title + table cell render. There's a single unified agents table now (no
  // separate built-in section), so scope to the level-1 page title.
  expect(screen.getByRole("heading", { level: 1, name: /agents/i })).toBeInTheDocument();
  expect(screen.getByText("cur")).toBeInTheDocument();
  // There's a single "Add" control (no standalone Detect button).
  expect(screen.queryByRole("button", { name: /detect/i })).not.toBeInTheDocument();
  // The header add control is a dropdown; opening it then picking "Add agent"
  // opens the combined dialog, and revealing "Add manually" shows the form.
  // The trigger and the menu item share the "Add agent" label, so pick the
  // menu item (the last match — the portal-rendered popover item).
  fireEvent.click(screen.getByRole("button", { name: /add agent/i }));
  const addItems = screen.getAllByRole("button", { name: /^add agent$/i });
  fireEvent.click(addItems[addItems.length - 1]);
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

  test("renders the welcome panel when no agents exist", () => {
    stubHooks({ data: [] });
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
});
