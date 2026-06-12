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

function renderList(conversations: Conversation[]) {
  return render(
    <ConversationList
      conversations={conversations}
      activeId={null}
      loading={false}
      onSelect={vi.fn()}
      onCreate={vi.fn()}
      onRename={vi.fn()}
      onDelete={vi.fn()}
    />,
  );
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
