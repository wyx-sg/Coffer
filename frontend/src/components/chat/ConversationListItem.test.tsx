// frontend/src/components/chat/ConversationListItem.test.tsx
// Plain unit test (no acceptance marker): a channel-originated conversation
// shows a "via {channel}" chip tooltipped with the peer's display name (ADR-021).
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { ConversationListItem } from "./ConversationListItem";
import type { Conversation } from "@/lib/api/chat";

const base: Conversation = {
  id: "1",
  agent_key: "builtin",
  title: "Deploy plan",
  model_id: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function renderItem(conversation: Conversation) {
  render(
    <ConversationListItem
      conversation={conversation}
      isActive={false}
      onSelect={vi.fn()}
      onRename={vi.fn()}
      onDelete={vi.fn()}
      onArchive={vi.fn()}
    />,
  );
}

describe("ConversationListItem origin badge", () => {
  test("renders a via-channel chip with the peer display name as title", () => {
    renderItem({
      ...base,
      origin: "channel",
      peer: { chat_id: "c-9", display_name: "Alice", channel: "telegram" },
    });
    const chip = screen.getByText(/via telegram/i);
    expect(chip).toBeInTheDocument();
    expect(chip).toHaveAttribute("title", "Alice");
  });

  test("renders no chip for a web-origin conversation", () => {
    renderItem({ ...base, origin: "web", peer: null });
    expect(screen.queryByText(/via /i)).not.toBeInTheDocument();
  });

  test("renders no chip when origin is absent (legacy rows)", () => {
    renderItem(base);
    expect(screen.queryByText(/via /i)).not.toBeInTheDocument();
  });
});
