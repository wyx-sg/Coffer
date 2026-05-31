// frontend/src/components/chat/NewConversationDialog.test.tsx
//
// The new-conversation flow: the picker lists built-in + managed agents, the
// first (built-in) target is preselected, and Start creates the conversation
// with its target_ref and hands the new id back to the caller.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren, ReactNode } from "react";

import { NewConversationDialog } from "./NewConversationDialog";
import type { ChatTarget } from "@/lib/hooks/useChatTargets";

vi.mock("@/lib/hooks/useChatTargets", () => ({ useChatTargets: vi.fn() }));
vi.mock("@/lib/hooks/useChat", () => ({ useCreateConversation: vi.fn() }));

const targetsHook = await import("@/lib/hooks/useChatTargets");
const chatHook = await import("@/lib/hooks/useChat");
const useChatTargetsMock = vi.mocked(targetsHook.useChatTargets);
const useCreateConversationMock = vi.mocked(chatHook.useCreateConversation);

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children ?? ui}</QueryClientProvider>
  );
}

const TARGETS: ChatTarget[] = [
  {
    ref: "builtin_agent:coffer",
    kind: "builtin_agent",
    name: "coffer",
    description: "The built-in agent",
  },
  { ref: "agent:claude-code", kind: "agent", name: "claude-code", description: null },
];

afterEach(() => vi.clearAllMocks());

describe("NewConversationDialog", () => {
  test("lists built-in and managed targets and creates with the selected ref", async () => {
    useChatTargetsMock.mockReturnValue({
      data: TARGETS,
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof targetsHook.useChatTargets>);

    const mutate = vi.fn((_body, opts?: { onSuccess?: (c: { id: string }) => void }) =>
      opts?.onSuccess?.({ id: "new-conv" }),
    );
    useCreateConversationMock.mockReturnValue({
      mutate,
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof chatHook.useCreateConversation>);

    const onCreated = vi.fn();
    render(<NewConversationDialog open onOpenChange={() => {}} onCreated={onCreated} />, {
      wrapper: wrap(null),
    });

    // Both targets render.
    expect(screen.getByText("coffer")).toBeInTheDocument();
    expect(screen.getByText("claude-code")).toBeInTheDocument();

    // Start creates with the preselected built-in ref and routes to the new id.
    fireEvent.click(screen.getByRole("button", { name: /start chat/i }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("new-conv"));
    expect(mutate).toHaveBeenCalledWith({ target_ref: "builtin_agent:coffer" }, expect.anything());
  });

  test("can select the managed agent before creating", async () => {
    useChatTargetsMock.mockReturnValue({
      data: TARGETS,
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof targetsHook.useChatTargets>);
    const mutate = vi.fn();
    useCreateConversationMock.mockReturnValue({
      mutate,
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof chatHook.useCreateConversation>);

    render(<NewConversationDialog open onOpenChange={() => {}} onCreated={() => {}} />, {
      wrapper: wrap(null),
    });

    fireEvent.click(screen.getByText("claude-code"));
    fireEvent.click(screen.getByRole("button", { name: /start chat/i }));
    expect(mutate).toHaveBeenCalledWith({ target_ref: "agent:claude-code" }, expect.anything());
  });

  test("shows the empty state when there are no targets", () => {
    useChatTargetsMock.mockReturnValue({
      data: [],
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof targetsHook.useChatTargets>);
    useCreateConversationMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof chatHook.useCreateConversation>);

    render(<NewConversationDialog open onOpenChange={() => {}} onCreated={() => {}} />, {
      wrapper: wrap(null),
    });
    expect(screen.getByText(/no agents available/i)).toBeInTheDocument();
  });
});
