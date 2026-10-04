// pages/ConversationsPage.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConversationsPage } from "./ConversationsPage";
import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { makeBinding, makeConversation } from "@/test/conversationFixtures";
import { acceptance } from "@/test/acceptance";
import type { Conversation, Message } from "@/lib/api/chat";
import { contentBlock } from "@/lib/chat/contentBlock";
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
        secret_ref: "ref",
        compatible_agents: ["claude_code"],
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
  useChannels: () => ({
    data: [
      { uid: "ch-1", name: "team-bot", title: "Team bot", config: { channel_type: "seatalk" } },
    ],
  }),
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
        <ToastProvider>
          <TooltipProvider>
            <Routes>
              <Route path="/conversations" element={page} />
              <Route path="/conversations/:id" element={page} />
            </Routes>
          </TooltipProvider>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

/** New conversation: straight to the draft, with its composer (no dialog). */
async function openDraft() {
  fireEvent.click(await screen.findByRole("button", { name: /new conversation/i }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  return screen.findByRole("textbox", { name: /message input/i });
}

function send(box: HTMLElement, text: string) {
  fireEvent.change(box, { target: { value: text } });
  fireEvent.keyDown(box, { key: "Enter", shiftKey: false });
}

/** The daemon's listing narrowed by `source` the way the server does it. */
function serveBySource(all: ReturnType<typeof makeConv>[]) {
  chatApiMock.listConversations.mockImplementation(async (opts: { source?: string[] }) => ({
    conversations: opts.source?.length
      ? all.filter((c) => opts.source!.includes(c.channel_binding?.channel_uid ?? "coffer"))
      : all,
  }));
}

describe("ConversationsPage list", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  // Opens on the list — no welcome, no composer — with New conversation beside it.
  acceptance("chat", "the page opens on the list with no welcome page", async () => {
    chatApiMock.listConversations.mockResolvedValue({
      conversations: [makeConv({ title: "Fix reconnect" }), channelConv],
    });
    chatApiMock.getConversation.mockResolvedValue(makeConv({ title: "Fix reconnect" }));
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    const view = renderPage("/conversations");
    expect(await screen.findByRole("link", { name: "Fix reconnect" })).toHaveAttribute(
      "href",
      "/conversations/conv-1",
    );
    expect(screen.getByText("SeaTalk · coffer-dev › thread")).toBeInTheDocument();
    expect(screen.getByText("3 new issues since yesterday")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /new conversation/i })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /message input/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/welcome|suggestion/i)).not.toBeInTheDocument();
    view.unmount();

    // The composer of an open conversation has no voice input.
    renderPage("/conversations/conv-1");
    const composer = await screen.findByTestId("composer");
    expect(
      within(composer).queryByRole("button", { name: /voice|dictat|microphone|record/i }),
    ).not.toBeInTheDocument();
  });

  acceptance("chat", "a row names the chat and thread it came from", async () => {
    const binding = (place: Partial<NonNullable<ReturnType<typeof makeBinding>["place"]>>) =>
      makeBinding({
        place: {
          chat_kind: "direct",
          thread: false,
          parallel_mark: null,
          chat_name: null,
          ...place,
        },
      });
    chatApiMock.listConversations.mockResolvedValue({
      conversations: [
        makeConv({
          id: "dm",
          title: "In the DM",
          preview: "dm line",
          channel_binding: binding({}),
        }),
        makeConv({
          id: "grp",
          title: "In the group thread",
          preview: "group line",
          channel_binding: binding({ chat_kind: "group", chat_name: "coffer-dev", thread: true }),
        }),
        makeConv({
          id: "par",
          title: "Parallel work",
          preview: "parallel line",
          running: true,
          channel_binding: binding({ parallel_mark: "🧵#2 deploy check", thread: true }),
        }),
      ],
    });
    renderPage("/conversations");
    const row = async (title: string) =>
      (await screen.findByRole("link", { name: title })).closest("li")!;
    const dm = await row("In the DM");
    expect(dm).toHaveTextContent("SeaTalk · DM");
    expect(dm).toHaveTextContent("dm line");
    expect(dm).not.toHaveTextContent("Running");
    const grp = await row("In the group thread");
    expect(grp).toHaveTextContent("SeaTalk · coffer-dev › thread");
    expect(grp).toHaveTextContent("group line");
    const par = await row("Parallel work");
    expect(par).toHaveTextContent("SeaTalk · DM · Thread 2");
    expect(par).toHaveTextContent("parallel line");
    expect(par).toHaveTextContent("Running");
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

      fireEvent.click(screen.getByRole("button", { name: /^Source/ }));
      fireEvent.click(await screen.findByRole("option", { name: "SeaTalk · Team bot" }));
      await waitFor(() => expect(screen.queryByText("From the web")).not.toBeInTheDocument());
      expect(screen.getByText("Daily Sentry triage")).toBeInTheDocument();
    },
  );

  test("a channel's link narrows the list to that channel, named in the Source pill", async () => {
    serveBySource([makeConv({ title: "From the web" }), channelConv]);
    renderPage("/conversations?source=ch-1");
    expect(await screen.findByText("Daily Sentry triage")).toBeInTheDocument();
    expect(screen.queryByText("From the web")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /^Source:\s*SeaTalk · Team bot/ }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(await screen.findByText("From the web")).toBeInTheDocument();
  });

  test("a legacy ?channel= link is read once as a source", async () => {
    serveBySource([makeConv({ title: "From the web" }), channelConv]);
    renderPage("/conversations?channel=ch-1");
    expect(await screen.findByText("Daily Sentry triage")).toBeInTheDocument();
    expect(screen.queryByText("From the web")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /^Source:\s*SeaTalk · Team bot/ }),
    ).toBeInTheDocument();
  });

  test("with nothing matching the filters, Clear filters brings every conversation back", async () => {
    serveBySource([makeConv({ title: "From the web" })]);
    renderPage("/conversations?source=ch-9");
    expect(await screen.findByText("No conversations match")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(await screen.findByText("From the web")).toBeInTheDocument();
  });

  test("the archived list has no explanatory strip", async () => {
    chatApiMock.listConversations.mockImplementation(async (opts: { archived?: boolean }) => ({
      conversations: opts.archived
        ? [makeConv({ id: "old", title: "Old work", archived_at: "2026-02-01T00:00:00Z" })]
        : [makeConv({ title: "From the web" })],
    }));
    renderPage("/conversations?archived=1");
    expect(await screen.findByText("Old work")).toBeInTheDocument();
    expect(screen.queryByText(/read-only/i)).not.toBeInTheDocument();
  });

  test("with no conversation at all, the empty state is only the header and a message", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    renderPage("/conversations");
    expect(await screen.findByText("No conversations yet")).toBeInTheDocument();
    expect(
      screen.getByText("Start one here, or message one of your channels from SeaTalk or Telegram."),
    ).toBeInTheDocument();
    // The header's button is the only one: the empty state does not repeat it.
    expect(screen.getAllByRole("button", { name: /new conversation/i })).toHaveLength(1);
    expect(screen.queryByRole("textbox", { name: "Search titles and messages" })).toBeNull();
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

  test("the last folder is the draft's default and is carried into the create", async () => {
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

  test("New conversation opens the draft with no dialog and no request", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [makeConv()] });
    chatApiMock.getConversation.mockResolvedValue(makeConv());
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderPage("/conversations");

    await openDraft();
    expect(await screen.findByText(/New conversation with Claude Code in/)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(chatApiMock.createConversation).not.toHaveBeenCalled();
  });

  test("the folder and agent last used are the next draft's defaults", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    chatApiMock.createConversation.mockResolvedValue(makeConv({ id: "new-conv" }));
    renderPage("/conversations/new", [
      { agent_key: "claude_code", display_name: "Claude Code", available: true },
      { agent_key: "codex", display_name: "Codex", available: true },
    ]);
    // Choose a typed folder on the draft, then send.
    fireEvent.click(await screen.findByRole("button", { name: "Workspace" }));
    fireEvent.change(await screen.findByRole("textbox", { name: /folder path/i }), {
      target: { value: "/Users/me/other" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Use" }));
    send(await screen.findByRole("textbox", { name: /message input/i }), "hi");
    await waitFor(() =>
      expect(chatApiMock.createConversation).toHaveBeenCalledWith({
        agent_key: "claude_code",
        agent_config: { cwd: "/Users/me/other" },
      }),
    );
    expect(localStorage.getItem("coffer.conversations.lastWorkingDir")).toBe("/Users/me/other");
    expect(localStorage.getItem("coffer.conversations.lastAgent")).toBe("claude_code");
  });

  test("the draft with no managed agent available says how to get one", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    renderPage("/conversations/new", [
      { agent_key: "claude_code", display_name: "Claude Code", available: false },
    ]);
    expect(await screen.findByText("No agent connected")).toBeInTheDocument();
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

  acceptance("chat", "a channel's conversation is continued from the page", async () => {
    const msg = (seq: number, role: Message["role"], text: string): Message => ({
      id: `m-${seq}`,
      conversation_id: "conv-st",
      seq,
      role,
      content: [contentBlock({ type: "text", text })],
      status: "complete",
      prompt_tokens: null,
      completion_tokens: null,
      model_id: null,
      finished_at: null,
      created_at: "2026-01-01T00:00:00Z",
    });
    chatApiMock.listConversations.mockResolvedValue({ conversations: [channelConv] });
    chatApiMock.getConversation.mockResolvedValue(channelConv);
    chatApiMock.listMessages.mockResolvedValue({
      messages: [
        msg(1, "user", "Any new Sentry issues?"),
        msg(2, "assistant", "Three since yesterday."),
      ],
    });
    renderPage("/conversations/conv-st");
    // The full exchange the channel had …
    expect(await screen.findByText("Any new Sentry issues?")).toBeInTheDocument();
    expect(await screen.findByText("Three since yesterday.")).toBeInTheDocument();
    // … and a reply from the page is a turn in that same conversation.
    const composer = await screen.findByTestId("composer");
    send(within(composer).getByRole("textbox", { name: /message input/i }), "Which is worst?");
    await waitFor(() =>
      expect(chatApiMock.sendMessage).toHaveBeenCalledWith("conv-st", "Which is worst?", []),
    );
    expect(chatApiMock.createConversation).not.toHaveBeenCalled();
  });

  test("/conversations/:id opens that conversation full width, headed by its source, with no list beside it", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [makeConv(), channelConv] });
    chatApiMock.getConversation.mockResolvedValue(channelConv);
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderPage("/conversations/conv-st");
    expect(await screen.findByRole("heading", { name: "Daily Sentry triage" })).toBeInTheDocument();
    expect(
      await screen.findByText(/send a message to start the conversation/i),
    ).toBeInTheDocument();
    // No list column: not the other conversation, not the filters, not a search box.
    expect(screen.queryByRole("link", { name: /Test Conv/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: /source/i })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("textbox", { name: /search conversations/i }),
    ).not.toBeInTheDocument();
  });

  test("the draft is full width too", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [makeConv()] });
    renderPage("/conversations/new?agent=codex");
    expect(await screen.findByText(/New conversation with Claude Code in/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Test Conv/ })).not.toBeInTheDocument();
  });

  test("the list groups conversations under time headings", async () => {
    const now = new Date();
    chatApiMock.listConversations.mockResolvedValue({
      conversations: [
        makeConv({ id: "a", title: "Fresh one", updated_at: now.toISOString() }),
        makeConv({ id: "b", title: "Ancient one", updated_at: "2020-01-01T00:00:00Z" }),
      ],
    });
    renderPage("/conversations");
    expect(await screen.findByText("Today")).toBeInTheDocument();
    expect(screen.getByText("Earlier")).toBeInTheDocument();
    expect(screen.queryByText("Yesterday")).not.toBeInTheDocument();
  });

  acceptance("chat", "delete asks first, naming the conversation", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [makeConv()] });
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderPage("/conversations/conv-1");

    fireEvent.click(await screen.findByRole("button", { name: /more actions/i }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Delete…" }));

    expect(await screen.findByText("Delete “Test Conv”?")).toBeInTheDocument();
    expect(
      screen.getByText(
        "“Test Conv” and its messages are removed from Coffer; files the agent changed stay. To keep it out of the way instead, archive it.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete conversation" })).toBeInTheDocument();
    expect(chatApiMock.deleteConversation).not.toHaveBeenCalled();
  });

  test("the title bar row has the title and ⋯, and no back link, archived pill or page header", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [makeConv()] });
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderPage("/conversations/conv-1");
    const bar = await screen.findByTestId("content-title-bar");
    expect(within(bar).getByRole("heading", { name: "Test Conv" })).toBeInTheDocument();
    expect(within(bar).getByRole("button", { name: "More actions" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /conversations/i })).not.toBeInTheDocument();
    expect(screen.queryByText("Archived")).not.toBeInTheDocument();
  });

  acceptance("chat", "rename a conversation in place", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [makeConv()] });
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    chatApiMock.updateConversation.mockResolvedValue(makeConv({ title: "Better name" }));
    renderPage("/conversations/conv-1");

    fireEvent.click(await screen.findByRole("button", { name: "More actions" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Rename" }));
    const input = await screen.findByRole("textbox", { name: "Conversation title" });
    expect(screen.getByText("Enter to save · Esc to cancel")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.change(input, { target: { value: "Better name" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() =>
      expect(chatApiMock.updateConversation).toHaveBeenCalledWith("conv-1", {
        title: "Better name",
      }),
    );
    expect(screen.queryByRole("textbox", { name: "Conversation title" })).not.toBeInTheDocument();
  });

  test("Esc cancels a rename and keeps the title", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [makeConv()] });
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderPage("/conversations/conv-1");

    fireEvent.click(await screen.findByRole("button", { name: "Test Conv" }));
    const input = await screen.findByRole("textbox", { name: "Conversation title" });
    fireEvent.change(input, { target: { value: "Nope" } });
    fireEvent.keyDown(input, { key: "Escape" });

    expect(screen.queryByRole("textbox", { name: "Conversation title" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Test Conv" })).toBeInTheDocument();
    expect(chatApiMock.updateConversation).not.toHaveBeenCalled();
  });

  test("the list's Rename opens the conversation with its title already being edited", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [makeConv()] });
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    renderPage({ pathname: "/conversations/conv-1", state: { rename: true } });
    expect(await screen.findByRole("textbox", { name: "Conversation title" })).toHaveValue(
      "Test Conv",
    );
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
    // Unarchive lives in the notice that stands in for the reply box, not in the menu.
    expect(screen.getByRole("button", { name: /unarchive to continue/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "More actions" }));
    expect(screen.queryByRole("menuitem", { name: "Unarchive" })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Archive" })).not.toBeInTheDocument();
  });

  test("unarchiving an archived thread re-enables the composer", async () => {
    chatApiMock.listConversations.mockResolvedValue({ conversations: [] });
    chatApiMock.getConversation
      .mockResolvedValueOnce(makeConv({ archived_at: "2026-02-01T00:00:00Z" }))
      .mockResolvedValue(makeConv({ archived_at: null }));
    chatApiMock.listMessages.mockResolvedValue({ messages: [] });
    chatApiMock.unarchiveConversation.mockResolvedValue(makeConv({ archived_at: null }));
    renderPage("/conversations/conv-1");

    fireEvent.click(await screen.findByRole("button", { name: /unarchive to continue/i }));

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
    expect(screen.getByRole("button", { name: "Workspace" })).toHaveTextContent("~/work");
    expect(screen.getByText("Nothing is sent until you press Send.")).toBeInTheDocument();
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
