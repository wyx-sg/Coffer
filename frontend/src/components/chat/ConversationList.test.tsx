import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { ConversationList } from "./ConversationList";
import type { Conversation } from "@/lib/api/chat";

const conv = (id: string, title: string): Conversation => ({
  id,
  agent_key: "builtin",
  title,
  model_id: null,
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
