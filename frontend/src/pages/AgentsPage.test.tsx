// frontend/src/pages/AgentsPage.test.tsx
//
// TEST25-206: AgentsPage renders the table + the add-form toggle. We mock
// the agents hooks so the page doesn't depend on a running daemon.
//
// Carries the acceptance marker for spec scenario "desktop app agents
// page" — the surface that spec agent-registry §US 4 requires.

import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";
import { AgentsPage } from "./AgentsPage";
import { TooltipProvider } from "@/components/ui/tooltip";
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
// The table's availability column reads the provider registry.
vi.mock("@/lib/hooks/useAgentProviders", () => ({
  useAgentProviders: vi.fn(() => ({
    data: [{ agent_key: "codex", display_name: "Codex", available: true }],
    isPending: false,
  })),
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
      <TooltipProvider>
        <MemoryRouter>{children ?? ui}</MemoryRouter>
      </TooltipProvider>
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

acceptance("agent-registry", "desktop app agents page", async () => {
  stubHooks({
    data: [
      {
        uid: "u-cur",
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
  expect(screen.getByRole("heading", { name: /^agents$/i })).toBeInTheDocument();
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

  test("keeps the header up over skeleton rows while the query is pending", () => {
    stubHooks({ isPending: true });
    render(<AgentsPage />, { wrapper: wrap(null) });
    // No bare "Loading…" card: the title is already there over a busy table.
    expect(screen.getByRole("heading", { name: /agents/i })).toBeInTheDocument();
    expect(screen.getByRole("table")).toHaveAttribute("aria-busy", "true");
    expect(screen.getAllByTestId("skeleton-row").length).toBeGreaterThan(0);
    expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
  });

  test("renders the welcome panel when no agents exist", () => {
    stubHooks({ data: [] });
    // Welcome panel only when truly empty — no registry agents.
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

  test("renders only managed agents — no built-in agent card", () => {
    stubHooks({
      data: [
        {
          uid: "u-cur",
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
    // The managed agent renders; the retired built-in persona does not.
    expect(screen.getByText("cur")).toBeInTheDocument();
    expect(screen.queryByText("Coffer Assistant")).not.toBeInTheDocument();
    expect(screen.queryByText("Built-in")).not.toBeInTheDocument();
  });
});
