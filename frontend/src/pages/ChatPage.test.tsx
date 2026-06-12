// pages/ChatPage.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ChatPage } from "./ChatPage";
import type { Conversation } from "@/lib/api/chat";
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
  agent_key: "builtin",
  title: "Test Conv",
  model_id: "model-1",
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

function renderPage(initialPath = "/chat") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  chatApiMock.listAgents = vi.fn().mockResolvedValue({
    agents: [{ agent_key: "builtin", display_name: "Coffer Assistant", available: true }],
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

  test("shows conversation history panel with new chat button", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    modelsApiMock.list.mockResolvedValue({ models: [] });
    renderPage();
    expect(await screen.findByText("Conversations")).toBeInTheDocument();
  });

  test("bare /chat shows the draft surface (composer), not a modal", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    modelsApiMock.list.mockResolvedValue({ models: [makeModel()] });
    renderPage("/chat");
    // Draft guide + composer are present; no "Start conversation" dialog button.
    expect(await screen.findByText(/start a new conversation/i)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /message input/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /start conversation/i })).not.toBeInTheDocument();
  });

  test("draft with no models shows the no-model empty state", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    modelsApiMock.list.mockResolvedValue({ models: [] });
    renderPage("/chat");
    expect(await screen.findByText("No model configured")).toBeInTheDocument();
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
    modelsApiMock.list.mockResolvedValue({ models: [makeModel()] });
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    chatApiMock.createConversation.mockResolvedValue(makeConv({ id: "new-conv" }));
    renderPage("/chat");

    const composer = await screen.findByRole("textbox", { name: /message input/i });
    fireEvent.change(composer, { target: { value: "hello there" } });
    fireEvent.keyDown(composer, { key: "Enter", shiftKey: false });

    await waitFor(() =>
      expect(chatApiMock.createConversation).toHaveBeenCalledWith({
        agent_key: "builtin",
        agent_config: { model_id: "model-1" },
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

  test("surfaces an error when creating a conversation fails", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    modelsApiMock.list.mockResolvedValue({ models: [makeModel()] });
    chatApiMock.createConversation.mockRejectedValue(new Error("boom"));
    renderPage("/chat");

    const composer = await screen.findByRole("textbox", { name: /message input/i });
    fireEvent.change(composer, { target: { value: "hi" } });
    fireEvent.keyDown(composer, { key: "Enter", shiftKey: false });

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
