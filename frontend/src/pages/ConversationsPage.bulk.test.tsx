// pages/ConversationsPage.bulk.test.tsx — selecting conversations on the list and
// archiving, unarchiving or deleting them together (spec chat "Create, rename,
// archive, unarchive and delete conversations").
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConversationsPage } from "./ConversationsPage";
import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { makeConversation } from "@/test/conversationFixtures";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/api/chat", () => ({
  chatApi: {
    listConversations: vi.fn(),
    batchConversations: vi.fn(),
    getConversation: vi.fn(),
    listMessages: vi.fn(),
  },
}));
vi.mock("@/lib/api/agentProviders", () => ({ agentProvidersApi: { list: vi.fn() } }));
vi.mock("@/lib/hooks/useChannels", () => ({ useChannels: () => ({ data: [] }) }));

const { chatApi } = await import("@/lib/api/chat");
const api = chatApi as unknown as Record<string, ReturnType<typeof vi.fn>>;
const { agentProvidersApi } = await import("@/lib/api/agentProviders");

const now = new Date().toISOString();
const rows = ["a", "b", "c", "d"].map((id, i) =>
  // Newest first, so the table's order is a, b, c, d.
  makeConversation({
    id,
    title: `Conv ${id}`,
    updated_at: new Date(Date.now() - i * 1000).toISOString() || now,
  }),
);

function renderPage(path = "/conversations") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  vi.mocked(agentProvidersApi.list).mockResolvedValue({
    agents: [{ agent_key: "claude_code", display_name: "Claude Code", available: true }],
  });
  const page = <ConversationsPage />;
  return render(
    <MemoryRouter initialEntries={[path]}>
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

const rowBox = (title: string) => screen.getByRole("checkbox", { name: `Select ${title}` });

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  api.listConversations.mockResolvedValue({ conversations: rows });
  api.batchConversations.mockImplementation(async (_action: string, ids: string[]) => ({
    results: ids.map((id) => ({ id, outcome: "done", reason: null })),
  }));
});

describe("Conversations selection", () => {
  test("ticking a row shows the selection bar; the row itself does not open", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select Conv a" }));
    expect(screen.getByText("1 of 4 selected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Archive" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete…" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear" })).toBeInTheDocument();
    // The selection bar replaces the filter row.
    expect(screen.queryByRole("textbox", { name: "Search titles and messages" })).toBeNull();
    // Still on the list: the checkbox click did not navigate.
    expect(screen.getByRole("link", { name: "Conv b" })).toBeInTheDocument();
  });

  test("shift-click ticks the range between two rows", async () => {
    renderPage();
    await screen.findByRole("link", { name: "Conv a" });
    fireEvent.click(rowBox("Conv a"));
    fireEvent.click(rowBox("Conv c"), { shiftKey: true });
    expect(screen.getByText("3 of 4 selected")).toBeInTheDocument();
    expect(rowBox("Conv d")).not.toBeChecked();
  });

  test("Select all ticks every row; ticked again, it clears", async () => {
    renderPage();
    await screen.findByText("Conv a");
    const all = screen.getByRole("checkbox", { name: "Select all" });
    fireEvent.click(all);
    expect(screen.getByText("4 of 4 selected")).toBeInTheDocument();
    expect(all).toBeChecked();
    fireEvent.click(all);
    expect(screen.queryByText(/selected/)).not.toBeInTheDocument();
  });

  acceptance("chat", "Select all ticks every conversation the view holds", async () => {
    const more = makeConversation({
      id: "e",
      title: "Conv e",
      updated_at: new Date(Date.now() - 10_000).toISOString(),
    });
    api.listConversations.mockImplementation(async ({ cursor }: { cursor?: string | null }) =>
      cursor
        ? { conversations: [more], next_cursor: null, total: 5 }
        : { conversations: rows, next_cursor: "c1", total: 5 },
    );
    renderPage();
    await screen.findByText("Conv a");
    fireEvent.click(screen.getByRole("checkbox", { name: "Select all" }));
    expect(await screen.findByText("5 of 5 selected")).toBeInTheDocument();
    expect(rowBox("Conv e")).toBeChecked();
  });

  test("one row ticked leaves Select all half-ticked", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select Conv b" }));
    const all = screen.getByRole("checkbox", { name: "Select all" }) as HTMLInputElement;
    expect(all.indeterminate).toBe(true);
    fireEvent.click(all);
    expect(screen.getByText("4 of 4 selected")).toBeInTheDocument();
  });

  test("changing a filter drops the selection", async () => {
    renderPage();
    await screen.findByRole("link", { name: "Conv a" });
    fireEvent.click(rowBox("Conv a"));
    expect(screen.getByText("1 of 4 selected")).toBeInTheDocument();
    // Clear ends the selection and brings the filter row back.
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(
      await screen.findByRole("textbox", { name: "Search titles and messages" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/selected/)).not.toBeInTheDocument();
    // A different view starts with nothing ticked.
    fireEvent.click(rowBox("Conv a"));
    api.listConversations.mockResolvedValue({ conversations: rows.slice(1) });
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    fireEvent.click(await screen.findByRole("button", { name: "Archived" }));
    await waitFor(() => expect(screen.queryByText(/selected/)).not.toBeInTheDocument());
  });

  test("Archive runs straight away, toasts with Undo and refreshes the list", async () => {
    renderPage();
    await screen.findByRole("link", { name: "Conv a" });
    fireEvent.click(rowBox("Conv a"));
    fireEvent.click(rowBox("Conv b"));
    api.listConversations.mockResolvedValue({ conversations: rows.slice(2) });
    fireEvent.click(screen.getByRole("button", { name: "Archive" }));
    await waitFor(() => expect(api.batchConversations).toHaveBeenCalledWith("archive", ["a", "b"]));
    expect(await screen.findByText("Archived 2 conversations")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("link", { name: "Conv a" })).toBeNull());
    expect(screen.queryByText(/selected/)).not.toBeInTheDocument();
  });

  test("Delete confirms first, naming the count and titles, then the rows are gone", async () => {
    renderPage();
    await screen.findByRole("link", { name: "Conv a" });
    for (const id of ["a", "b", "c", "d"]) fireEvent.click(rowBox(`Conv ${id}`));
    fireEvent.click(screen.getByRole("button", { name: "Delete…" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Delete 4 conversations?")).toBeInTheDocument();
    expect(
      within(dialog).getByText(
        "These conversations and their messages are removed from Coffer; files the agents changed stay.",
      ),
    ).toBeInTheDocument();
    for (const id of ["a", "b", "c", "d"]) {
      expect(within(dialog).getByText(`Conv ${id}`)).toBeInTheDocument();
    }
    expect(api.batchConversations).not.toHaveBeenCalled();
    api.listConversations.mockResolvedValue({ conversations: [] });
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete 4 conversations" }));
    await waitFor(() =>
      expect(api.batchConversations).toHaveBeenCalledWith("delete", ["a", "b", "c", "d"]),
    );
    expect(await screen.findByText("Deleted 4 conversations")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("link", { name: "Conv a" })).toBeNull());
  });

  acceptance("chat", "ticking rows replaces the filter row with a selection bar", async () => {
    const many = Array.from({ length: 7 }, (_, i) =>
      makeConversation({
        id: `m${i}`,
        title: `Many ${i}`,
        updated_at: new Date(Date.now() - i * 1000).toISOString(),
      }),
    );
    api.listConversations.mockResolvedValue({ conversations: many, total: 7 });
    renderPage();
    await screen.findByRole("link", { name: "Many 0" });
    for (const c of many) fireEvent.click(rowBox(c.title));
    expect(screen.getByText("7 of 7 selected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete…" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getAllByRole("listitem")).toHaveLength(5);
    expect(within(dialog).getByText("Showing 5 of 7")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Show all" }));
    expect(within(dialog).getAllByRole("listitem")).toHaveLength(7);
    expect(within(dialog).queryByText(/Showing 5/)).toBeNull();
  });

  test("a running conversation is reported as skipped, with the rest done", async () => {
    api.batchConversations.mockResolvedValue({
      results: [
        { id: "a", outcome: "skipped", reason: "running" },
        { id: "b", outcome: "done", reason: null },
      ],
    });
    renderPage();
    await screen.findByRole("link", { name: "Conv a" });
    fireEvent.click(rowBox("Conv a"));
    fireEvent.click(rowBox("Conv b"));
    fireEvent.click(screen.getByRole("button", { name: "Delete…" }));
    fireEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", {
        name: "Delete 2 conversations",
      }),
    );
    expect(await screen.findByText("1 done, 1 skipped")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /details/i }));
    expect(await screen.findByText(/still running and was left as it is/)).toBeInTheDocument();
  });

  test("a failed call says so and leaves the selection in place", async () => {
    api.batchConversations.mockRejectedValue(new Error("boom"));
    renderPage();
    await screen.findByRole("link", { name: "Conv a" });
    fireEvent.click(rowBox("Conv a"));
    fireEvent.click(screen.getByRole("button", { name: "Archive" }));
    await waitFor(() => expect(api.batchConversations).toHaveBeenCalled());
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  test("the archived view offers Unarchive and Delete", async () => {
    api.listConversations.mockResolvedValue({
      conversations: rows.map((c) => ({ ...c, archived_at: now })),
    });
    renderPage("/conversations?archived=1");
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select Conv a" }));
    expect(screen.queryByRole("button", { name: "Archive" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Unarchive" }));
    await waitFor(() => expect(api.batchConversations).toHaveBeenCalledWith("unarchive", ["a"]));
    expect(await screen.findByText("Unarchived 1 conversation")).toBeInTheDocument();
  });
});
