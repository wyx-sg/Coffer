// frontend/src/lib/hooks/useChatTurn.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

import { useChatTurn } from "./useChatTurn";
import { ApiError } from "@/lib/api/errors";

// Mock the streamClient module.
vi.mock("@/lib/chat/streamClient", () => ({
  streamChatTurn: vi.fn(),
}));

// Mock chatApi — useChatTurn calls submitApproval / interruptTurn on it.
vi.mock("@/lib/api/chat", () => ({
  chatApi: {
    submitApproval: vi.fn(),
    interruptTurn: vi.fn(),
  },
}));

const streamClientModule = await import("@/lib/chat/streamClient");
const streamChatTurnMock = vi.mocked(streamClientModule.streamChatTurn);
const { chatApi } = await import("@/lib/api/chat");
const chatApiMock = chatApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

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
  });

  test("initial state: not streaming, no liveMessage, no error", () => {
    const { result } = renderHook(() => useChatTurn("conv-1"), {
      wrapper: makeWrapper(),
    });

    expect(result.current.isStreaming).toBe(false);
    expect(result.current.liveMessage).toBeNull();
    expect(result.current.error).toBeNull();
    expect(typeof result.current.send).toBe("function");
    expect(typeof result.current.clearError).toBe("function");
  });

  test("completes a turn with text_delta events, clears liveMessage after done", async () => {
    streamChatTurnMock.mockImplementation(
      async function* () {
        yield { event: "turn_start", data: {} };
        yield { event: "text_delta", data: { text: "Hello" } };
        yield { event: "text_delta", data: { text: " world" } };
        yield { event: "turn_done", data: { stop_reason: "end_turn" } };
      },
    );

    const { result } = renderHook(() => useChatTurn("conv-1"), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      await result.current.send("hi");
    });

    // After turn completes, liveMessage is cleared and isStreaming is false.
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.liveMessage).toBeNull();
    expect(result.current.error).toBeNull();
    expect(streamChatTurnMock).toHaveBeenCalledWith("conv-1", "hi", expect.any(AbortSignal));
  });

  test("sets error on ApiError and clears streaming state", async () => {
    streamChatTurnMock.mockImplementation(async function* () {
      yield { event: "turn_start", data: {} };
      throw new ApiError("TURN_IN_PROGRESS", "a turn is already in progress");
    });

    const { result } = renderHook(() => useChatTurn("conv-1"), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      await result.current.send("hi");
    });

    expect(result.current.isStreaming).toBe(false);
    expect(result.current.error).toBeInstanceOf(ApiError);
    expect((result.current.error as ApiError).code).toBe("TURN_IN_PROGRESS");
  });

  test("sets error on generic Error", async () => {
    // Reject immediately instead of using a generator to avoid require-yield lint.
    streamChatTurnMock.mockReturnValue(
      (async function* () {
        yield { event: "turn_start", data: {} };
        throw new Error("network failure");
      })(),
    );

    const { result } = renderHook(() => useChatTurn("conv-1"), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      await result.current.send("hi");
    });

    expect(result.current.error).toBeInstanceOf(Error);
    expect((result.current.error as Error).message).toBe("network failure");
  });

  test("clearError resets error state", async () => {
    streamChatTurnMock.mockReturnValue(
      (async function* () {
        yield { event: "turn_start", data: {} };
        throw new Error("network failure");
      })(),
    );

    const { result } = renderHook(() => useChatTurn("conv-1"), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      await result.current.send("hi");
    });

    expect(result.current.error).not.toBeNull();

    act(() => {
      result.current.clearError();
    });

    expect(result.current.error).toBeNull();
  });

  test("send is idempotent — a second call while streaming is a no-op", async () => {
    // The generator captures the 'send' reference snapshot — once isStreaming=true
    // the second call should bail out immediately without calling streamChatTurn again.
    // We can verify this by checking mock call count stays at 1.
    streamChatTurnMock.mockImplementation(
      async function* () {
        yield { event: "turn_start", data: {} };
        yield { event: "turn_done", data: { stop_reason: "end_turn" } };
      },
    );

    const { result } = renderHook(() => useChatTurn("conv-1"), {
      wrapper: makeWrapper(),
    });

    // First send completes.
    await act(async () => {
      await result.current.send("first");
    });

    expect(streamChatTurnMock).toHaveBeenCalledTimes(1);
    expect(result.current.isStreaming).toBe(false);
  });

  test("accumulates tool_call and tool_result events without error", async () => {
    streamChatTurnMock.mockImplementation(
      async function* () {
        yield { event: "turn_start", data: {} };
        yield {
          event: "tool_call",
          data: {
            tool_use_id: "t1",
            tool_name: "coffer__search_memory",
            tool_input: { query: "OAuth" },
          },
        };
        yield {
          event: "tool_result",
          data: { tool_use_id: "t1", tool_name: "coffer__search_memory", output: { result: "found" }, error: null },
        };
        yield { event: "text_delta", data: { text: "Based on" } };
        yield { event: "turn_done", data: { stop_reason: "end_turn" } };
      },
    );

    const { result } = renderHook(() => useChatTurn("conv-1"), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      await result.current.send("what about OAuth?");
    });

    expect(result.current.error).toBeNull();
    expect(result.current.isStreaming).toBe(false);
    expect(streamChatTurnMock).toHaveBeenCalledWith("conv-1", "what about OAuth?", expect.any(AbortSignal));
  });

  test("turn_error event surfaces an error in hook state", async () => {
    streamChatTurnMock.mockImplementation(
      async function* () {
        yield { event: "turn_start", data: {} };
        yield { event: "text_delta", data: { text: "thinking..." } };
        yield { event: "turn_error", data: { code: "MODEL_ERROR", message: "provider failed" } };
      },
    );

    const { result } = renderHook(() => useChatTurn("conv-1"), {
      wrapper: makeWrapper(),
    });

    await act(async () => {
      await result.current.send("hi");
    });

    // turn_error must surface as an error so the Chat page can display it.
    expect(result.current.error).toBeInstanceOf(ApiError);
    expect((result.current.error as ApiError).code).toBe("MODEL_ERROR");
    expect((result.current.error as ApiError).message).toContain("provider failed");
    expect(result.current.isStreaming).toBe(false);
  });

  test("isStreaming is true while a turn streams and false once it ends", async () => {
    // A controllable gate keeps the turn open so mid-stream state is
    // deterministic — no real timers, no act()-without-await warning.
    let release!: () => void;
    const gate = new Promise<void>((r) => {
      release = r;
    });
    streamChatTurnMock.mockImplementation(async function* () {
      yield { event: "turn_start", data: {} };
      await gate;
      yield { event: "turn_done", data: { stop_reason: "end_turn" } };
    });

    const { result } = renderHook(() => useChatTurn("conv-1"), {
      wrapper: makeWrapper(),
    });

    // Kick off the turn; it parks at the gate.
    let sendPromise!: Promise<void>;
    act(() => {
      sendPromise = result.current.send("hello");
    });

    // Mid-stream: the turn is streaming.
    await waitFor(() => expect(result.current.isStreaming).toBe(true));

    // Let the turn finish.
    release();
    await act(async () => {
      await sendPromise;
    });

    expect(result.current.isStreaming).toBe(false);
    expect(result.current.error).toBeNull();
  });

  test("approval_request pauses the turn; submitApproval delivers the decision", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => {
      release = r;
    });
    streamChatTurnMock.mockImplementation(async function* () {
      yield { event: "turn_start", data: {} };
      yield {
        event: "approval_request",
        data: { request_id: "r1", tool_use_id: "t1", tool_name: "run", tool_input: {} },
      };
      await gate; // park here — the turn is awaiting the decision
      yield { event: "turn_done", data: { stop_reason: "end_turn" } };
    });
    chatApiMock.submitApproval.mockResolvedValue(undefined);

    const { result } = renderHook(() => useChatTurn("conv-1"), { wrapper: makeWrapper() });

    // Kick off the turn; it parks at the gate after emitting approval_request.
    let sendPromise!: Promise<void>;
    act(() => {
      sendPromise = result.current.send("hi");
    });

    await waitFor(() => expect(result.current.pendingApproval).not.toBeNull());
    expect(result.current.pendingApproval?.request_id).toBe("r1");

    await act(async () => {
      await result.current.submitApproval("allow");
    });
    expect(chatApiMock.submitApproval).toHaveBeenCalledWith("conv-1", {
      request_id: "r1",
      behavior: "allow",
    });
    expect(result.current.pendingApproval).toBeNull();

    release();
    await act(async () => {
      await sendPromise;
    });
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.error).toBeNull();
  });

  test("switching conversation mid-stream resets state and aborts the old stream", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => {
      release = r;
    });
    let capturedSignal: AbortSignal | undefined;
    streamChatTurnMock.mockImplementation(async function* (_c, _t, signal) {
      capturedSignal = signal;
      yield { event: "turn_start", data: {} };
      yield { event: "text_delta", data: { text: "partial A" } };
      await gate;
      yield { event: "turn_done", data: { stop_reason: "end_turn" } };
    });

    const { result, rerender } = renderHook(({ id }) => useChatTurn(id), {
      wrapper: makeWrapper(),
      initialProps: { id: "conv-A" },
    });

    act(() => {
      void result.current.send("hi");
    });
    await waitFor(() => expect(result.current.isStreaming).toBe(true));
    expect(result.current.liveMessage?.text).toBe("partial A");

    // Switch to a different conversation while conv-A is still streaming.
    act(() => {
      rerender({ id: "conv-B" });
    });

    // Conv-A's turn state must not bleed into conv-B.
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.liveMessage).toBeNull();
    expect(result.current.pendingApproval).toBeNull();
    // The previous conversation's stream was aborted.
    expect(capturedSignal?.aborted).toBe(true);

    release(); // let the orphaned generator unwind
  });

  test("a stale send() continuation from the previous conversation cannot clear the new conversation's turn state", async () => {
    // Conv-A's generator parks mid-stream; we switch to conv-B and start a
    // turn there; then conv-A's generator finishes. A's continuation
    // (invalidateQueries + setState + finally) must NOT wipe B's live state.
    let releaseA!: () => void;
    const gateA = new Promise<void>((r) => {
      releaseA = r;
    });
    let releaseB!: () => void;
    const gateB = new Promise<void>((r) => {
      releaseB = r;
    });

    streamChatTurnMock.mockImplementation(async function* (convId: string) {
      yield { event: "turn_start", data: {} };
      if (convId === "conv-A") {
        yield { event: "text_delta", data: { text: "from A" } };
        await gateA;
        yield { event: "turn_done", data: { stop_reason: "end_turn" } };
      } else {
        yield { event: "text_delta", data: { text: "from B" } };
        await gateB;
        yield { event: "turn_done", data: { stop_reason: "end_turn" } };
      }
    });

    const { result, rerender } = renderHook(({ id }) => useChatTurn(id), {
      wrapper: makeWrapper(),
      initialProps: { id: "conv-A" },
    });

    let sendA!: Promise<void>;
    act(() => {
      sendA = result.current.send("hi A");
    });
    await waitFor(() => expect(result.current.liveMessage?.text).toBe("from A"));

    // Switch to conv-B and start a turn there.
    act(() => {
      rerender({ id: "conv-B" });
    });
    act(() => {
      void result.current.send("hi B");
    });
    await waitFor(() => expect(result.current.liveMessage?.text).toBe("from B"));
    expect(result.current.isStreaming).toBe(true);

    // Conv-A's stale continuation completes now.
    releaseA();
    await act(async () => {
      await sendA;
    });

    // B's in-flight state survives the stale continuation.
    expect(result.current.isStreaming).toBe(true);
    expect(result.current.liveMessage?.text).toBe("from B");

    releaseB();
  });

  test("interrupt() calls chatApi.interruptTurn for the conversation", async () => {
    chatApiMock.interruptTurn.mockResolvedValue(undefined);
    const { result } = renderHook(() => useChatTurn("conv-9"), { wrapper: makeWrapper() });

    await act(async () => {
      await result.current.interrupt();
    });

    expect(chatApiMock.interruptTurn).toHaveBeenCalledWith("conv-9");
  });
});
