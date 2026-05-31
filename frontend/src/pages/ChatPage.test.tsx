// frontend/src/pages/ChatPage.test.tsx
//
// Carries the acceptance marker for spec scenario "create / list / rename /
// archive / restore / delete a conversation" on the desktop surface: the chat
// page renders the conversation list, the per-conversation action menu exposes
// rename / archive / delete, and an empty selection shows the welcome prompt.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import type { PropsWithChildren, ReactNode } from "react";

import { ChatPage } from "./ChatPage";
import { acceptance } from "@/test/acceptance";
import type { ConversationOut } from "@/lib/api/chat";

vi.mock("@/lib/hooks/useChat", () => ({
  useConversations: vi.fn(),
  useArchiveConversation: vi.fn(),
  useRestoreConversation: vi.fn(),
  useDeleteConversation: vi.fn(),
  useRenameConversation: vi.fn(),
  useConversation: vi.fn(),
  useCreateConversation: vi.fn(),
}));
vi.mock("@/lib/hooks/useChatTargets", () => ({ useChatTargets: vi.fn() }));
const hooks = await import("@/lib/hooks/useChat");
const targetsHook = await import("@/lib/hooks/useChatTargets");
const useConversationsMock = vi.mocked(hooks.useConversations);

function mutationStub() {
  return { mutate: vi.fn(), isPending: false, error: null } as unknown as ReturnType<
    typeof hooks.useArchiveConversation
  >;
}

function wrap(ui: ReactNode, initialPath = "/chat") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/chat" element={children ?? ui} />
          <Route path="/chat/:id" element={children ?? ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const SAMPLE: ConversationOut[] = [
  {
    id: "conv-1",
    target_ref: "builtin_agent:coffer",
    title: "Planning chat",
    status: "active",
    model_snapshot: {},
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
  },
];

afterEach(() => vi.clearAllMocks());

function stub(conversations: ConversationOut[], isPending = false) {
  useConversationsMock.mockReturnValue({
    data: conversations,
    isPending,
  } as unknown as ReturnType<typeof hooks.useConversations>);
  vi.mocked(hooks.useArchiveConversation).mockReturnValue(mutationStub());
  vi.mocked(hooks.useRestoreConversation).mockReturnValue(
    mutationStub() as unknown as ReturnType<typeof hooks.useRestoreConversation>,
  );
  vi.mocked(hooks.useDeleteConversation).mockReturnValue(
    mutationStub() as unknown as ReturnType<typeof hooks.useDeleteConversation>,
  );
  vi.mocked(hooks.useRenameConversation).mockReturnValue(
    mutationStub() as unknown as ReturnType<typeof hooks.useRenameConversation>,
  );
  vi.mocked(hooks.useCreateConversation).mockReturnValue(
    mutationStub() as unknown as ReturnType<typeof hooks.useCreateConversation>,
  );
  vi.mocked(targetsHook.useChatTargets).mockReturnValue({
    data: [],
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof targetsHook.useChatTargets>);
}

acceptance(
  "008-builtin-agent-chat",
  "create / list / rename / archive / restore / delete a conversation",
  async () => {
    stub(SAMPLE);
    render(<ChatPage />, { wrapper: wrap(null) });

    // The conversation is listed.
    expect(screen.getByText("Planning chat")).toBeInTheDocument();

    // The row action menu exposes rename / archive / delete.
    fireEvent.click(screen.getByRole("button", { name: /conversation actions/i }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^rename$/i })).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /^archive$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^delete$/i })).toBeInTheDocument();
  },
);

describe("ChatPage", () => {
  test("shows the welcome prompt when no conversation is selected", () => {
    stub(SAMPLE);
    render(<ChatPage />, { wrapper: wrap(null) });
    expect(screen.getByText(/start chatting/i)).toBeInTheDocument();
  });

  test("shows the empty-list message when there are no conversations", () => {
    stub([]);
    render(<ChatPage />, { wrapper: wrap(null) });
    expect(screen.getByText(/no conversations yet/i)).toBeInTheDocument();
  });

  test("offers a new-chat button", () => {
    stub(SAMPLE);
    render(<ChatPage />, { wrapper: wrap(null) });
    expect(screen.getByRole("button", { name: /new chat/i })).toBeInTheDocument();
  });
});
