import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import { ConversationList } from "./ConversationList";
import type { Conversation } from "@/lib/api/chat";

const conv = (id: string, title: string): Conversation => ({
  id,
  agent_key: "builtin",
  title,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
});

function renderList(
  conversations: Conversation[],
  overrides: Partial<React.ComponentProps<typeof ConversationList>> = {},
) {
  const handlers = {
    onToggleView: vi.fn(),
    onArchive: vi.fn(),
    onRestore: vi.fn(),
  };
  render(
    <ConversationList
      conversations={conversations}
      activeId={null}
      loading={false}
      view="active"
      onToggleView={handlers.onToggleView}
      onSelect={vi.fn()}
      onCreate={vi.fn()}
      onRename={vi.fn()}
      onDelete={vi.fn()}
      onArchive={handlers.onArchive}
      onRestore={handlers.onRestore}
      {...overrides}
    />,
  );
  return handlers;
}

describe("ConversationList search", () => {
  test("filters the list by title as the user types", () => {
    renderList([conv("1", "OAuth notes"), conv("2", "Dinner recipes")]);
    expect(screen.getByText("OAuth notes")).toBeInTheDocument();
    expect(screen.getByText("Dinner recipes")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("textbox", { name: /search conversations/i }), {
      target: { value: "oauth" },
    });

    expect(screen.getByText("OAuth notes")).toBeInTheDocument();
    expect(screen.queryByText("Dinner recipes")).not.toBeInTheDocument();
  });

  test("shows a no-matches message when nothing matches", () => {
    renderList([conv("1", "OAuth notes")]);
    fireEvent.change(screen.getByRole("textbox", { name: /search conversations/i }), {
      target: { value: "zzz" },
    });
    expect(screen.getByText(/no matching conversations/i)).toBeInTheDocument();
  });

  test("hides the search box when there are no conversations at all", () => {
    renderList([]);
    expect(screen.queryByRole("textbox", { name: /search conversations/i })).not.toBeInTheDocument();
  });
});

describe("ConversationList archive", () => {
  test("active view exposes an archive action per row", () => {
    const { onArchive } = renderList([conv("1", "Keep me")]);
    fireEvent.click(screen.getByRole("button", { name: /^archive$/i }));
    expect(onArchive).toHaveBeenCalledWith("1");
  });

  test("the archived filter tab switches to archived", () => {
    const { onToggleView } = renderList([conv("1", "A")]);
    fireEvent.click(screen.getByRole("tab", { name: /archived/i }));
    expect(onToggleView).toHaveBeenCalledOnce();
  });

  test("clicking the already-selected filter tab is a no-op", () => {
    const { onToggleView } = renderList([conv("1", "A")]);
    fireEvent.click(screen.getByRole("tab", { name: /active/i }));
    expect(onToggleView).not.toHaveBeenCalled();
  });

  test("archived view exposes a restore action and selects the archived tab", () => {
    const { onRestore } = renderList([conv("1", "Old chat")], { view: "archived" });
    fireEvent.click(screen.getByRole("button", { name: /restore/i }));
    expect(onRestore).toHaveBeenCalledWith("1");
    expect(screen.getByRole("tab", { name: /archived/i })).toHaveAttribute("aria-selected", "true");
  });
});

describe("ConversationListItem keyboard reachability", () => {
  // The row action buttons are hover-only (opacity-0 group-hover:opacity-100),
  // which makes them invisible — and thus effectively unreachable — for keyboard
  // users. They must also reveal on keyboard focus, so each carries
  // focus-visible:opacity-100 (the button itself) and group-focus-within:opacity-100
  // (any sibling focused within the row).
  test("hover-only action buttons reveal on focus, not just hover", () => {
    renderList([conv("1", "Keep me")]);
    for (const name of [/^rename$/i, /^archive$/i, /^delete$/i]) {
      const btn = screen.getByRole("button", { name });
      expect(btn.className).toContain("focus-visible:opacity-100");
      expect(btn.className).toContain("group-focus-within:opacity-100");
    }
  });
});

acceptance("chat", "a channel's conversation is listed beside the web's with a badge", () => {
  renderList([
    conv("web", "Started on the web"),
    {
      ...conv("im", "Started on the phone"),
      channel_binding: { channel_uid: "ch-1", channel: "telegram", chat_id: "c-9" },
    },
  ]);

  const items = screen.getAllByRole("listitem");
  expect(items).toHaveLength(2);
  const web = items.find((li) => li.textContent?.includes("Started on the web"))!;
  const im = items.find((li) => li.textContent?.includes("Started on the phone"))!;
  expect(im).toHaveTextContent(/via telegram/i);
  expect(web).not.toHaveTextContent(/via /i);
});

// spec chat "Search the conversation list by title".
acceptance("chat", "search narrows the conversation list by title", () => {
  renderList([conv("1", "Alpha rollout"), conv("2", "beta notes"), conv("3", "Gamma")]);

  fireEvent.change(screen.getByRole("textbox", { name: /search conversations/i }), {
    target: { value: "  ALP " },
  });

  // Case-insensitive substring of the title, with the query trimmed.
  const items = screen.getAllByRole("listitem");
  expect(items).toHaveLength(1);
  expect(items[0]).toHaveTextContent("Alpha rollout");

  // Clearing the query brings every conversation back.
  fireEvent.change(screen.getByRole("textbox", { name: /search conversations/i }), {
    target: { value: "" },
  });
  expect(screen.getAllByRole("listitem")).toHaveLength(3);
});

acceptance("chat", "a search that matches nothing is not an empty list", () => {
  renderList([conv("1", "Alpha rollout")]);
  fireEvent.change(screen.getByRole("textbox", { name: /search conversations/i }), {
    target: { value: "zzz" },
  });
  expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  expect(screen.getByText("No matching conversations")).toBeInTheDocument();
  expect(screen.queryByText(/no conversations yet/i)).not.toBeInTheDocument();
  // The search box stays, so the query can be changed.
  expect(screen.getByRole("textbox", { name: /search conversations/i })).toHaveValue("zzz");
});

acceptance("chat", "an empty conversation list offers no search", () => {
  renderList([]);
  expect(screen.getByText(/no conversations yet/i)).toBeInTheDocument();
  expect(screen.queryByText("No matching conversations")).not.toBeInTheDocument();
  expect(screen.queryByRole("textbox", { name: /search conversations/i })).not.toBeInTheDocument();
});
