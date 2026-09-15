// frontend/src/lib/hooks/useMessageThread.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";

import { useMessageThread } from "./useMessageThread";
import { messagesKey } from "@/lib/api/queryKeys";
import type { Message } from "@/lib/api/chat";
import type { LiveMessage } from "@/lib/hooks/chatTurnEvents";

vi.mock("@/lib/api/chat", () => ({
  chatApi: { listMessages: vi.fn() },
}));

const { chatApi } = await import("@/lib/api/chat");
const listMessages = vi.mocked(chatApi.listMessages);

const row = (overrides: Partial<Message>): Message => ({
  id: "m1",
  conversation_id: "conv-1",
  seq: 1,
  role: "user",
  content: [{ type: "text", text: "hi" }],
  status: "complete",
  created_at: "2026-01-01T00:00:00Z",
  ...overrides,
});

const LIVE: LiveMessage = { text: "", toolBlocks: [], streaming: true };

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

describe("useMessageThread", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("fetches the conversation's messages under the shared messages key", async () => {
    listMessages.mockResolvedValue({ messages: [row({})] });
    const { qc, wrapper } = makeWrapper();
    const { result } = renderHook(() => useMessageThread("conv-1", null), { wrapper });

    expect(result.current.isPending).toBe(true);
    await waitFor(() => expect(result.current.messages).toHaveLength(1));
    expect(listMessages).toHaveBeenCalledWith("conv-1");
    expect(qc.getQueryData(messagesKey("conv-1"))).toHaveLength(1);
  });

  test("drops fetched streaming placeholder rows only while a live bubble is shown", async () => {
    listMessages.mockResolvedValue({
      messages: [row({}), row({ id: "m2", seq: 2, role: "assistant", status: "streaming" })],
    });
    const { wrapper } = makeWrapper();
    const { result, rerender } = renderHook(
      ({ live }: { live: LiveMessage | null }) => useMessageThread("conv-1", live),
      { wrapper, initialProps: { live: LIVE as LiveMessage | null } },
    );

    await waitFor(() => expect(result.current.messages).toHaveLength(1));
    expect(result.current.messages[0].id).toBe("m1");

    // No live bubble → the placeholder renders as the server-side in-progress row.
    rerender({ live: null });
    expect(result.current.messages).toHaveLength(2);
  });

  test("after a failed turn drops an empty streaming placeholder, never streamed text", async () => {
    listMessages.mockResolvedValue({
      messages: [
        row({}),
        row({ id: "m2", seq: 2, role: "assistant", status: "streaming", content: [] }),
        row({
          id: "m3",
          seq: 3,
          role: "assistant",
          status: "streaming",
          content: [{ type: "text", text: "so far" }],
        }),
      ],
    });
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useMessageThread("conv-1", null, new Error("boom")), {
      wrapper,
    });

    await waitFor(() => expect(result.current.messages).toHaveLength(2));
    expect(result.current.messages.map((m) => m.id)).toEqual(["m1", "m3"]);
  });

  test("surfaces a fetch failure as error with an empty list", async () => {
    listMessages.mockRejectedValue(new Error("boom"));
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useMessageThread("conv-1", null), { wrapper });

    await waitFor(() => expect(result.current.error).toBeInstanceOf(Error));
    expect(result.current.messages).toEqual([]);
  });
});
