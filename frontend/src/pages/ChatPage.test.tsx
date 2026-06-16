// pages/ChatPage.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ChatPage } from "./ChatPage";
import type { Conversation } from "@/lib/api/chat";
import { ApiError } from "@/lib/api/errors";
import type { Model } from "@/lib/api/models";

vi.mock("@/lib/api/chat", () => ({
  chatApi: {
    listConversations: vi.fn(),
    createConversation: vi.fn(),
    getConversation: vi.fn(),
    updateConversation: vi.fn(),
    deleteConversation: vi.fn(),
    archiveConversation: vi.fn(),
    unarchiveConversation: vi.fn(),
    listMessages: vi.fn(),
    listAgents: vi.fn(),
  },
}));

vi.mock("@/lib/api/models", () => ({
  modelsApi: { list: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn() },
}));

vi.mock("@/lib/chat/streamClient", () => ({
  streamChatTurn: vi.fn(async function* () {}),
}));

const { chatApi } = await import("@/lib/api/chat");
const { modelsApi } = await import("@/lib/api/models");
const chatApiMock = chatApi as unknown as Record<string, ReturnType<typeof vi.fn>>;
const modelsApiMock = modelsApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

const makeConv = (overrides?: Partial<Conversation>): Conversation => ({
  id: "conv-1",
  agent_key: "claude_code",
  title: "Test Conv",
  model_id: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  ...overrides,
});

const makeModel = (overrides?: Partial<Model>): Model => ({
  id: "model-1",
  display_name: "Test Model",
  provider: "anthropic",
  model: "claude-3-5-sonnet",
  is_default: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  ...overrides,
});

function renderPage(
  initialPath = "/chat",
  agents?: { agent_key: string; display_name: string; available: boolean }[],
) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  chatApiMock.listAgents = vi.fn().mockResolvedValue({
    agents: agents ?? [{ agent_key: "claude_code", display_name: "Claude Code", available: true }],
  });
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:id" element={<ChatPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("ChatPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("shows conversation list with active/archived filter", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    modelsApiMock.list.mockResolvedValue({ models: [] });
    renderPage();
    expect(await screen.findByRole("tab", { name: /active/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /archived/i })).toBeInTheDocument();
  });

  test("bare /chat shows the draft surface with a composer right away, not a modal", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    modelsApiMock.list.mockResolvedValue({ models: [] });
    renderPage("/chat");
    // No per-turn working-directory step anymore: the draft guide + composer
    // appear immediately — no "Start conversation" dialog button.
    expect(await screen.findByText(/start a new conversation/i)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /message input/i })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /working directory/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /start conversation/i })).not.toBeInTheDocument();
  });

  test("draft with no managed agent available shows the install/configure empty state", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    modelsApiMock.list.mockResolvedValue({ models: [] });
    renderPage("/chat", [
      { agent_key: "claude_code", display_name: "Claude Code", available: false },
    ]);
    expect(await screen.findByText("No managed agent available")).toBeInTheDocument();
  });

  test("/chat/:id opens that conversation's thread (URL-addressable)", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [makeConv()] });
    modelsApiMock.list.mockResolvedValue({ models: [makeModel()] });
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderPage("/chat/conv-1");
    // The thread's empty prompt (not the draft guide) appears for a real conv.
    await waitFor(() =>
      expect(screen.getByText(/send a message to start the conversation/i)).toBeInTheDocument(),
    );
  });

  test("sending the first message in the draft creates a conversation", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    modelsApiMock.list.mockResolvedValue({ models: [] });
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    chatApiMock.createConversation.mockResolvedValue(makeConv({ id: "new-conv" }));
    renderPage("/chat");

    // No working-directory step: just type the first message. The turn defaults
    // to the Coffer-managed workspace on the backend, so no cwd is sent.
    const composer = await screen.findByRole("textbox", { name: /message input/i });
    fireEvent.change(composer, { target: { value: "hello there" } });
    fireEvent.keyDown(composer, { key: "Enter", shiftKey: false });

    await waitFor(() =>
      expect(chatApiMock.createConversation).toHaveBeenCalledWith({
        agent_key: "claude_code",
        agent_config: {},
      }),
    );
  });

  test("deleting a conversation asks for confirmation first", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [makeConv()] });
    modelsApiMock.list.mockResolvedValue({ models: [makeModel()] });
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderPage("/chat/conv-1");

    // Reveal the row's delete control and click it.
    const delBtn = await screen.findByRole("button", { name: /delete/i });
    fireEvent.click(delBtn);

    // A confirm dialog appears; the API is NOT called until confirmed.
    expect(await screen.findByText(/delete this conversation\?/i)).toBeInTheDocument();
    expect(chatApiMock.deleteConversation).not.toHaveBeenCalled();
  });

  test("/chat/:id for an archived conversation opens it read-only with a restore CTA", async () => {
    // P0-3: archived rows are not in the active list — the thread must still
    // open (by-id fetch), read-only, instead of falling through to the draft.
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    modelsApiMock.list.mockResolvedValue({ models: [makeModel()] });
    chatApiMock.getConversation.mockResolvedValue(
      makeConv({ archived_at: "2026-02-01T00:00:00Z" }),
    );
    chatApiMock.listMessages.mockResolvedValue({
      messages: [
        {
          id: "m1",
          conversation_id: "conv-1",
          seq: 1,
          role: "user",
          content: [{ type: "text", text: "old question" }],
          status: "complete",
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
    });
    renderPage("/chat/conv-1");

    expect(await screen.findByText("old question")).toBeInTheDocument();
    // Read-only: no composer; a restore call-to-action instead.
    expect(screen.queryByRole("textbox", { name: /message input/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /restore/i })).toBeInTheDocument();
  });

  test("restoring an archived thread unarchives it and re-enables the composer", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    modelsApiMock.list.mockResolvedValue({ models: [makeModel()] });
    chatApiMock.getConversation
      .mockResolvedValueOnce(makeConv({ archived_at: "2026-02-01T00:00:00Z" }))
      .mockResolvedValue(makeConv({ archived_at: null }));
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    chatApiMock.unarchiveConversation.mockResolvedValue(makeConv({ archived_at: null }));
    renderPage("/chat/conv-1");

    fireEvent.click(await screen.findByRole("button", { name: /restore/i }));

    await waitFor(() => expect(chatApiMock.unarchiveConversation).toHaveBeenCalled());
    expect(chatApiMock.unarchiveConversation.mock.calls[0][0]).toBe("conv-1");
    expect(await screen.findByRole("textbox", { name: /message input/i })).toBeInTheDocument();
  });

  test("an unknown /chat/:id shows a not-found state, not the silent draft surface", async () => {
    // P0-3: a stale deep-link must say so explicitly — typing into the draft
    // here would silently create a NEW conversation.
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    modelsApiMock.list.mockResolvedValue({ models: [makeModel()] });
    chatApiMock.getConversation.mockRejectedValue(
      new ApiError("CONVERSATION_NOT_FOUND", "conversation not found"),
    );
    renderPage("/chat/nope");

    expect(await screen.findByText("Conversation not found")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /message input/i })).not.toBeInTheDocument();

    // The explicit way out: start a fresh chat from the not-found state — the
    // draft surface (with its composer) replaces the not-found UI.
    fireEvent.click(screen.getByRole("button", { name: /start a new chat/i }));
    expect(await screen.findByRole("textbox", { name: /message input/i })).toBeInTheDocument();
  });

  test("surfaces an error when creating a conversation fails", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    modelsApiMock.list.mockResolvedValue({ models: [] });
    chatApiMock.createConversation.mockRejectedValue(new Error("boom"));
    renderPage("/chat");

    const composer = await screen.findByRole("textbox", { name: /message input/i });
    fireEvent.change(composer, { target: { value: "hi" } });
    fireEvent.keyDown(composer, { key: "Enter", shiftKey: false });

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
