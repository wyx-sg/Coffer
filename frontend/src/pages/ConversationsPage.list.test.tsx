// pages/ConversationsPage.list.test.tsx — the Conversations list as the Run
// canvas draws it (3.1.01–05, 20): day groups without counts, a row's status
// word, source and ⋯ menu, the filter row and its URL, and the list's error.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ConversationsPage } from "./ConversationsPage";
import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api/errors";
import { makeBinding, makeConversation } from "@/test/conversationFixtures";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/api/chat", () => ({
  chatApi: {
    listConversations: vi.fn(),
    archiveConversation: vi.fn(),
    unarchiveConversation: vi.fn(),
    deleteConversation: vi.fn(),
    batchConversations: vi.fn(),
    getConversation: vi.fn(),
    listMessages: vi.fn(),
  },
}));
vi.mock("@/lib/api/agentProviders", () => ({ agentProvidersApi: { list: vi.fn() } }));
vi.mock("@/lib/hooks/useChannels", () => ({
  useChannels: () => ({
    data: [
      { uid: "ch-1", name: "team-bot", title: "Team bot", config: { channel_type: "seatalk" } },
      { uid: "ch-2", name: "personal", title: "Personal", config: { channel_type: "telegram" } },
    ],
  }),
}));
vi.mock("@/lib/chat/streamClient", () => ({
  subscribeConversationEvents: vi.fn(async function* () {}),
}));

const { chatApi } = await import("@/lib/api/chat");
const api = chatApi as unknown as Record<string, ReturnType<typeof vi.fn>>;
const { agentProvidersApi } = await import("@/lib/api/agentProviders");

const at = (daysAgo: number, hour = 12) => {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  d.setHours(hour, 5, 0, 0);
  return d.toISOString();
};

const today = makeConversation({
  id: "t",
  title: "Today one",
  preview: "line of today",
  updated_at: at(0, 0),
  running: true,
});
const yesterday = makeConversation({
  id: "y",
  title: "Yesterday one",
  updated_at: at(1, 14),
  channel_binding: makeBinding({
    channel_uid: "ch-2",
    platform: "telegram",
    place: null,
    channel: "Personal",
  }),
});
const earlier = makeConversation({ id: "e", title: "Earlier one", updated_at: at(20, 9) });

function Probe() {
  const loc = useLocation();
  return (
    <output data-testid="loc">{`${loc.pathname}${loc.search}|${JSON.stringify(loc.state)}`}</output>
  );
}

function renderPage(path = "/conversations") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  vi.mocked(agentProvidersApi.list).mockResolvedValue({
    agents: [
      { agent_key: "claude_code", display_name: "Claude Code", available: true },
      { agent_key: "codex", display_name: "Codex", available: true },
    ],
  });
  const page = <ConversationsPage />;
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <TooltipProvider>
            <Probe />
            <Routes>
              <Route path="/conversations" element={page} />
              <Route path="/conversations/:id" element={<div>detail</div>} />
            </Routes>
          </TooltipProvider>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const row = (title: string) =>
  screen.getByRole("link", { name: title }).closest("li") as HTMLElement;
const loc = () => decodeURIComponent(screen.getByTestId("loc").textContent ?? "");

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  api.listConversations.mockResolvedValue({
    conversations: [today, yesterday, earlier],
    next_cursor: null,
    total: 3,
  });
  api.batchConversations.mockImplementation(async (_a: string, ids: string[]) => ({
    results: ids.map((id) => ({ id, outcome: "done", reason: null })),
  }));
});

describe("Conversations list", () => {
  test("the header is a title, one line and a solid New conversation, with no count anywhere", async () => {
    renderPage();
    await screen.findByRole("link", { name: "Today one" });
    expect(screen.getByRole("heading", { name: "Conversations" })).toBeInTheDocument();
    expect(
      screen.getByText("Every conversation, from Coffer and your channels."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /New conversation/ })).toBeInTheDocument();
    expect(screen.queryByText(/\b3 conversations\b/)).toBeNull();
  });

  acceptance("chat", "rows are grouped by day without counts", async () => {
    renderPage();
    await screen.findByRole("link", { name: "Today one" });
    const list = screen.getByRole("list", { name: "Conversations" });
    const groups = within(list)
      .getAllByRole("listitem", { hidden: true })
      .filter((li) => li.getAttribute("aria-hidden") === "true")
      .map((li) => li.textContent);
    expect(groups).toEqual(["Today", "Yesterday", "Earlier"]);
    expect(screen.queryByRole("columnheader")).toBeNull();
    // Today and yesterday show the clock, an earlier day its date.
    expect(row("Today one")).toHaveTextContent("00:05");
    expect(row("Yesterday one")).toHaveTextContent("14:05");
    expect(row("Earlier one")).toHaveTextContent(/^.*[A-Z][a-z]{2} \d{1,2}/);
  });

  test("a row shows its preview, source, agent and a Running word", async () => {
    renderPage();
    await screen.findByRole("link", { name: "Today one" });
    expect(row("Today one")).toHaveTextContent("line of today");
    expect(row("Today one")).toHaveTextContent("Running");
    expect(row("Today one")).toHaveTextContent("Coffer");
    expect(row("Today one")).toHaveTextContent("Claude Code");
    expect(row("Yesterday one")).toHaveTextContent("Telegram · Personal");
    expect(row("Yesterday one")).not.toHaveTextContent("Running");
  });

  test("Needs you shows when the conversation says so", async () => {
    api.listConversations.mockResolvedValue({
      conversations: [{ ...today, needs_you: true }],
      next_cursor: null,
      total: 1,
    });
    renderPage();
    await screen.findByRole("link", { name: "Today one" });
    expect(row("Today one")).toHaveTextContent("Needs you");
    expect(row("Today one")).not.toHaveTextContent("Running");
  });

  acceptance("chat", "a row's menu acts on one conversation", async () => {
    renderPage();
    await screen.findByRole("link", { name: "Today one" });
    fireEvent.click(within(row("Today one")).getByRole("button", { name: "More actions" }));
    const menu = await screen.findByRole("menu");
    expect(
      within(menu)
        .getAllByRole("menuitem")
        .map((i) => i.textContent),
    ).toEqual(["Rename", "Archive", "Delete…"]);
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Rename" }));
    await waitFor(() => expect(loc()).toBe('/conversations/t|{"rename":true}'));
  });

  test("Archive acts at once and the toast has Undo", async () => {
    api.batchConversations.mockClear();
    renderPage();
    await screen.findByRole("link", { name: "Today one" });
    fireEvent.click(within(row("Today one")).getByRole("button", { name: "More actions" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Archive" }));
    await waitFor(() => expect(api.batchConversations).toHaveBeenCalledWith("archive", ["t"]));
    fireEvent.click(await screen.findByRole("button", { name: "Undo" }));
    await waitFor(() => expect(api.batchConversations).toHaveBeenCalledWith("unarchive", ["t"]));
  });

  test("Delete… asks first, naming the conversation", async () => {
    api.deleteConversation.mockResolvedValue(undefined);
    renderPage();
    await screen.findByRole("link", { name: "Today one" });
    fireEvent.click(within(row("Today one")).getByRole("button", { name: "More actions" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Delete…" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Delete “Today one”?")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(api.deleteConversation).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete conversation" }));
    await waitFor(() => expect(api.deleteConversation.mock.calls[0][0]).toBe("t"));
  });

  test("the archived view offers Unarchive and Delete… and no Rename", async () => {
    api.listConversations.mockResolvedValue({
      conversations: [{ ...today, archived_at: at(2) }],
      next_cursor: null,
      total: 1,
    });
    renderPage("/conversations?archived=1");
    await screen.findByRole("link", { name: "Today one" });
    fireEvent.click(within(row("Today one")).getByRole("button", { name: "More actions" }));
    const menu = await screen.findByRole("menu");
    expect(
      within(menu)
        .getAllByRole("menuitem")
        .map((i) => i.textContent),
    ).toEqual(["Unarchive", "Delete…"]);
  });
});

describe("Conversations filter row", () => {
  test("segmented first, then the search, then the Source and Agent pills", async () => {
    renderPage();
    await screen.findByRole("link", { name: "Today one" });
    const search = screen.getByRole("textbox", { name: "Search titles and messages" });
    const view = screen.getByRole("group", { name: "View" });
    const source = screen.getByRole("button", { name: /^Source/ });
    const agent = screen.getByRole("button", { name: /^Agent/ });
    const before = (a: Node, b: Node) =>
      Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    expect(before(view, search)).toBe(true);
    expect(before(search, source)).toBe(true);
    expect(before(source, agent)).toBe(true);
    expect(screen.queryByRole("button", { name: "Clear filters" })).toBeNull();
  });

  test("/ focuses the search, and typing puts q in the URL", async () => {
    renderPage();
    await screen.findByRole("link", { name: "Today one" });
    fireEvent.keyDown(document.body, { key: "/" });
    const search = screen.getByRole("textbox", { name: "Search titles and messages" });
    expect(search).toHaveFocus();
    fireEvent.change(search, { target: { value: "sentry" } });
    await waitFor(() => expect(loc()).toContain("?q=sentry"));
  });

  acceptance("chat", "the Source pill filters by several sources", async () => {
    renderPage();
    await screen.findByRole("link", { name: "Today one" });
    fireEvent.click(screen.getByRole("button", { name: /^Source/ }));
    fireEvent.click(await screen.findByRole("option", { name: "Coffer" }));
    fireEvent.click(screen.getByRole("option", { name: "Telegram · Personal" }));
    expect(screen.getByRole("option", { name: "SeaTalk · Team bot" })).toBeInTheDocument();
    await waitFor(() => expect(loc()).toContain("?source=coffer,ch-2"));
    await waitFor(() => expect(screen.queryByRole("link", { name: "Earlier one" })).not.toBeNull());
    expect(screen.getByRole("link", { name: "Yesterday one" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear filters" })).toBeInTheDocument();
  });

  test("the Agent pill narrows by agent and Clear filters resets everything", async () => {
    api.listConversations.mockResolvedValue({
      conversations: [today, { ...earlier, agent_key: "codex" }],
      next_cursor: null,
      total: 2,
    });
    renderPage("/conversations?q=x");
    await screen.findByRole("link", { name: "Today one" });
    fireEvent.click(screen.getByRole("button", { name: /^Agent/ }));
    fireEvent.click(await screen.findByRole("option", { name: "Codex" }));
    await waitFor(() => expect(screen.queryByRole("link", { name: "Today one" })).toBeNull());
    await waitFor(() => expect(loc()).toContain("agent=codex"));
    fireEvent.keyDown(document.body, { key: "Escape" });
    fireEvent.click(await screen.findByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(loc().split("|")[0]).toBe("/conversations"));
  });

  test("a legacy ?channel= link is rewritten to ?source= once", async () => {
    renderPage("/conversations?channel=ch-1");
    await waitFor(() => expect(loc().split("|")[0]).toBe("/conversations?source=ch-1"));
  });
});

describe("Conversations list states", () => {
  test("with no conversation at all there is the header and one message, no filter row", async () => {
    api.listConversations.mockResolvedValue({ conversations: [], next_cursor: null, total: 0 });
    renderPage();
    expect(await screen.findByText("No conversations yet")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "View" })).toBeNull();
  });

  test("an empty archive says so, without a strip", async () => {
    api.listConversations.mockResolvedValue({ conversations: [], next_cursor: null, total: 0 });
    renderPage("/conversations?archived=1");
    expect(await screen.findByText("No archived conversations")).toBeInTheDocument();
  });

  acceptance("chat", "a list that fails to load says so", async () => {
    api.listConversations.mockRejectedValueOnce(new ApiError("INTERNAL_ERROR", "boom"));
    renderPage();
    expect(await screen.findByText("Couldn’t load conversations")).toBeInTheDocument();
    api.listConversations.mockResolvedValue({
      conversations: [today],
      next_cursor: null,
      total: 1,
    });
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("link", { name: "Today one" })).toBeInTheDocument();
  });
});
