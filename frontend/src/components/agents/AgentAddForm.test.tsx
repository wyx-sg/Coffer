// frontend/src/components/agents/AgentAddForm.test.tsx
//
// TEST25-206: AgentAddForm renders + submits via `useRegisterAgent`. We
// mock the hook so we can assert the body that would be POSTed.

import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { AgentAddForm } from "./AgentAddForm";

vi.mock("@/lib/hooks/useAgents", () => ({
  useRegisterAgent: vi.fn(),
}));
const { useRegisterAgent } = await import("@/lib/hooks/useAgents");
const useRegisterAgentMock = vi.mocked(useRegisterAgent);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children ?? ui}</QueryClientProvider>
  );
}

describe("AgentAddForm", () => {
  afterEach(() => vi.clearAllMocks());

  test("renders type select + name input + cancel/register buttons", () => {
    useRegisterAgentMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof useRegisterAgent>);
    render(<AgentAddForm onClose={() => {}} onCreated={() => {}} />, { wrapper: wrap(null) });
    expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /register/i })).toBeInTheDocument();
  });

  test("calls mutateAsync with the form body on submit and fires onCreated", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    const onCreated = vi.fn();
    useRegisterAgentMock.mockReturnValue({
      mutateAsync,
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof useRegisterAgent>);
    render(<AgentAddForm onClose={() => {}} onCreated={onCreated} />, { wrapper: wrap(null) });

    // The required `name` field is the input under the "Name" label.
    const nameLabel = screen.getByText(/^name$/i);
    const nameField = nameLabel.parentElement?.querySelector("input");
    expect(nameField).not.toBeNull();
    fireEvent.change(nameField!, { target: { value: "my-cursor" } });

    // Submit.
    const submit = screen.getByRole("button", { name: /register/i });
    fireEvent.click(submit);

    // Wait a tick for the async mutation.
    await new Promise((r) => setTimeout(r, 0));

    expect(mutateAsync).toHaveBeenCalledTimes(1);
    const body = mutateAsync.mock.calls[0][0];
    expect(body.name).toBe("my-cursor");
    // Default type the form pre-selects is "cursor".
    expect(body.type).toBe("cursor");
    expect(onCreated).toHaveBeenCalled();
  });

  test("clicking Cancel calls onClose", () => {
    useRegisterAgentMock.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof useRegisterAgent>);
    const onClose = vi.fn();
    render(<AgentAddForm onClose={onClose} onCreated={() => {}} />, {
      wrapper: wrap(null),
    });
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
