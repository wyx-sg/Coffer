// components/chat/MessageThread.mirror.test.tsx
// A channel conversation's thread says where a reply also goes and marks the
// replies its channel has not received yet (spec chat "Show where a reply will
// also be sent"). The mirror comes from the single-conversation GET: the list
// row the page opens the thread with carries `mirror: null`.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { MessageThread } from "./MessageThread";
import { acceptance } from "@/test/acceptance";
import type { ChannelMirror, Conversation, Message } from "@/lib/api/chat";
import { contentBlock } from "@/lib/chat/contentBlock";

vi.mock("@/lib/api/chat", () => ({
  chatApi: {
    listMessages: vi.fn(),
    getConversation: vi.fn(),
    getAgentConfig: vi.fn().mockResolvedValue({ model: null, effort: null }),
  },
}));
vi.mock("@/lib/hooks/useProviders", () => ({ useProviders: () => ({ data: [] }) }));
vi.mock("@/lib/hooks/useModelIntrospection", () => ({
  useListProviderModels: () => ({ mutate: vi.fn() }),
}));

const { chatApi } = await import("@/lib/api/chat");
const chatApiMock = chatApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

const BINDING = {
  channel: "st",
  channel_uid: "u-st",
  chat_id: "g-1",
  platform: "seatalk" as const,
  place: null,
};

const LISTED: Conversation = {
  id: "conv-1",
  agent_key: "claude_code",
  title: "deploy check",
  archived_at: null,
  channel_binding: { ...BINDING, mirror: null },
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  preview: null,
  running: false,
};

const userMsg = (id: string, text: string): Message => ({
  id,
  conversation_id: "conv-1",
  seq: Number(id.slice(-1)),
  role: "user",
  content: [contentBlock({ type: "text", text })],
  status: "complete",
  prompt_tokens: null,
  completion_tokens: null,
  model_id: null,
  finished_at: null,
  created_at: "2026-01-01T00:00:00Z",
});

function withMirror(mirror: ChannelMirror): Conversation {
  return { ...LISTED, channel_binding: { ...BINDING, mirror } };
}

function renderThread(conversation: Conversation = LISTED) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <MessageThread
          conversation={conversation}
          liveMessage={null}
          isStreaming={false}
          onSend={vi.fn()}
        />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("MessageThread channel mirror", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chatApiMock.listMessages.mockResolvedValue({
      messages: [userMsg("m1", "ship it"), userMsg("m2", "and the docs")],
    });
  });

  acceptance("chat", "the Conversations page shows where a reply also goes", async () => {
    chatApiMock.getConversation.mockResolvedValue(
      withMirror({
        deliverable: true,
        platform: "seatalk",
        target: "SeaTalk · 🧵#1 deploy check",
        reason: null,
        undelivered: [
          { kind: "reply", text: "(from Coffer) and the docs", created_at: "2026-01-01T00:01:00Z" },
          { kind: "answer", text: "ship it", created_at: "2026-01-01T00:02:00Z" },
        ],
      }),
    );
    renderThread();

    expect(
      await screen.findByText("Also sends to SeaTalk · 🧵#1 deploy check"),
    ).toBeInTheDocument();
    expect(chatApiMock.getConversation).toHaveBeenCalledWith("conv-1");
    // Only the reply the channel still owes is marked — an owed answer marks no user bubble.
    const marks = await screen.findAllByText("Not delivered to SeaTalk yet");
    expect(marks).toHaveLength(1);
    expect(marks[0]!.closest(".items-end")).toHaveTextContent("and the docs");
  });

  test("a reply that stays in Coffer says so", async () => {
    chatApiMock.getConversation.mockResolvedValue(
      withMirror({
        deliverable: false,
        platform: "seatalk",
        target: "SeaTalk · group",
        reason: "group_main",
        undelivered: [],
      }),
    );
    renderThread();

    expect(await screen.findByText("Replies stay in Coffer")).toBeInTheDocument();
    expect(screen.queryByText(/Also sends to/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /more info/i })).toBeInTheDocument();
  });

  test("a web conversation has no hint and fetches no detail", async () => {
    renderThread({ ...LISTED, channel_binding: null });

    expect(await screen.findByText("ship it")).toBeInTheDocument();
    expect(chatApiMock.getConversation).not.toHaveBeenCalled();
    expect(screen.queryByText(/Also sends to|Replies stay in Coffer/)).not.toBeInTheDocument();
  });
});
