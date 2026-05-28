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
  useDetectAgents: vi.fn(),
  useRegisterAgent: vi.fn(),
  useRemoveAgent: vi.fn(),
}));
const hooks = await import("@/lib/hooks/useAgents");
const useAgentsMock = vi.mocked(hooks.useAgents);
const useDetectAgentsMock = vi.mocked(hooks.useDetectAgents);
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
  useDetectAgentsMock.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue({}),
    isPending: false,
  } as unknown as ReturnType<typeof hooks.useDetectAgents>);
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
        type: "cursor",
        skill_dir: "/home/u/.cursor/skills",
        skill_dir_override: null,
        auto_detected: true,
        enabled: true,
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
  // Clicking "Add agent" reveals the registration form.
  fireEvent.click(screen.getByRole("button", { name: /add agent/i }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: /^register$/i })).toBeInTheDocument(),
  );
});

describe("AgentsPage", () => {
  afterEach(() => vi.clearAllMocks());

  test("renders the loading state when the query is pending", () => {
    stubHooks({ isPending: true });
    render(<AgentsPage />, { wrapper: wrap(null) });
    // The card body shows the loading copy.
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  test("renders the empty-state card when no agents exist", () => {
    stubHooks({ data: [] });
    render(<AgentsPage />, { wrapper: wrap(null) });
    expect(screen.getByText(/no agents registered/i)).toBeInTheDocument();
  });

  test("renders the error card when the query errors", () => {
    stubHooks({
      error: { code: "BOOM", message: "kaboom" },
    });
    render(<AgentsPage />, { wrapper: wrap(null) });
    expect(screen.getByText(/failed to load agents/i)).toBeInTheDocument();
  });
});
