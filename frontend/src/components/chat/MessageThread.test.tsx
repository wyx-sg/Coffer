// components/chat/MessageThread.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MessageThread } from "./MessageThread";
import { acceptance } from "@/test/acceptance";
import type { Conversation, Message } from "@/lib/api/chat";

vi.mock("@/lib/api/chat", () => ({
  chatApi: {
    listMessages: vi.fn(),
    getAgentConfig: vi.fn().mockResolvedValue({ cwd: null, model: null }),
  },
}));

// The AgentModelBar's model picker pulls provider suggestions; stub those out so
// this thread-focused test makes no network calls.
vi.mock("@/lib/hooks/useProviders", () => ({ useProviders: () => ({ data: [] }) }));
vi.mock("@/lib/hooks/useModelIntrospection", () => ({
  useListProviderModels: () => ({ mutate: vi.fn() }),
}));

const { chatApi } = await import("@/lib/api/chat");
const chatApiMock = chatApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

const BASE_CONV: Conversation = {
  id: "conv-1",
  agent_key: "claude_code",
  title: "Test",
  model_id: null,
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
    liveMessage: null,
    isStreaming: false,
    onSend: vi.fn(),
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

  test("renders the thread with a per-conversation agent model picker", async () => {
    // Chat talks only to managed agents (Claude Code, Codex). The per-conversation
    // model is the agent's own model (agent_config.model, ADR-024 → ADR-032), so
    // the thread bar carries a model picker — but never the built-in agent's
    // "No model configured" empty state.
    chatApiMock.listMessages = vi.fn().mockResolvedValue({ messages: [] });
    renderThread();
    await waitFor(() => expect(chatApiMock.listMessages).toHaveBeenCalled());
    expect(screen.getByLabelText(/agent model/i)).toBeInTheDocument();
    expect(screen.queryByText("No model configured")).not.toBeInTheDocument();
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
    await waitFor(() => expect(screen.getByText("Hello from assistant")).toBeInTheDocument());
  });

  test("renders live streaming message text", async () => {
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderThread({
      liveMessage: { text: "Streaming reply...", toolBlocks: [], streaming: true },
    });
    await waitFor(() => expect(screen.getByText("Streaming reply...")).toBeInTheDocument());
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
    await waitFor(() => expect(screen.getByRole("textbox")).toBeInTheDocument());
  });

  test("Composer stays ENABLED while a turn streams (the next message queues)", async () => {
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderThread({ isStreaming: true });
    await waitFor(() => expect(screen.getByRole("textbox")).toBeInTheDocument());
    expect(screen.getByRole("textbox")).not.toBeDisabled();
  });

  test("renders queued messages one per row; clicking remove drops that item", async () => {
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    const onSetPending = vi.fn();
    renderThread({
      isStreaming: true,
      pending: ["first queued", "second queued"],
      onSetPending,
    });
    await waitFor(() => expect(screen.getByText("first queued")).toBeInTheDocument());
    expect(screen.getByText("second queued")).toBeInTheDocument();

    // Each row has a remove button; removing the first leaves only the second.
    const removeButtons = screen.getAllByRole("button", { name: /remove from queue/i });
    expect(removeButtons).toHaveLength(2);
    act(() => {
      fireEvent.click(removeButtons[0]);
    });
    expect(onSetPending).toHaveBeenCalledWith(["second queued"]);
  });

  acceptance("008-agent-chat", "editing a queued message re-queues it at the tail", async () => {
    // The edit affordance pulls a queued message back into the composer to amend;
    // re-sending it (still streaming) re-queues it at the tail via the send path.
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    const onSetPending = vi.fn();
    renderThread({
      isStreaming: true,
      pending: ["first queued", "second queued"],
      onSetPending,
    });
    await waitFor(() => expect(screen.getByText("first queued")).toBeInTheDocument());

    const editButtons = screen.getAllByRole("button", { name: /edit queued message/i });
    expect(editButtons).toHaveLength(2);
    act(() => {
      fireEvent.click(editButtons[0]);
    });
    // Removed from the queue…
    expect(onSetPending).toHaveBeenCalledWith(["second queued"]);
    // …and pulled back into the composer for the user to amend.
    expect(screen.getByRole("textbox")).toHaveValue("first queued");
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
        makeMsg({
          id: "msg-3",
          seq: 3,
          role: "user",
          content: [{ type: "text", text: "my question" }],
        }),
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

  test("does not render a per-conversation model selector", async () => {
    // Managed agents carry no Coffer-registered model, so the thread bar shows
    // only the agent label — there is no model selector.
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderThread({ agentLabel: "Other Agent" });
    await waitFor(() => expect(screen.getByText("Other Agent")).toBeInTheDocument());
    expect(screen.queryByRole("combobox", { name: /select.*model/i })).not.toBeInTheDocument();
  });

  acceptance("008-agent-chat", "second message queues during a streaming turn", async () => {
    // Fire-and-return + persistent subscription: while a reply streams the
    // composer stays usable, and a message sent mid-turn shows up as a queued
    // chip (the queue_changed event surfaced it) instead of being blocked.
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderThread({ isStreaming: true, pending: ["my queued question"] });

    // The composer is never locked by streaming.
    await waitFor(() => expect(screen.getByRole("textbox")).toBeInTheDocument());
    expect(screen.getByRole("textbox")).not.toBeDisabled();

    // The second message appears as a removable queued chip.
    expect(screen.getByText("my queued question")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /remove from queue/i })).toBeInTheDocument();
  });
});
