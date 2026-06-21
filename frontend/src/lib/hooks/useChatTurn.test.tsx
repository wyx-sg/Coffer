// frontend/src/lib/hooks/useChatTurn.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

import { useChatTurn } from "./useChatTurn";
import { ApiError } from "@/lib/api/errors";
import type { AgentEvent } from "@/lib/chat/streamClient";

// Mock the streamClient module — useChatTurn opens a GET /events subscription.
vi.mock("@/lib/chat/streamClient", () => ({
  subscribeConversationEvents: vi.fn(),
}));

// Mock chatApi — useChatTurn calls sendMessage / setPending / interruptTurn.
vi.mock("@/lib/api/chat", () => ({
  chatApi: {
    sendMessage: vi.fn(),
    setPending: vi.fn(),
    interruptTurn: vi.fn(),
  },
}));

const streamClientModule = await import("@/lib/chat/streamClient");
const subscribeMock = vi.mocked(streamClientModule.subscribeConversationEvents);
const { chatApi } = await import("@/lib/api/chat");
const chatApiMock = chatApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

/** A subscription generator that yields a fixed list of events then ends. */
function fromEvents(...events: AgentEvent[]) {
  return async function* () {
    for (const e of events) yield e;
  };
}

/** A subscription generator parked on a gate after the given events. */
function gatedSubscription(gate: Promise<void>, ...events: AgentEvent[]) {
  return async function* () {
    for (const e of events) yield e;
    await gate;
  };
}

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("useChatTurn", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: an empty subscription that ends immediately.
    subscribeMock.mockImplementation(fromEvents());
    chatApiMock.sendMessage.mockResolvedValue({ queued: false });
    chatApiMock.setPending.mockResolvedValue({ pending: [] });
    chatApiMock.interruptTurn.mockResolvedValue(undefined);
  });

  test("initial state: not streaming, no liveMessage, no error, empty pending", async () => {
    const { result } = renderHook(() => useChatTurn("conv-1"), {
      wrapper: makeWrapper(),
    });

    expect(result.current.isStreaming).toBe(false);
    expect(result.current.liveMessage).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.pending).toEqual([]);
    expect(typeof result.current.send).toBe("function");
    expect(typeof result.current.clearError).toBe("function");
    expect(typeof result.current.setPending).toBe("function");

    // Let the subscription's async consumer settle so its state updates land
    // inside act (the empty generator ends immediately).
    await act(async () => {});
  });

  test("opens the subscription for the conversation on mount", async () => {
    renderHook(() => useChatTurn("conv-7"), { wrapper: makeWrapper() });
    expect(subscribeMock).toHaveBeenCalledWith("conv-7", expect.any(AbortSignal));
    await act(async () => {});
  });

  test("send() POSTs the message fire-and-return and shows an optimistic echo", async () => {
    let resolveSend!: () => void;
    chatApiMock.sendMessage.mockImplementation(
      () => new Promise<{ queued: boolean }>((r) => (resolveSend = () => r({ queued: false }))),
    );

    const { result } = renderHook(() => useChatTurn("conv-1"), { wrapper: makeWrapper() });

    act(() => {
      void result.current.send("what is OAuth?");
    });

    // The prompt is echoed immediately, before the POST resolves.
    await waitFor(() => expect(result.current.liveMessage?.userText).toBe("what is OAuth?"));
    expect(chatApiMock.sendMessage).toHaveBeenCalledWith("conv-1", "what is OAuth?");

    await act(async () => {
      resolveSend();
    });
  });

  test("send() NEVER blocks while a turn streams — a second call still POSTs (queues)", async () => {
    // A turn is in flight via the subscription; sending again must not be gated.
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    subscribeMock.mockImplementation(gatedSubscription(gate, { event: "turn_start", data: {} }));

    const { result } = renderHook(() => useChatTurn("conv-1"), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isStreaming).toBe(true));

    await act(async () => {
      await result.current.send("queued message");
    });

    expect(chatApiMock.sendMessage).toHaveBeenCalledWith("conv-1", "queued message");
    release();
  });

  test("accumulates text_delta into the live bubble and clears it once the reply lands", async () => {
    // Gate the stream BEFORE turn_done so the accumulated live bubble is
    // observable; otherwise the whole burst resolves before the first poll and
    // the assertions could pass against the initial (empty) state vacuously.
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    subscribeMock.mockImplementation(async function* () {
      yield { event: "turn_start", data: {} };
      yield { event: "text_delta", data: { text: "Hello" } };
      yield { event: "text_delta", data: { text: " world" } };
      await gate;
      yield { event: "turn_done", data: { stop_reason: "end_turn" } };
    });

    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    // Before the reply lands the cache holds only the user message, so the
    // complete-reply count captured at turn_start is 0.
    qc.setQueryData(
      ["messages", "conv-1"],
      [
        {
          id: "u1",
          conversation_id: "conv-1",
          seq: 0,
          role: "user",
          content: [{ type: "text", text: "q" }],
          status: "complete",
          created_at: "",
        },
      ],
    );
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useChatTurn("conv-1"), { wrapper });

    // Both deltas accumulate into the one live bubble while the turn streams.
    await waitFor(() => expect(result.current.liveMessage?.text).toBe("Hello world"));
    expect(result.current.isStreaming).toBe(true);

    // The reply is persisted server-side; the post-turn refetch now carries it
    // (complete-reply count 0 → 1).
    qc.setQueryData(
      ["messages", "conv-1"],
      [
        {
          id: "u1",
          conversation_id: "conv-1",
          seq: 0,
          role: "user",
          content: [{ type: "text", text: "q" }],
          status: "complete",
          created_at: "",
        },
        {
          id: "a1",
          conversation_id: "conv-1",
          seq: 1,
          role: "assistant",
          content: [{ type: "text", text: "Hello world" }],
          status: "complete",
          created_at: "",
        },
      ],
    );
    await act(async () => {
      release();
    });

    // turn_done sees the NEW reply land, so the live bubble is dropped.
    await waitFor(() => expect(result.current.liveMessage).toBeNull());
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.error).toBeNull();
  });

  test("keeps the live bubble until the refetched messages carry the assistant reply (no flicker)", async () => {
    // Gate before turn_done so we can observe the streamed bubble being KEPT
    // while the turn runs, then dropped only once the refetch carries the reply.
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    subscribeMock.mockImplementation(async function* () {
      yield { event: "turn_start", data: {} };
      yield { event: "text_delta", data: { text: "The answer" } };
      await gate;
      yield { event: "turn_done", data: { stop_reason: "end_turn" } };
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    // Reply not yet persisted: the cache holds only the user message for now.
    qc.setQueryData(
      ["messages", "conv-1"],
      [
        {
          id: "u1",
          conversation_id: "conv-1",
          seq: 0,
          role: "user",
          content: [{ type: "text", text: "q" }],
          status: "complete",
          created_at: "",
        },
      ],
    );
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useChatTurn("conv-1"), { wrapper });

    // The streamed answer is shown in the live bubble and KEPT during the turn.
    await waitFor(() => expect(result.current.liveMessage?.text).toBe("The answer"));

    // The persisted reply lands; the turn_done refetch carries it (count 0 → 1).
    qc.setQueryData(
      ["messages", "conv-1"],
      [
        {
          id: "u1",
          conversation_id: "conv-1",
          seq: 0,
          role: "user",
          content: [{ type: "text", text: "q" }],
          status: "complete",
          created_at: "",
        },
        {
          id: "a1",
          conversation_id: "conv-1",
          seq: 1,
          role: "assistant",
          content: [{ type: "text", text: "The answer" }],
          status: "complete",
          created_at: "",
        },
      ],
    );
    await act(async () => {
      release();
    });

    // Only now — with the persisted reply present — is the live bubble dropped.
    await waitFor(() => expect(result.current.liveMessage).toBeNull());
  });

  test("does NOT clear the live bubble when the refetch still lacks the assistant reply", async () => {
    subscribeMock.mockImplementation(
      fromEvents(
        { event: "turn_start", data: {} },
        { event: "text_delta", data: { text: "The answer" } },
        { event: "turn_done", data: { stop_reason: "end_turn" } },
      ),
    );
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    // Refetch brings only the user message back — the assistant reply hasn't landed.
    qc.setQueryData(
      ["messages", "conv-1"],
      [
        {
          id: "u1",
          conversation_id: "conv-1",
          seq: 0,
          role: "user",
          content: [{ type: "text", text: "q" }],
          status: "complete",
          created_at: "",
        },
      ],
    );
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useChatTurn("conv-1"), { wrapper });

    await waitFor(() => expect(result.current.liveMessage?.text).toBe("The answer"));
    expect(result.current.liveMessage).not.toBeNull();
  });

  test("reconciles a stuck live bubble when the stream ends without turn_done", async () => {
    // The stream drops mid-turn (no turn_done reaches us) but the reply finished
    // server-side. On stream end the hook must refetch and drop the spinning
    // live bubble instead of leaving it on "thinking…" forever.
    // Gate the stream open AFTER the partial so the stuck (spinning) bubble is
    // observable, then end the stream with NO turn_done to drive the reconcile.
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    subscribeMock.mockImplementation(async function* () {
      yield { event: "turn_start", data: {} };
      yield { event: "text_delta", data: { text: "partial" } };
      await gate;
      // stream ends here — NO turn_done
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    qc.setQueryData(
      ["messages", "conv-1"],
      [
        {
          id: "a1",
          conversation_id: "conv-1",
          seq: 1,
          role: "assistant",
          content: [{ type: "text", text: "the full reply" }],
          status: "complete",
          created_at: "",
        },
      ],
    );
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useChatTurn("conv-1"), { wrapper });

    // While the stream is open the live bubble spins on the partial text.
    await waitFor(() => expect(result.current.liveMessage?.text).toBe("partial"));
    expect(result.current.isStreaming).toBe(true);

    // The stream then ends with no turn_done; reconcile sees the persisted
    // assistant reply and drops the stale bubble instead of spinning forever.
    await act(async () => {
      release();
    });
    await waitFor(() => expect(result.current.liveMessage).toBeNull());
    expect(result.current.isStreaming).toBe(false);
  });

  test("stream ending without a landed reply resets streaming but keeps the live text", async () => {
    // Stream ends with only the user message persisted (reply not yet landed):
    // the live bubble is kept (no premature clear) but streaming is reset.
    subscribeMock.mockImplementation(
      fromEvents(
        { event: "turn_start", data: {} },
        { event: "text_delta", data: { text: "still thinking text" } },
      ),
    );
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    qc.setQueryData(
      ["messages", "conv-1"],
      [
        {
          id: "u1",
          conversation_id: "conv-1",
          seq: 0,
          role: "user",
          content: [{ type: "text", text: "q" }],
          status: "complete",
          created_at: "",
        },
      ],
    );
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useChatTurn("conv-1"), { wrapper });

    // Wait for the UNIQUE terminal state — the live text landed AND streaming
    // reset — in one condition. Waiting only on `isStreaming === false` is racy:
    // that is also the hook's initial state, so under CI scheduling the wait can
    // resolve in the initial window (before the stream's events are processed),
    // when liveMessage is still null. Both assertions hold only once the stream
    // has ended, so this converges deterministically.
    await waitFor(() => {
      expect(result.current.liveMessage?.text).toBe("still thinking text");
      expect(result.current.isStreaming).toBe(false);
    });
  });

  test("turn_error surfaces an error and drops the live bubble", async () => {
    subscribeMock.mockImplementation(
      fromEvents(
        { event: "turn_start", data: {} },
        { event: "text_delta", data: { text: "thinking..." } },
        { event: "turn_error", data: { code: "MODEL_ERROR", message: "provider failed" } },
      ),
    );

    const { result } = renderHook(() => useChatTurn("conv-1"), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.error).toBeInstanceOf(ApiError));
    expect((result.current.error as ApiError).code).toBe("MODEL_ERROR");
    expect((result.current.error as ApiError).message).toContain("provider failed");
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.liveMessage).toBeNull();
  });

  test("a subscription failure surfaces as an error", async () => {
    subscribeMock.mockImplementation(async function* () {
      yield { event: "turn_start", data: {} };
      throw new Error("network failure");
    });

    const { result } = renderHook(() => useChatTurn("conv-1"), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
    expect((result.current.error as Error).message).toBe("network failure");
  });

  test("send() error (POST rejected) surfaces in hook state", async () => {
    chatApiMock.sendMessage.mockRejectedValue(new ApiError("CONVERSATION_NOT_FOUND", "gone"));
    const { result } = renderHook(() => useChatTurn("conv-1"), { wrapper: makeWrapper() });

    await act(async () => {
      await result.current.send("hi");
    });

    expect(result.current.error).toBeInstanceOf(ApiError);
    expect((result.current.error as ApiError).code).toBe("CONVERSATION_NOT_FOUND");
  });

  test("clearError resets error state", async () => {
    subscribeMock.mockImplementation(async function* () {
      yield { event: "turn_start", data: {} };
      throw new Error("network failure");
    });

    const { result } = renderHook(() => useChatTurn("conv-1"), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.error).not.toBeNull());

    act(() => {
      result.current.clearError();
    });

    expect(result.current.error).toBeNull();
  });

  test("accumulates tool_call and tool_result events without error", async () => {
    subscribeMock.mockImplementation(
      fromEvents(
        { event: "turn_start", data: {} },
        {
          event: "tool_call",
          data: {
            tool_use_id: "t1",
            tool_name: "coffer__search_memory",
            tool_input: { query: "OAuth" },
          },
        },
        {
          event: "tool_result",
          data: {
            tool_use_id: "t1",
            tool_name: "coffer__search_memory",
            output: { result: "found" },
            error: null,
          },
        },
        { event: "text_delta", data: { text: "Based on" } },
        { event: "turn_done", data: { stop_reason: "end_turn" } },
      ),
    );

    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    qc.setQueryData(
      ["messages", "conv-1"],
      [
        {
          id: "a1",
          conversation_id: "conv-1",
          seq: 1,
          role: "assistant",
          content: [{ type: "text", text: "Based on" }],
          status: "complete",
          created_at: "",
        },
      ],
    );
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useChatTurn("conv-1"), { wrapper });

    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    expect(result.current.error).toBeNull();
  });

  test("isStreaming is true while a turn streams and false once it ends", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    subscribeMock.mockImplementation(async function* () {
      yield { event: "turn_start", data: {} };
      await gate;
      yield { event: "turn_done", data: { stop_reason: "end_turn" } };
    });

    const { result } = renderHook(() => useChatTurn("conv-1"), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isStreaming).toBe(true));

    await act(async () => {
      release();
    });

    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    expect(result.current.error).toBeNull();
  });

  test("queue_changed updates the pending queue", async () => {
    subscribeMock.mockImplementation(
      fromEvents({ event: "queue_changed", data: { pending: ["one", "two"] } }),
    );

    const { result } = renderHook(() => useChatTurn("conv-1"), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.pending).toEqual(["one", "two"]));
  });

  test("setPending() PUTs the new queue and reflects the response", async () => {
    chatApiMock.setPending.mockResolvedValue({ pending: ["kept"] });
    const { result } = renderHook(() => useChatTurn("conv-9"), { wrapper: makeWrapper() });

    await act(async () => {
      await result.current.setPending(["kept", "dropped"]);
    });

    expect(chatApiMock.setPending).toHaveBeenCalledWith("conv-9", ["kept", "dropped"]);
    expect(result.current.pending).toEqual(["kept"]);
  });

  test("switching conversation aborts the old subscription and reopens for the new one", async () => {
    const signals: AbortSignal[] = [];
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    subscribeMock.mockImplementation(async function* (_id: string, signal?: AbortSignal) {
      if (signal) signals.push(signal);
      yield { event: "turn_start", data: {} };
      yield { event: "text_delta", data: { text: "partial A" } };
      await gate;
    });

    const { result, rerender } = renderHook(({ id }) => useChatTurn(id), {
      wrapper: makeWrapper(),
      initialProps: { id: "conv-A" },
    });

    await waitFor(() => expect(result.current.liveMessage?.text).toBe("partial A"));
    expect(result.current.isStreaming).toBe(true);

    act(() => {
      rerender({ id: "conv-B" });
    });

    // Conv-A's state must not bleed into conv-B; its subscription was aborted.
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.liveMessage).toBeNull();
    expect(signals[0]?.aborted).toBe(true);
    expect(subscribeMock).toHaveBeenCalledWith("conv-B", expect.any(AbortSignal));

    release();
  });

  test("interrupt() calls chatApi.interruptTurn for the conversation", async () => {
    const { result } = renderHook(() => useChatTurn("conv-9"), { wrapper: makeWrapper() });

    await act(async () => {
      await result.current.interrupt();
    });

    expect(chatApiMock.interruptTurn).toHaveBeenCalledWith("conv-9");
  });

  test("turn_start invalidates the messages query so a committed user message appears", async () => {
    subscribeMock.mockImplementation(
      fromEvents(
        { event: "turn_start", data: {} },
        { event: "turn_done", data: { stop_reason: "end_turn" } },
      ),
    );
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    renderHook(() => useChatTurn("conv-1"), { wrapper });

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["messages", "conv-1"] }),
    );
  });

  test("invalidates the conversations list on send, so the auto-generated title appears", async () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useChatTurn("conv-1"), { wrapper });

    await act(async () => {
      await result.current.send("hi");
    });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["conversations"] });
  });
});
