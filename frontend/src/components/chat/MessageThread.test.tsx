// components/chat/MessageThread.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MessageThread } from "./MessageThread";
import { acceptance } from "@/test/acceptance";
import type { Conversation, Message } from "@/lib/api/chat";
import { ApiError } from "@/lib/api/errors";

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
    // model is the agent's own model (agent_config.model, the
    // coffer-model-is-an-internal-engine and model-catalogue-read-from-the-agent ADRs), so
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

  acceptance("chat", "an attached file is shown in the thread after a reload", async () => {
    // A fresh mount reads the persisted rows: the attachment reference comes back
    // as a chip naming the file and its type under the message text, with no path.
    chatApiMock.listMessages.mockResolvedValue({
      messages: [
        makeMsg({
          content: [
            { type: "text", text: "what is in this?" },
            { type: "attachment", filename: "report.pdf", mime: "application/pdf" },
          ],
        }),
      ],
    });
    renderThread();
    const chip = await screen.findByTestId("attachment-chip");
    expect(chip).toHaveTextContent("report.pdf");
    expect(chip).toHaveTextContent("application/pdf");
    expect(screen.getByText("what is in this?")).toBeInTheDocument();
  });

  test("an echo of a just-sent message shows its attachments before the row lands", async () => {
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderThread({
      pendingEchoes: [
        {
          id: "echo-9",
          text: "",
          attachments: [{ id: "a".repeat(32), filename: "shot.png", mime: "image/png" }],
          sentAt: Date.now(),
          afterSeq: -1,
        },
      ],
    });
    const chip = await screen.findByTestId("attachment-chip");
    expect(chip).toHaveTextContent("shot.png");
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
      liveMessage: { blocks: [{ type: "text", text: "Streaming reply..." }], streaming: true },
    });
    await waitFor(() => expect(screen.getByText("Streaming reply...")).toBeInTheDocument());
  });

  test("renders tool call card for live message with tool blocks", async () => {
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderThread({
      liveMessage: {
        streaming: true,
        blocks: [
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

  acceptance("chat", "editing a queued message re-queues it at the tail", async () => {
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
      liveMessage: { blocks: [{ type: "text", text: "live text" }], streaming: true },
    });
    await waitFor(() => expect(screen.getByText("live text")).toBeInTheDocument());
    // Exactly one in-progress bubble: the live one; the fetched placeholder is filtered.
    expect(screen.queryAllByText(/thinking/i)).toHaveLength(0);
  });

  acceptance("chat", "a just-sent prompt is shown before its row lands", async () => {
    // spec chat "Show a just-sent prompt immediately": the prompt must be
    // visible immediately, not only after the next messages fetch. The echo
    // comes from the turn hook, not from the thread.
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderThread({
      isStreaming: true,
      pendingEchoes: [
        { id: "echo-1", text: "my question", attachments: [], sentAt: Date.now(), afterSeq: -1 },
      ],
      liveMessage: { blocks: [{ type: "text", text: "replying" }], streaming: true },
    });
    await waitFor(() => expect(screen.getByText("my question")).toBeInTheDocument());
    expect(screen.getByText("replying")).toBeInTheDocument();
    // An echo is not the empty state.
    expect(screen.queryByText(/no messages/i)).not.toBeInTheDocument();
  });

  test("renders every echo it is given after the fetched rows — the thread does no dedupe", async () => {
    // Two identical consecutive prompts: the first is already persisted, the
    // second is still an echo. Which echoes stand is the turn hook's call (it
    // retires them by seq + time, see chatTurnEvents); the thread must render
    // both rather than suppress the echo because its text already appears.
    chatApiMock.listMessages.mockResolvedValue({
      messages: [
        makeMsg({ role: "user", content: [{ type: "text", text: "again" }] }),
        makeMsg({
          id: "msg-2",
          seq: 2,
          role: "assistant",
          content: [{ type: "text", text: "first answer" }],
        }),
      ],
    });
    renderThread({
      isStreaming: true,
      pendingEchoes: [
        { id: "echo-2", text: "again", attachments: [], sentAt: Date.now(), afterSeq: 2 },
      ],
      liveMessage: { blocks: [], streaming: true },
    });
    await waitFor(() => expect(screen.getByText("first answer")).toBeInTheDocument());
    expect(screen.getAllByText("again")).toHaveLength(2);
    // Order: persisted rows, then the echo, then the live bubble.
    const texts = screen.getAllByText(/again|first answer/).map((el) => el.textContent);
    expect(texts).toEqual(["again", "first answer", "again"]);
  });

  test("renders multiple echoes in send order", async () => {
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderThread({
      pendingEchoes: [
        { id: "echo-1", text: "first send", attachments: [], sentAt: 1, afterSeq: -1 },
        { id: "echo-2", text: "second send", attachments: [], sentAt: 2, afterSeq: -1 },
      ],
    });
    await waitFor(() => expect(screen.getByText("second send")).toBeInTheDocument());
    const texts = screen.getAllByText(/send$/).map((el) => el.textContent);
    expect(texts).toEqual(["first send", "second send"]);
  });

  test("readOnly hides the composer and shows a restore call-to-action", async () => {
    // spec chat "Open an archived conversation read-only": archived
    // conversations open read-only; restoring re-enables chat.
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

  test("a failed turn shows the error banner and never a 'Thinking…' bubble beside it", async () => {
    // A mid-turn stream drop leaves the live bubble streaming and a persisted
    // empty placeholder; with the error set, neither may keep "thinking".
    chatApiMock.listMessages.mockResolvedValue({
      messages: [
        makeMsg({ role: "user", content: [{ type: "text", text: "my question" }] }),
        makeMsg({ id: "msg-2", seq: 2, role: "assistant", status: "streaming", content: [] }),
      ],
    });
    renderThread({
      pendingEchoes: [
        { id: "echo-1", text: "my question", attachments: [], sentAt: Date.now(), afterSeq: -1 },
      ],
      liveMessage: { blocks: [], streaming: true },
      turnError: new Error("provider failed"),
    });
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/provider failed/i));
    // The failed user text stays on screen (the echo at once, the row when fetched).
    expect((await screen.findAllByText("my question")).length).toBeGreaterThan(0);
    await waitFor(() => expect(chatApiMock.listMessages).toHaveBeenCalled());
    expect(screen.queryByText(/thinking/i)).not.toBeInTheDocument();
  });

  acceptance("chat", "a failed turn offers a retry in the thread", async () => {
    chatApiMock.listMessages.mockResolvedValue({
      messages: [makeMsg({ role: "user", content: [{ type: "text", text: "try again" }] })],
    });
    const onSend = vi.fn();
    const onResend = vi.fn();
    const onClearTurnError = vi.fn();
    renderThread({ turnError: new Error("boom"), onSend, onResend, onClearTurnError });
    // Retry appears once the failed prompt is on screen (it is what gets re-sent).
    await waitFor(() => expect(screen.getByText("try again")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(onClearTurnError).toHaveBeenCalled();
    // The persisted message is resent by id, so the daemon rebuilds it whole.
    expect(onResend).toHaveBeenCalledWith("msg-1");
    expect(onSend).not.toHaveBeenCalled();
  });

  acceptance("chat", "a retry re-sends the failed message's attachments", async () => {
    // Before the failed prompt's row lands, Retry re-sends the echo as it was
    // sent: its text and its files' upload ids, never the text alone.
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    const png = { id: "a".repeat(32), filename: "shot.png", mime: "image/png" };
    const onSend = vi.fn();
    renderThread({
      turnError: new Error("boom"),
      onSend,
      pendingEchoes: [
        { id: "echo-1", text: "look", attachments: [png], sentAt: Date.now(), afterSeq: -1 },
      ],
    });
    fireEvent.click(await screen.findByRole("button", { name: /retry/i }));
    expect(onSend).toHaveBeenCalledWith("look", [png]);
  });

  test("a refused send offers no Retry — its message is still in the composer", async () => {
    chatApiMock.listMessages.mockResolvedValue({
      messages: [makeMsg({ role: "user", content: [{ type: "text", text: "older" }] })],
    });
    const onResend = vi.fn();
    renderThread({ turnError: new Error("refused"), retryable: false, onResend });
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/refused/i));
    await waitFor(() => expect(screen.getByText("older")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });

  test("a retry refused because its file was pruned says so", async () => {
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderThread({
      turnError: new ApiError("ATTACHMENT_EXPIRED", "attachment 'shot.png' is no longer stored"),
      retryable: false,
    });
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/deleted after 30 days/i),
    );
  });

  test("a not-logged-in agent error maps to actionable copy", async () => {
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderThread({ turnError: new Error("claude: Not logged in · run /login") });
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/isn't logged in on this machine/i),
    );
  });

  test("scrolling away from the bottom shows a Jump-to-latest pill that re-attaches", async () => {
    chatApiMock.listMessages.mockResolvedValue({ messages: [makeMsg({})] });
    const { container } = renderThread();
    await waitFor(() => expect(screen.getByText("Hello")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /jump to latest/i })).not.toBeInTheDocument();

    const scroller = container.querySelector("[tabindex='0']") as HTMLElement;
    Object.defineProperty(scroller, "scrollHeight", { configurable: true, value: 1000 });
    Object.defineProperty(scroller, "clientHeight", { configurable: true, value: 300 });
    scroller.scrollTop = 0;
    fireEvent.scroll(scroller);
    const pill = await screen.findByRole("button", { name: /jump to latest/i });
    fireEvent.click(pill);
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /jump to latest/i })).not.toBeInTheDocument(),
    );
  });

  acceptance("chat", "second message queues during a streaming turn", async () => {
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
