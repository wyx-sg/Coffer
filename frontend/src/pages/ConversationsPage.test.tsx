// pages/ConversationsPage.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConversationsPage } from "./ConversationsPage";
import { TooltipProvider } from "@/components/ui/tooltip";
import { makeBinding, makeConversation } from "@/test/conversationFixtures";
import { acceptance } from "@/test/acceptance";
import type { Conversation } from "@/lib/api/chat";
import { ApiError } from "@/lib/api/errors";

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
    // Per-conversation managed-agent model (the
    // coffer-model-is-an-internal-engine and model-catalogue-read-from-the-agent ADRs).
    getAgentConfig: vi.fn().mockResolvedValue({ cwd: null, model: null }),
    setAgentModel: vi.fn().mockResolvedValue({ cwd: null, model: null }),
    // Fire-and-return turn control (ADR chat-single-owner-live-mirror).
    sendMessage: vi.fn().mockResolvedValue({ queued: false }),
    resendMessage: vi.fn().mockResolvedValue({ queued: false }),
    uploadAttachment: vi.fn(),
    setPending: vi.fn().mockResolvedValue({ pending: [] }),
    interruptTurn: vi.fn().mockResolvedValue(undefined),
  },
}));

// The agents a conversation can run on come from the turn platform's provider
// registry (GET /agent-providers), which outlived the page's own /chat/agents.
vi.mock("@/lib/api/agentProviders", () => ({ agentProvidersApi: { list: vi.fn() } }));

// The model picker's provider suggestions are out of scope for these page tests,
// but the draft surface needs an active connection (otherwise it shows the
// no-connection empty state instead of the composer).
vi.mock("@/lib/hooks/useProviders", () => ({
  useProviders: () => ({
    data: [
      {
        name: "official",
        protocol: "anthropic",
        base_url: "https://api.anthropic.com",
        credential_ref: "ref",
        compatible_agents: ["claude_code"],
        is_active: true,
        internal_default: false,
        transcribe_default: false,
        fallback: true,
        enabled: true,
        description: null,
        created_at: "",
        updated_at: "",
      },
    ],
  }),
}));
// The model picker lists the daemon's answer for this agent — with a connection
// active that is the connection's curated ids, resolved server-side. It used to
// introspect the endpoint from the browser and union the result with the agent's
// own catalogue; it no longer touches the network, so there is nothing to mock
// beyond the one read it does.
vi.mock("@/lib/hooks/useAgentModels", () => ({
  useAgentModels: () => ({
    data: [
      {
        id: "claude-opus-4-8",
        label: "",
        description: "",
        efforts: [],
        default_effort: null,
      },
    ],
  }),
}));

vi.mock("@/lib/hooks/useChannels", () => ({
  useChannels: () => ({ data: [{ uid: "ch-1", name: "team-bot", title: "Team bot" }] }),
}));

vi.mock("@/lib/chat/streamClient", () => ({
  // The persistent GET /events subscription — an async generator that ends
  // immediately so no turn is in flight in these page-level tests.
  subscribeConversationEvents: vi.fn(async function* () {}),
}));

const { chatApi } = await import("@/lib/api/chat");
const chatApiMock = chatApi as unknown as Record<string, ReturnType<typeof vi.fn>>;
const { agentProvidersApi } = await import("@/lib/api/agentProviders");
const listAgentsMock = vi.mocked(agentProvidersApi.list);

const makeConv = (overrides?: Partial<Conversation>): Conversation => makeConversation(overrides);

const channelConv = makeConv({
  id: "conv-st",
  title: "Daily Sentry triage",
  preview: "3 new issues since yesterday",
  channel_binding: makeBinding({
    place: { chat_kind: "group", thread: true, parallel_mark: null, chat_name: "coffer-dev" },
  }),
});

function renderPage(
  initialPath: string | { pathname: string; state: unknown } = "/conversations",
  agents?: { agent_key: string; display_name: string; available: boolean }[],
) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  listAgentsMock.mockResolvedValue({
    agents: agents ?? [{ agent_key: "claude_code", display_name: "Claude Code", available: true }],
  });
  // One element for both addresses, exactly as router.tsx mounts it.
  const page = <ConversationsPage />;
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <QueryClientProvider client={qc}>
        <TooltipProvider>
          <Routes>
            <Route path="/conversations" element={page} />
            <Route path="/conversations/:id" element={page} />
          </Routes>
        </TooltipProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

/** New conversation → Start: the draft, with its composer. */
async function openDraft() {
  fireEvent.click(await screen.findByRole("button", { name: /new conversation/i }));
  const start = await screen.findByRole("button", { name: /^start$/i });
  await waitFor(() => expect(start).toBeEnabled());
  fireEvent.click(start);
  return screen.findByRole("textbox", { name: /message input/i });
}

function send(box: HTMLElement, text: string) {
  fireEvent.change(box, { target: { value: text } });
  fireEvent.keyDown(box, { key: "Enter", shiftKey: false });
}

describe("ConversationsPage list", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  test("opens on the list — no welcome, no composer — with New conversation beside it", async () => {
    chatApiMock.listConversations.mockResolvedValue({
      conversations: [makeConv({ title: "Fix reconnect" }), channelConv],
    });
    renderPage("/conversations");
    expect(await screen.findByRole("link", { name: "Fix reconnect" })).toHaveAttribute(
      "href",
      "/conversations/conv-1",
    );
    expect(screen.getByText("SeaTalk · coffer-dev › thread")).toBeInTheDocument();
    expect(screen.getByText("3 new issues since yesterday")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /new conversation/i })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /message input/i })).not.toBeInTheDocument();
  });

  acceptance(
    "chat",
    "a channel's conversation is listed beside the web's with a badge",
    async () => {
      chatApiMock.listConversations.mockResolvedValue({
        conversations: [makeConv({ title: "From the web" }), channelConv],
      });
      renderPage("/conversations");
      expect(await screen.findByText("From the web")).toBeInTheDocument();
      expect(screen.getAllByText("Coffer").length).toBeGreaterThan(0);

      fireEvent.click(screen.getByRole("button", { name: "SeaTalk" }));
      await waitFor(() => expect(screen.queryByText("From the web")).not.toBeInTheDocument());
      expect(screen.getByText("Daily Sentry triage")).toBeInTheDocument();
    },
  );

  test("a channel's link narrows the list to that channel, named in a chip that clears", async () => {
    chatApiMock.listConversations.mockResolvedValue({
      conversations: [makeConv({ title: "From the web" }), channelConv],
    });
    renderPage("/conversations?channel=ch-1");
    expect(await screen.findByText("Daily Sentry triage")).toBeInTheDocument();
    expect(screen.queryByText("From the web")).not.toBeInTheDocument();
    expect(screen.getByText("Channel: Team bot")).toBeInTheDocument();
    // The source switch stays beside the chip.
    expect(screen.getByRole("group", { name: "Source" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /clear channel filter/i }));
    expect(await screen.findByText("From the web")).toBeInTheDocument();
    expect(screen.queryByText("Channel: Team bot")).not.toBeInTheDocument();
  });

  test("with nothing matching the filters, Clear filters brings every conversation back", async () => {
    chatApiMock.listConversations.mockResolvedValue({
      conversations: [makeConv({ title: "From the web" })],
    });
    renderPage("/conversations?source=telegram");
    expect(await screen.findByText("No conversations match")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(await screen.findByText("From the web")).toBeInTheDocument();
  });

  test("the archived list says how to continue an archived conversation", async () => {
    chatApiMock.listConversations.mockImplementation(async (archived?: boolean) => ({
      conversations: archived
        ? [makeConv({ id: "old", title: "Old work", archived_at: "2026-02-01T00:00:00Z" })]
        : [makeConv({ title: "From the web" })],
    }));
    renderPage("/conversations?archived=1");
    expect(await screen.findByText("Old work")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Archived conversations are read-only. Open one and choose Restore from its ⋯ menu to continue it.",
      ),
    ).toBeInTheDocument();
  });

  test("with no conversation at all, one empty state offers New conversation", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    renderPage("/conversations");
    expect(await screen.findByText("No conversations yet")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /new conversation/i }).length).toBeGreaterThan(0);
  });
});

describe("ConversationsPage draft", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  acceptance("chat", "the draft creates the conversation on first send", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    chatApiMock.createConversation.mockResolvedValue(makeConv({ id: "new-conv" }));
    renderPage("/conversations");

    // Opening the draft creates nothing; the first send does.
    const composer = await openDraft();
    expect(chatApiMock.createConversation).not.toHaveBeenCalled();
    send(composer, "hello there");

    // No folder chosen: no cwd, so the turn runs in Coffer's own workspace.
    await waitFor(() =>
      expect(chatApiMock.createConversation).toHaveBeenCalledWith({
        agent_key: "claude_code",
        agent_config: {},
      }),
    );
  });

  test("the working directory chosen in New conversation is carried into the create", async () => {
    localStorage.setItem("coffer.conversations.lastWorkingDir", "/Users/me/project");
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    chatApiMock.createConversation.mockResolvedValue(makeConv({ id: "new-conv" }));
    renderPage("/conversations");

    send(await openDraft(), "hi");
    await waitFor(() =>
      expect(chatApiMock.createConversation).toHaveBeenCalledWith({
        agent_key: "claude_code",
        agent_config: { cwd: "/Users/me/project" },
      }),
    );
  });

  test("a draft model is carried into the created conversation's agent_config", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    chatApiMock.createConversation.mockResolvedValue(makeConv({ id: "new-conv" }));
    renderPage("/conversations");
    const composer = await openDraft();

    const trigger = await screen.findByRole("combobox", { name: /agent model/i });
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    fireEvent.click(screen.getByRole("option", { name: "claude-opus-4-8" }));
    send(composer, "hi");

    await waitFor(() =>
      expect(chatApiMock.createConversation).toHaveBeenCalledWith({
        agent_key: "claude_code",
        agent_config: { model: "claude-opus-4-8" },
      }),
    );
  });

  test("the draft with no managed agent available says how to get one", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    renderPage("/conversations/new", [
      { agent_key: "claude_code", display_name: "Claude Code", available: false },
    ]);
    expect(await screen.findByText("No managed agent available")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /message input/i })).not.toBeInTheDocument();
  });

  test("surfaces an error when creating a conversation fails", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    chatApiMock.createConversation.mockRejectedValue(new Error("boom"));
    renderPage("/conversations/new");
    send(await screen.findByRole("textbox", { name: /message input/i }), "hi");
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  acceptance(
    "chat",
    "a draft's first message refused after its conversation is created keeps its text and files",
    async () => {
      const shot = { id: "a".repeat(32), filename: "shot.png", mime: "image/png", size: 2048 };
      chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
      chatApiMock.listMessages.mockResolvedValue({ messages: [] });
      chatApiMock.createConversation.mockResolvedValue(makeConv({ id: "new-conv" }));
      chatApiMock.getConversation.mockResolvedValue(makeConv({ id: "new-conv" }));
      chatApiMock.uploadAttachment.mockResolvedValue(shot);
      chatApiMock.sendMessage.mockRejectedValueOnce(
        new ApiError("ATTACHMENT_NOT_FOUND", "attachment not found"),
      );
      renderPage("/conversations/new");

      const draft = await screen.findByRole("textbox", { name: /message input/i });
      fireEvent.change(screen.getByTestId("composer-file-input"), {
        target: { files: [new File([new Uint8Array(2048)], "shot.png", { type: "image/png" })] },
      });
      await waitFor(() => expect(screen.getByRole("button", { name: /send/i })).toBeEnabled());
      fireEvent.change(draft, { target: { value: "what is this?" } });
      fireEvent.keyDown(draft, { key: "Enter", shiftKey: false });

      // The conversation is created, then its first message is refused.
      await waitFor(() =>
        expect(chatApiMock.sendMessage).toHaveBeenCalledWith("new-conv", "what is this?", [
          shot.id,
        ]),
      );
      // The refusal is shown — without a Retry, since the message never ran …
      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent(/no longer available/i);
      expect(within(alert).queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
      // … and the new conversation's composer holds the text and the file again.
      const composer = screen.getByTestId("composer");
      await waitFor(() =>
        expect(within(composer).getByTestId("attachment-chip")).toHaveTextContent("shot.png"),
      );
      expect(within(composer).getByRole("textbox", { name: /message input/i })).toHaveValue(
        "what is this?",
      );
      expect(screen.getByText(/send a message to start the conversation/i)).toBeInTheDocument();

      // Sending it again from there carries the same file.
      chatApiMock.sendMessage.mockResolvedValueOnce({ queued: false });
      fireEvent.click(within(composer).getByRole("button", { name: /send/i }));
      await waitFor(() =>
        expect(chatApiMock.sendMessage).toHaveBeenLastCalledWith("new-conv", "what is this?", [
          shot.id,
        ]),
      );
    },
  );
});

describe("ConversationsPage open conversation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  test("/conversations/:id opens that conversation beside the list, headed by its source", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [makeConv(), channelConv] });
    chatApiMock.getConversation.mockResolvedValue(channelConv);
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderPage("/conversations/conv-st");
    expect(await screen.findByRole("heading", { name: "Daily Sentry triage" })).toBeInTheDocument();
    // The list and the thread load on their own queries; wait for each.
    expect(await screen.findByRole("link", { name: /Test Conv/ })).toBeInTheDocument();
    expect(await screen.findByText(/send a message to start the conversation/i)).toBeInTheDocument();
  });

  test("deleting a conversation from its menu asks for confirmation first", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [makeConv()] });
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderPage("/conversations/conv-1");

    fireEvent.click(await screen.findByRole("button", { name: /more actions/i }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Delete…" }));

    expect(await screen.findByText(/delete this conversation\?/i)).toBeInTheDocument();
    expect(
      screen.getByText(
        "“Test Conv” and its messages are removed from Coffer. Files the agent changed and Claude Code’s own session files stay. This can’t be undone — Archive keeps it instead.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete conversation" })).toBeInTheDocument();
    expect(chatApiMock.deleteConversation).not.toHaveBeenCalled();
  });

  test("archiving from the menu needs no confirmation", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [makeConv()] });
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    chatApiMock.archiveConversation.mockResolvedValue(
      makeConv({ archived_at: "2026-02-01T00:00:00Z" }),
    );
    renderPage("/conversations/conv-1");

    fireEvent.click(await screen.findByRole("button", { name: /more actions/i }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Archive" }));

    await waitFor(() => expect(chatApiMock.archiveConversation).toHaveBeenCalled());
    expect(chatApiMock.archiveConversation.mock.calls[0][0]).toBe("conv-1");
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  acceptance("chat", "an archived conversation opens read-only", async () => {
    // Archived rows are not in the active list — the thread still opens (by-id
    // fetch), read-only, instead of falling through to the draft.
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
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
    renderPage("/conversations/conv-1");

    expect(await screen.findByText("old question")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /message input/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /restore/i })).toBeInTheDocument();
  });

  test("restoring an archived thread unarchives it and re-enables the composer", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    chatApiMock.getConversation
      .mockResolvedValueOnce(makeConv({ archived_at: "2026-02-01T00:00:00Z" }))
      .mockResolvedValue(makeConv({ archived_at: null }));
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    chatApiMock.unarchiveConversation.mockResolvedValue(makeConv({ archived_at: null }));
    renderPage("/conversations/conv-1");

    fireEvent.click(await screen.findByRole("button", { name: /restore to continue/i }));

    await waitFor(() => expect(chatApiMock.unarchiveConversation).toHaveBeenCalled());
    expect(chatApiMock.unarchiveConversation.mock.calls[0][0]).toBe("conv-1");
    expect(await screen.findByRole("textbox", { name: /message input/i })).toBeInTheDocument();
  });

  acceptance("chat", "a stale conversation link says so", async () => {
    // Typing into a draft here would silently create a NEW conversation.
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    chatApiMock.getConversation.mockRejectedValue(
      new ApiError("CONVERSATION_NOT_FOUND", "conversation not found"),
    );
    renderPage("/conversations/nope");

    expect(await screen.findByText("Conversation not found")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /message input/i })).not.toBeInTheDocument();

    // The way out: New conversation, then the draft's composer.
    fireEvent.click(screen.getByRole("button", { name: /start a new conversation/i }));
    fireEvent.click(await screen.findByRole("button", { name: /^start$/i }));
    expect(await screen.findByRole("textbox", { name: /message input/i })).toBeInTheDocument();
  });
});

describe("ConversationsPage hand-off", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  test("the draft opens with the prompt in the composer and nothing is sent until Send", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    chatApiMock.createConversation.mockResolvedValue(makeConv({ id: "new-conv" }));
    chatApiMock.getConversation.mockResolvedValue(makeConv({ id: "new-conv" }));
    renderPage({
      pathname: "/conversations/new",
      state: {
        handoff: { agentKey: "claude_code", cwd: "/Users/me/work", prompt: "Install jq 1.6." },
      },
    });

    const box = await screen.findByRole("textbox", { name: /message input/i });
    await waitFor(() => expect(box).toHaveValue("Install jq 1.6."));
    expect(screen.getByText("/Users/me/work")).toBeInTheDocument();
    // Pre-filled, not sent: no conversation exists and no turn has run.
    await new Promise((r) => setTimeout(r, 20));
    expect(chatApiMock.createConversation).not.toHaveBeenCalled();
    expect(chatApiMock.sendMessage).not.toHaveBeenCalled();

    fireEvent.keyDown(box, { key: "Enter", shiftKey: false });
    await waitFor(() =>
      expect(chatApiMock.createConversation).toHaveBeenCalledWith({
        agent_key: "claude_code",
        agent_config: { cwd: "/Users/me/work" },
      }),
    );
    await waitFor(() =>
      expect(chatApiMock.sendMessage).toHaveBeenCalledWith("new-conv", "Install jq 1.6.", []),
    );
  });
});
