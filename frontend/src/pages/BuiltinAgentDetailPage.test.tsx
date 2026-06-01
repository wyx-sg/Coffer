// frontend/src/pages/BuiltinAgentDetailPage.test.tsx — spec 008.
// The built-in agent detail page mirrors the external one: a header with
// edit/delete (delete surfaces the 409 inline), and Overview / Config / Skill /
// MCP tabs. Model + credential_ref are read-only (set in Settings → AI).
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ApiError } from "@/lib/api/errors";

vi.mock("@/lib/hooks/useBuiltinAgents", () => ({
  useBuiltinAgent: vi.fn(),
  useRemoveBuiltinAgent: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  // The edit form (opened from this page) uses these.
  useCreateBuiltinAgent: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  usePatchBuiltinAgent: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
}));
vi.mock("@/lib/hooks/useSkills", () => ({
  useSkills: vi.fn(() => ({ data: [], isPending: false, error: null })),
}));
vi.mock("@/lib/hooks/useResources", () => ({
  useResources: vi.fn(() => ({ data: [], isPending: false, error: null })),
}));

const { useBuiltinAgent, useRemoveBuiltinAgent } = await import("@/lib/hooks/useBuiltinAgents");
const { BuiltinAgentDetailPage } = await import("./BuiltinAgentDetailPage");
const useBuiltinAgentMock = vi.mocked(useBuiltinAgent);
const useRemoveMock = vi.mocked(useRemoveBuiltinAgent);

const AGENT = {
  ref: "builtin_agent:coffer",
  kind: "builtin_agent",
  name: "coffer",
  description: "Coffer's own agent",
  config: {
    model: "anthropic:claude-sonnet-4-6",
    credential_ref: "ai/anthropic",
    use_gateway: true,
    confirm_tools: ["*delete*"],
  },
  enabled: true,
  created_at: "2026-05-28T00:00:00Z",
  updated_at: "2026-05-28T00:00:00Z",
};

function mockLoaded() {
  useBuiltinAgentMock.mockReturnValue({
    data: AGENT,
    isPending: false,
    error: null,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof useBuiltinAgent>);
}

function renderAt() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/agents/builtin/coffer"]}>
        <Routes>
          <Route path="/agents/builtin/:name" element={<BuiltinAgentDetailPage />} />
          <Route path="/agents" element={<div>agents list</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("BuiltinAgentDetailPage", () => {
  test("renders the header and the Overview/Config/Skill/MCP tabs", () => {
    mockLoaded();
    renderAt();
    expect(screen.getByRole("heading", { name: "coffer" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /overview/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^config$/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^skills$/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /mcp servers/i })).toBeInTheDocument();
  });

  test("the overview shows the read-only model and that the provider key is configured", () => {
    mockLoaded();
    renderAt();
    // Model appears (read-only) and the provider-key status reads "Configured".
    expect(screen.getAllByText("anthropic:claude-sonnet-4-6").length).toBeGreaterThan(0);
    expect(screen.getByText(/configured \(anthropic\)/i)).toBeInTheDocument();
  });

  test("clicking Edit opens the behaviour-only edit form (no model field)", () => {
    mockLoaded();
    renderAt();
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    // The form no longer has a model input — model lives in Settings → AI.
    expect(screen.queryByDisplayValue("anthropic:claude-sonnet-4-6")).not.toBeInTheDocument();
  });

  test("deleting surfaces the last-agent 409 inline", () => {
    const mutate = vi.fn((_name, opts: { onError: (e: unknown) => void }) => {
      opts.onError(
        new ApiError("CANNOT_DELETE_LAST_BUILTIN_AGENT", "cannot delete the last built-in agent"),
      );
    });
    useRemoveMock.mockReturnValue({
      mutate,
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveBuiltinAgent>);
    mockLoaded();
    renderAt();
    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));
    expect(mutate).toHaveBeenCalled();
    expect(within(dialog).getByRole("alert")).toHaveTextContent(/last built-in agent/i);
  });

  test("shows a not-found message when the agent fails to load", () => {
    useBuiltinAgentMock.mockReturnValue({
      data: undefined,
      isPending: false,
      error: { code: "RESOURCE_NOT_FOUND", message: "nope" },
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useBuiltinAgent>);
    renderAt();
    expect(screen.getByText(/failed to load built-in agent/i)).toBeInTheDocument();
  });
});
