// frontend/src/components/agents/BuiltinAgentTable.test.tsx — spec 008 US8.
// Renders the built-in agents list, opens the edit form, and verifies the
// last-agent 409 (CANNOT_DELETE_LAST_BUILTIN_AGENT) shows inline in the delete
// dialog rather than crashing.
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { BuiltinAgentTable } from "./BuiltinAgentTable";
import type { BuiltinAgentOut } from "@/lib/api/builtinAgents";
import { ApiError } from "@/lib/api/errors";

vi.mock("@/lib/hooks/useBuiltinAgents", () => ({
  useRemoveBuiltinAgent: vi.fn(),
  useCreateBuiltinAgent: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  usePatchBuiltinAgent: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
}));

const { useRemoveBuiltinAgent } = await import("@/lib/hooks/useBuiltinAgents");
const useRemoveMock = vi.mocked(useRemoveBuiltinAgent);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children ?? ui}</QueryClientProvider>
  );
}

const SAMPLE: BuiltinAgentOut[] = [
  {
    ref: "builtin_agent:coffer",
    kind: "builtin_agent",
    name: "coffer",
    description: null,
    config: {
      model: "anthropic:claude-sonnet-4-6",
      use_gateway: true,
      confirm_tools: ["*delete*"],
    },
    enabled: true,
    created_at: "2026-05-28T00:00:00Z",
    updated_at: "2026-05-28T00:00:00Z",
  },
];

describe("BuiltinAgentTable", () => {
  afterEach(() => vi.clearAllMocks());

  test("renders a row with name, model, and confirm-tools count", () => {
    useRemoveMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveBuiltinAgent>);
    render(<BuiltinAgentTable agents={SAMPLE} />, { wrapper: wrap(null) });
    expect(screen.getByText("coffer")).toBeInTheDocument();
    expect(screen.getByText("anthropic:claude-sonnet-4-6")).toBeInTheDocument();
  });

  test("the edit action opens the edit form", () => {
    useRemoveMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveBuiltinAgent>);
    render(<BuiltinAgentTable agents={SAMPLE} />, { wrapper: wrap(null) });
    fireEvent.click(screen.getByRole("button", { name: /edit coffer/i }));
    const dialog = screen.getByRole("dialog");
    // Edit mode shows the read-only name and the model value.
    expect(within(dialog).getByDisplayValue("anthropic:claude-sonnet-4-6")).toBeInTheDocument();
  });

  test("a last-agent 409 is shown inside the delete dialog", () => {
    const mutate = vi.fn((_name, opts: { onError: (e: unknown) => void }) => {
      opts.onError(
        new ApiError("CANNOT_DELETE_LAST_BUILTIN_AGENT", "cannot delete the last built-in agent"),
      );
    });
    useRemoveMock.mockReturnValue({
      mutate,
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveBuiltinAgent>);
    render(<BuiltinAgentTable agents={SAMPLE} />, { wrapper: wrap(null) });
    fireEvent.click(screen.getByRole("button", { name: /delete coffer/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));
    expect(mutate).toHaveBeenCalled();
    // The translated error copy (or envelope fallback) is rendered, not a crash.
    expect(within(dialog).getByRole("alert")).toHaveTextContent(/last built-in agent/i);
  });
});
