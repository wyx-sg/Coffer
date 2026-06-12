// pages/ChatPage.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ChatPage } from "./ChatPage";
import type { Conversation } from "@/lib/api/chat";
import type { Model } from "@/lib/api/models";

// Mock the hooks to isolate the page component.
vi.mock("@/lib/api/chat", () => ({
  chatApi: {
    listConversations: vi.fn(),
    createConversation: vi.fn(),
    getConversation: vi.fn(),
    updateConversation: vi.fn(),
    deleteConversation: vi.fn(),
    listMessages: vi.fn(),
  },
}));

vi.mock("@/lib/api/models", () => ({
  modelsApi: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
  },
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

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ChatPage />
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
    // History panel header
    expect(await screen.findByText("Conversations")).toBeInTheDocument();
  });

  test("shows no-model empty state when conversation selected has no model AND no models configured", async () => {
    const conv = makeConv({ model_id: null });
    chatApiMock.listConversations.mockResolvedValue({ conversations: [conv] });
    modelsApiMock.list.mockResolvedValue({ models: [] });
    chatApiMock.listMessages = vi.fn().mockResolvedValue({ messages: [] });
    renderPage();

    // Click on the conversation
    const item = await screen.findByText("Test Conv");
    item.click();

    await waitFor(() =>
      expect(screen.getByText("No model configured")).toBeInTheDocument(),
    );
  });

  test("does NOT show no-model empty state when conversation has model_id null but models are configured (I2)", async () => {
    // FR-016: a conversation with model_id=null uses the default model — it is valid.
    const conv = makeConv({ model_id: null });
    chatApiMock.listConversations.mockResolvedValue({ conversations: [conv] });
    modelsApiMock.list.mockResolvedValue({ models: [makeModel()] });
    chatApiMock.listMessages = vi.fn().mockResolvedValue({ messages: [] });
    renderPage();

    // Click on the conversation
    const item = await screen.findByText("Test Conv");
    item.click();

    // Empty state must NOT appear when models exist
    await waitFor(() =>
      expect(screen.queryByText("No model configured")).not.toBeInTheDocument(),
    );
  });

  test("shows 'select or create' prompt when no conversation active", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    modelsApiMock.list.mockResolvedValue({ models: [] });
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByText(/select a conversation or start a new one/i),
      ).toBeInTheDocument(),
    );
  });

  test("renders conversation list items", async () => {
    chatApiMock.listConversations.mockResolvedValue({
      conversations: [makeConv(), makeConv({ id: "conv-2", title: "Second Chat" })],
    });
    modelsApiMock.list.mockResolvedValue({ models: [makeModel()] });
    renderPage();
    expect(await screen.findByText("Test Conv")).toBeInTheDocument();
    expect(await screen.findByText("Second Chat")).toBeInTheDocument();
  });

  test("surfaces an error when creating a conversation fails", async () => {
    const { fireEvent } = await import("@testing-library/react");
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    modelsApiMock.list.mockResolvedValue({ models: [makeModel()] });
    chatApiMock.createConversation.mockRejectedValue(new Error("boom"));

    renderPage();

    // Open the new-conversation dialog and confirm.
    const openButtons = await screen.findAllByRole("button", { name: /new chat/i });
    fireEvent.click(openButtons[0]);
    fireEvent.click(await screen.findByRole("button", { name: /start conversation/i }));

    // The failure must be surfaced, not silently swallowed.
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
