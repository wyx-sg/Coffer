// pages/ConversationsPage.test.tsx — the Conversations page as the Run canvas
// draws it: a list of the conversations IM channels opened and nothing else —
// day groups without counts, a row's channel, status word, Stop and ⋯ menu, the
// filter row and its URL, rename and delete, and the list's states.
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
    renameConversation: vi.fn(),
    deleteConversation: vi.fn(),
    interruptTurn: vi.fn(),
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

const { chatApi } = await import("@/lib/api/chat");
const api = chatApi as unknown as Record<string, ReturnType<typeof vi.fn>>;
const { agentProvidersApi } = await import("@/lib/api/agentProviders");

const at = (daysAgo: number, hour = 12) => {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  d.setHours(hour, 5, 0, 0);
  return d.toISOString();
};

const place = (p: Partial<NonNullable<ReturnType<typeof makeBinding>["place"]>>) => ({
  chat_kind: "direct" as const,
  thread: false,
  parallel_mark: null,
  chat_name: null,
  ...p,
});

const today = makeConversation({
  id: "t",
  title: "Today one",
  updated_at: at(0, 0),
  running: true,
});
const yesterday = makeConversation({
  id: "y",
  title: "Yesterday one",
  updated_at: at(1, 14),
  cwd: "/work/web",
  channel_binding: makeBinding({
    channel_uid: "ch-2",
    platform: "telegram",
    place: null,
    channel: "Personal",
  }),
});
const earlier = makeConversation({
  id: "e",
  title: "Earlier one",
  updated_at: at(20, 9),
  agent_key: "codex",
});

function Probe() {
  const loc = useLocation();
  return <output data-testid="loc">{`${loc.pathname}${loc.search}`}</output>;
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
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <TooltipProvider>
            <Probe />
            <Routes>
              <Route path="/conversations" element={<ConversationsPage />} />
            </Routes>
          </TooltipProvider>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const row = (title: string) => screen.getByText(title).closest("li") as HTMLElement;
/** A row by its id: it stays findable while its title is an input. */
const rowOf = (id: string) => document.querySelector(`li[data-session="${id}"]`) as HTMLElement;
const loc = () => decodeURIComponent(screen.getByTestId("loc").textContent ?? "");
const listed = (...rows: ReturnType<typeof makeConversation>[]) =>
  api.listConversations.mockResolvedValue({
    conversations: rows,
    next_cursor: null,
    total: rows.length,
  });
const openMenu = async (title: string) => {
  fireEvent.click(within(row(title)).getByRole("button", { name: `More actions for ${title}` }));
  return screen.findByRole("menu");
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  listed(today, yesterday, earlier);
});

describe("Conversations list", () => {
  acceptance("chat", "the page opens on the list with no welcome page", async () => {
    renderPage();
    await screen.findByText("Today one");
    expect(screen.getByRole("heading", { name: "Conversations" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /New conversation/ })).toBeNull();
    // The only text box is the search: there is no reply box.
    expect(screen.getAllByRole("textbox").map((e) => e.getAttribute("aria-label"))).toEqual([
      "Search titles and directories",
    ]);
    expect(screen.queryByText(/Start a conversation|Suggestions/)).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
  });

  acceptance("chat", "a channel's conversations are listed with the channel's badge", async () => {
    renderPage();
    await screen.findByText("Today one");
    expect(row("Today one")).toHaveTextContent("SeaTalk · DM");
    expect(row("Yesterday one")).toHaveTextContent("Telegram · Personal");
    expect(row("Earlier one")).toHaveTextContent("SeaTalk · DM");
    expect(api.listConversations.mock.calls[0][0].source).toEqual([]);
    // Filtering by one channel asks the server for that channel's.
    fireEvent.click(screen.getByRole("button", { name: /^Channel/ }));
    fireEvent.click(await screen.findByRole("option", { name: "Telegram · Personal" }));
    await waitFor(() => expect(loc()).toContain("?source=ch-2"));
    await waitFor(() =>
      expect(api.listConversations.mock.calls.at(-1)?.[0]).toMatchObject({ source: ["ch-2"] }),
    );
  });

  acceptance("chat", "a row names the chat and thread it came from", async () => {
    const dm = makeConversation({
      id: "dm",
      title: "From a DM",
      updated_at: at(0, 3),
      channel_binding: makeBinding({ place: place({}) }),
    });
    const group = makeConversation({
      id: "grp",
      title: "From a group",
      updated_at: at(0, 2),
      channel_binding: makeBinding({
        place: place({ chat_kind: "group", chat_name: "coffer-dev", thread: true }),
      }),
    });
    const parallel = makeConversation({
      id: "par",
      title: "Parallel one",
      updated_at: at(0, 1),
      running: true,
      cwd: "/work/api",
      channel_binding: makeBinding({
        place: place({ parallel_mark: "🧵#2 deploy check", thread: true }),
      }),
    });
    listed(dm, group, parallel);
    renderPage();
    await screen.findByText("From a DM");
    expect(row("From a DM")).toHaveTextContent("SeaTalk · DM");
    expect(row("From a group")).toHaveTextContent("SeaTalk · coffer-dev › thread");
    expect(row("Parallel one")).toHaveTextContent("SeaTalk · DM · Thread 2");
    expect(row("Parallel one")).toHaveTextContent("Claude Code");
    expect(row("Parallel one")).toHaveTextContent("/work/api");
    expect(row("Parallel one")).toHaveTextContent("Running");
    expect(row("From a DM")).not.toHaveTextContent("Running");
  });

  acceptance("chat", "rows are grouped by day without counts", async () => {
    renderPage();
    await screen.findByText("Today one");
    const list = screen.getByRole("list", { name: "Conversations" });
    const groups = within(list)
      .getAllByRole("listitem", { hidden: true })
      .filter((li) => li.hasAttribute("data-band"))
      .map((li) => li.textContent);
    expect(groups).toEqual(["Today", "Yesterday", "Earlier"]);
    expect(screen.queryByRole("columnheader")).toBeNull();
    // Today and yesterday show the clock, an earlier day its date.
    expect(row("Today one")).toHaveTextContent("00:05");
    expect(row("Yesterday one")).toHaveTextContent("14:05");
    expect(row("Earlier one")).toHaveTextContent(/[A-Z][a-z]{2} \d{1,2}/);
  });

  test("a row shows the agent and the abbreviated working directory", async () => {
    listed({ ...today, cwd: "/home/me/work/api" }, { ...yesterday, agent_key: "codex" });
    renderPage();
    await screen.findByText("Today one");
    expect(row("Today one")).toHaveTextContent("Claude Code");
    expect(row("Yesterday one")).toHaveTextContent("Codex");
    expect(row("Yesterday one")).toHaveTextContent("/work/web");
  });

  acceptance("chat", "a waiting conversation is marked", async () => {
    listed({ ...today, running: true, needs_you: true }, yesterday);
    renderPage();
    await screen.findByText("Today one");
    // Waiting on the owner outranks Running.
    expect(row("Today one")).toHaveTextContent("Needs you");
    expect(row("Today one")).not.toHaveTextContent("Running");
    expect(row("Yesterday one")).not.toHaveTextContent("Needs you");
    // Once the question is answered the status goes away.
    listed({ ...today, running: true, needs_you: false }, yesterday);
    window.dispatchEvent(new Event("visibilitychange"));
    await waitFor(() => expect(row("Today one")).not.toHaveTextContent("Needs you"));
  });

  acceptance(
    "chat",
    "running and waiting rows are marked from the daemon's turn state",
    async () => {
      listed(
        { ...today, running: true },
        { ...yesterday, needs_you: true },
        { ...earlier, running: false },
      );
      renderPage();
      await screen.findByText("Today one");
      expect(row("Today one")).toHaveTextContent("Running");
      expect(
        within(row("Today one")).getByRole("button", { name: "Stop Today one" }),
      ).toBeVisible();
      expect(row("Yesterday one")).toHaveTextContent("Needs you");
      expect(row("Earlier one")).not.toHaveTextContent(/Running|Needs you/);
      expect(within(row("Earlier one")).queryByRole("button", { name: /^Stop/ })).toBeNull();
    },
  );

  acceptance("chat", "the page stops a turn another surface started", async () => {
    api.interruptTurn.mockResolvedValue(undefined);
    renderPage();
    await screen.findByText("Today one");
    fireEvent.click(within(row("Today one")).getByRole("button", { name: "Stop Today one" }));
    await waitFor(() => expect(api.interruptTurn.mock.calls[0][0]).toBe("t"));
  });

  test("pressing a row does nothing yet", async () => {
    renderPage();
    await screen.findByText("Today one");
    fireEvent.click(row("Today one"));
    expect(loc()).toBe("/conversations");
    expect(api.interruptTurn).not.toHaveBeenCalled();
  });

  acceptance("chat", "the conversation list pages by cursor", async () => {
    const more = makeConversation({ id: "m", title: "Second page", updated_at: at(2, 9) });
    api.listConversations.mockImplementation(async (opts: { cursor?: string | null }) =>
      opts.cursor
        ? { conversations: [more], next_cursor: null, total: 2 }
        : { conversations: [today], next_cursor: "c1", total: null },
    );
    renderPage();
    await screen.findByText("Today one");
    expect(api.listConversations.mock.calls[0][0]).toMatchObject({ limit: 30 });
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Second page")).toBeInTheDocument();
    expect(api.listConversations.mock.calls.at(-1)?.[0]).toMatchObject({
      limit: 50,
      cursor: "c1",
    });
  });
});

describe("Conversation rows", () => {
  acceptance("chat", "a row's menu acts on one conversation", async () => {
    renderPage();
    await screen.findByText("Today one");
    const menu = await openMenu("Today one");
    expect(
      within(menu)
        .getAllByRole("menuitem")
        .map((i) => i.textContent),
    ).toEqual(["Rename", "Delete…"]);
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Rename" }));
    // Rename edits the title in place in the row, with no dialog.
    expect(await within(rowOf("t")).findByRole("textbox", { name: "Title" })).toHaveValue(
      "Today one",
    );
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  acceptance("chat", "rename a conversation in place", async () => {
    api.renameConversation.mockResolvedValue(makeConversation({ id: "t", title: "Better name" }));
    renderPage();
    await screen.findByText("Today one");
    fireEvent.click(within(await openMenu("Today one")).getByRole("menuitem", { name: "Rename" }));
    const input = await within(rowOf("t")).findByRole("textbox", { name: "Title" });
    // Esc keeps the old title.
    fireEvent.change(input, { target: { value: "Dropped" } });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.getByText("Today one")).toBeInTheDocument();
    expect(api.renameConversation).not.toHaveBeenCalled();
    // Enter saves it.
    fireEvent.click(within(await openMenu("Today one")).getByRole("menuitem", { name: "Rename" }));
    const again = await within(rowOf("t")).findByRole("textbox", { name: "Title" });
    fireEvent.change(again, { target: { value: "  Better name " } });
    listed({ ...today, title: "Better name" }, yesterday, earlier);
    fireEvent.keyDown(again, { key: "Enter" });
    await waitFor(() => expect(api.renameConversation).toHaveBeenCalledWith("t", "Better name"));
    expect(await screen.findByText("Better name")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Title" })).toBeNull();
  });

  acceptance("chat", "a refused rename leaves the index alone", async () => {
    api.renameConversation.mockRejectedValue(new ApiError("INTERNAL_ERROR", "agent said no"));
    renderPage();
    await screen.findByText("Today one");
    fireEvent.click(within(await openMenu("Today one")).getByRole("menuitem", { name: "Rename" }));
    const input = await within(rowOf("t")).findByRole("textbox", { name: "Title" });
    fireEvent.change(input, { target: { value: "Refused" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(api.renameConversation).toHaveBeenCalled());
    // The error is shown and the row keeps its title.
    expect(await screen.findByRole("status")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("textbox", { name: "Title" })).toBeNull());
    expect(screen.getByText("Today one")).toBeInTheDocument();
    expect(screen.queryByText("Refused")).toBeNull();
  });

  acceptance("chat", "delete asks first, naming the conversation", async () => {
    api.deleteConversation.mockResolvedValue(undefined);
    renderPage();
    await screen.findByText("Today one");
    fireEvent.click(within(await openMenu("Today one")).getByRole("menuitem", { name: "Delete…" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Delete “Today one”?")).toBeInTheDocument();
    expect(dialog).toHaveTextContent("deleted from the agent as well and cannot be recovered");
    expect(dialog).toHaveTextContent("Files the agent changed stay");
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(api.deleteConversation).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete conversation" }));
    await waitFor(() => expect(api.deleteConversation.mock.calls[0][0]).toBe("t"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});

describe("Conversations filter row", () => {
  test("the search comes first, then the Channel and Agent pills, with no view switch", async () => {
    renderPage();
    await screen.findByText("Today one");
    const search = screen.getByRole("textbox", { name: "Search titles and directories" });
    const channel = screen.getByRole("button", { name: /^Channel/ });
    const agent = screen.getByRole("button", { name: /^Agent/ });
    const before = (a: Node, b: Node) =>
      Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    expect(before(search, channel)).toBe(true);
    expect(before(channel, agent)).toBe(true);
    expect(screen.queryByRole("group", { name: "View" })).toBeNull();
    expect(screen.queryByText("Archived")).toBeNull();
    expect(screen.queryByRole("button", { name: "Clear filters" })).toBeNull();
  });

  test("/ focuses the search, and typing puts q in the URL and asks the server", async () => {
    renderPage();
    await screen.findByText("Today one");
    fireEvent.keyDown(document.body, { key: "/" });
    const search = screen.getByRole("textbox", { name: "Search titles and directories" });
    expect(search).toHaveFocus();
    fireEvent.change(search, { target: { value: "sentry" } });
    await waitFor(() => expect(loc()).toContain("?q=sentry"));
    await waitFor(() =>
      expect(api.listConversations.mock.calls.at(-1)?.[0]).toMatchObject({ q: "sentry" }),
    );
  });

  acceptance("chat", "the Channel pill filters by several channels", async () => {
    const first = renderPage();
    await screen.findByText("Today one");
    fireEvent.click(screen.getByRole("button", { name: /^Channel/ }));
    fireEvent.click(await screen.findByRole("option", { name: "SeaTalk · Team bot" }));
    fireEvent.click(screen.getByRole("option", { name: "Telegram · Personal" }));
    await waitFor(() => expect(loc()).toContain("?source=ch-1,ch-2"));
    await waitFor(() =>
      expect(api.listConversations.mock.calls.at(-1)?.[0]).toMatchObject({
        source: ["ch-1", "ch-2"],
      }),
    );
    expect(screen.getByRole("button", { name: "Clear filters" })).toBeInTheDocument();
    first.unmount();
    // A link carrying the earlier ?channel= is read once as that source and rewritten.
    renderPage("/conversations?channel=ch-1");
    await waitFor(() => expect(loc()).toBe("/conversations?source=ch-1"));
  });

  test("the Agent pill narrows by agent and Clear filters resets everything", async () => {
    renderPage("/conversations?q=x");
    await screen.findByText("Today one");
    fireEvent.click(screen.getAllByRole("button", { name: /^Agent/ })[0]);
    fireEvent.click(await screen.findByRole("option", { name: "Codex" }));
    await waitFor(() => expect(loc()).toContain("agent=codex"));
    await waitFor(() =>
      expect(api.listConversations.mock.calls.at(-1)?.[0]).toMatchObject({ agent: ["codex"] }),
    );
    fireEvent.keyDown(document.body, { key: "Escape" });
    fireEvent.click(await screen.findByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(loc()).toBe("/conversations"));
  });
});

describe("Conversations list states", () => {
  acceptance("chat", "an empty conversation list offers no search", async () => {
    api.listConversations.mockResolvedValue({ conversations: [], next_cursor: null, total: 0 });
    renderPage();
    expect(await screen.findByText("No conversations yet")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("button", { name: /^Channel/ })).toBeNull();
  });

  acceptance("chat", "a search that matches nothing is not an empty list", async () => {
    api.listConversations.mockImplementation(async (opts: { q?: string }) => ({
      conversations: opts.q ? [] : [today],
      next_cursor: null,
      total: opts.q ? 0 : 1,
    }));
    renderPage();
    await screen.findByText("Today one");
    const search = screen.getByRole("textbox", { name: "Search titles and directories" });
    fireEvent.change(search, { target: { value: "zzz" } });
    expect(await screen.findByText("No conversations match")).toBeInTheDocument();
    expect(screen.queryByText("No conversations yet")).toBeNull();
    expect(screen.getByRole("textbox", { name: "Search titles and directories" })).toHaveValue(
      "zzz",
    );
    expect(screen.getByRole("button", { name: "Clear filters" })).toBeInTheDocument();
  });

  acceptance("chat", "a list that fails to load says so", async () => {
    api.listConversations.mockRejectedValueOnce(new ApiError("INTERNAL_ERROR", "boom"));
    renderPage();
    expect(await screen.findByText("Couldn’t load conversations")).toBeInTheDocument();
    listed(today);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Today one")).toBeInTheDocument();
  });
});
