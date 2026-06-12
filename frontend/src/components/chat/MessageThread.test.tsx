// components/chat/MessageThread.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MessageThread } from "./MessageThread";
import type { Conversation, Message } from "@/lib/api/chat";
import type { Model } from "@/lib/api/models";

vi.mock("@/lib/api/chat", () => ({
  chatApi: {
    listMessages: vi.fn(),
  },
}));

const { chatApi } = await import("@/lib/api/chat");
const chatApiMock = chatApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

const BASE_CONV: Conversation = {
  id: "conv-1",
  agent_key: "builtin",
  title: "Test",
  model_id: "model-1",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const BASE_MODEL: Model = {
  id: "model-1",
  display_name: "Test Model",
  provider: "anthropic",
  model: "claude-3-5-sonnet",
  is_default: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const makeMsg = (overrides: Partial<Message>): Message => ({
  id: "msg-1",
  conversation_id: "conv-1",
  seq: 1,
  role: "user",
  content: [{ type: "text", text: "Hello" }],
  status: "complete",
  created_at: "2026-01-01T00:00:00Z",
  ...overrides,
});

function renderThread(props?: Partial<React.ComponentProps<typeof MessageThread>>) {
  const defaultProps: React.ComponentProps<typeof MessageThread> = {
    conversation: BASE_CONV,
    models: [BASE_MODEL],
    liveMessage: null,
    isStreaming: false,
    onSend: vi.fn(),
    onModelChange: vi.fn(),
  };
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <MessageThread {...defaultProps} {...props} />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("MessageThread", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("shows no-model empty state when zero models are configured", () => {
    // I2: empty state is driven by the model LIST, not by conversation.model_id.
    chatApiMock.listMessages = vi.fn();
    renderThread({ models: [] });
    expect(screen.getByText("No model configured")).toBeInTheDocument();
  });

  test("does NOT show no-model empty state when models exist but conversation.model_id is null", async () => {
    // I2: conversation with model_id=null uses the default model — it is valid.
    chatApiMock.listMessages = vi.fn().mockResolvedValue({ messages: [] });
    renderThread({ conversation: { ...BASE_CONV, model_id: null }, models: [BASE_MODEL] });
    await waitFor(() =>
      expect(screen.queryByText("No model configured")).not.toBeInTheDocument(),
    );
  });

  test("renders user messages right-aligned", async () => {
    chatApiMock.listMessages.mockResolvedValue({
      messages: [makeMsg({ role: "user", content: [{ type: "text", text: "Hey there" }] })],
    });
    renderThread();
    await waitFor(() => expect(screen.getByText("Hey there")).toBeInTheDocument());
  });

  test("renders assistant messages", async () => {
    chatApiMock.listMessages.mockResolvedValue({
      messages: [
        makeMsg({
          id: "msg-2",
          role: "assistant",
          content: [{ type: "text", text: "Hello from assistant" }],
        }),
      ],
    });
    renderThread();
    await waitFor(() =>
      expect(screen.getByText("Hello from assistant")).toBeInTheDocument(),
    );
  });

  test("renders live streaming message text", async () => {
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderThread({
      liveMessage: { text: "Streaming reply...", toolBlocks: [], streaming: true },
    });
    await waitFor(() =>
      expect(screen.getByText("Streaming reply...")).toBeInTheDocument(),
    );
  });

  test("renders tool call card for live message with tool blocks", async () => {
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderThread({
      liveMessage: {
        text: "",
        streaming: true,
        toolBlocks: [
          {
            type: "tool_use",
            tool_use_id: "tc-1",
            tool_name: "search",
            tool_input: { query: "test" },
          },
        ],
      },
    });
    await waitFor(() => expect(screen.getByText("search")).toBeInTheDocument());
  });

  test("renders Composer", async () => {
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderThread();
    await waitFor(() =>
      expect(screen.getByRole("textbox")).toBeInTheDocument(),
    );
  });

  test("Composer is disabled while streaming", async () => {
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderThread({ isStreaming: true });
    await waitFor(() =>
      expect(screen.getByRole("textbox")).toBeDisabled(),
    );
  });

  test("locks the composer when the server reports an in-flight turn (persisted streaming row)", async () => {
    // After a reload/switch-back mid-turn there is no client stream, but the
    // fetched messages contain the streaming placeholder — the composer must
    // be locked (sending would just 409) until the turn finishes.
    chatApiMock.listMessages.mockResolvedValue({
      messages: [
        makeMsg({ role: "user" }),
        makeMsg({ id: "msg-2", seq: 2, role: "assistant", status: "streaming", content: [] }),
      ],
    });
    renderThread({ isStreaming: false });
    await waitFor(() => expect(screen.getByRole("textbox")).toBeDisabled());
  });

  test("does not render fetched streaming rows while a live message is shown", async () => {
    // A mid-turn refetch (e.g. window refocus) returns the placeholder row;
    // rendering it alongside the live bubble would duplicate the reply.
    chatApiMock.listMessages.mockResolvedValue({
      messages: [
        makeMsg({ role: "user" }),
        makeMsg({ id: "msg-2", seq: 2, role: "assistant", status: "streaming", content: [] }),
      ],
    });
    renderThread({
      isStreaming: true,
      liveMessage: { text: "live text", toolBlocks: [], streaming: true },
    });
    await waitFor(() => expect(screen.getByText("live text")).toBeInTheDocument());
    // Exactly one in-progress bubble: the live one; the fetched placeholder is filtered.
    expect(screen.queryAllByText(/thinking/i)).toHaveLength(0);
  });

  test("renders the just-sent user message echo while the reply streams", async () => {
    // P0-4: the prompt must be visible immediately, not only after the next
    // messages fetch.
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderThread({
      isStreaming: true,
      liveMessage: { userText: "my question", text: "replying", toolBlocks: [], streaming: true },
    });
    await waitFor(() => expect(screen.getByText("my question")).toBeInTheDocument());
    expect(screen.getByText("replying")).toBeInTheDocument();
  });

  test("does not duplicate the echo once the persisted user message is fetched", async () => {
    // A mid-turn refetch returns the persisted user row — the fetched row
    // wins and the optimistic echo is suppressed.
    chatApiMock.listMessages.mockResolvedValue({
      messages: [
        makeMsg({ role: "user", content: [{ type: "text", text: "earlier question" }] }),
        makeMsg({
          id: "msg-2",
          seq: 2,
          role: "assistant",
          content: [{ type: "text", text: "earlier answer" }],
        }),
        makeMsg({ id: "msg-3", seq: 3, role: "user", content: [{ type: "text", text: "my question" }] }),
        makeMsg({ id: "msg-4", seq: 4, role: "assistant", status: "streaming", content: [] }),
      ],
    });
    renderThread({
      isStreaming: true,
      liveMessage: { userText: "my question", text: "", toolBlocks: [], streaming: true },
    });
    await waitFor(() => expect(screen.getByText("earlier answer")).toBeInTheDocument());
    expect(screen.getAllByText("my question")).toHaveLength(1);
  });

  test("readOnly hides the composer and shows a restore call-to-action", async () => {
    // P0-3: archived conversations open read-only; restoring re-enables chat.
    chatApiMock.listMessages.mockResolvedValue({
      messages: [makeMsg({ content: [{ type: "text", text: "old message" }] })],
    });
    const onRestore = vi.fn();
    renderThread({ readOnly: true, onRestore });
    await waitFor(() => expect(screen.getByText("old message")).toBeInTheDocument());
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getByText("This conversation is archived.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /restore/i }));
    expect(onRestore).toHaveBeenCalled();
  });

  test("shows the agent's display name from props, not a hardcoded one", async () => {
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderThread({ agentLabel: "Research Bot" });
    await waitFor(() => expect(screen.getByText("Research Bot")).toBeInTheDocument());
  });

  test("hides the model selector for a non-builtin agent", async () => {
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderThread({
      conversation: { ...BASE_CONV, agent_key: "other" },
      agentLabel: "Other Agent",
      showModelSelector: false,
    });
    await waitFor(() => expect(screen.getByText("Other Agent")).toBeInTheDocument());
    expect(
      screen.queryByRole("combobox", { name: /select.*model/i }),
    ).not.toBeInTheDocument();
  });

  test("renders the approval card when a turn is paused on approval", async () => {
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    const onApprovalDecide = vi.fn();
    renderThread({
      isStreaming: true,
      pendingApproval: {
        request_id: "r1",
        tool_use_id: "t1",
        tool_name: "run_command",
        tool_input: { cmd: "ls" },
      },
      onApprovalDecide,
    });
    await waitFor(() =>
      expect(screen.getByText("Approval required")).toBeInTheDocument(),
    );
    expect(screen.getByText("run_command")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /allow/i }));
    await waitFor(() => expect(onApprovalDecide).toHaveBeenCalledWith("allow"));
  });
});
