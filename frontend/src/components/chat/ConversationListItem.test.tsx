// frontend/src/components/chat/ConversationListItem.test.tsx
// Plain unit test (no acceptance marker): a channel-bound conversation shows a
// "via {channel}" chip derived from channel_binding (ADR-021).
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

describe("ConversationListItem channel badge", () => {
  test("renders a via-channel chip from channel_binding", () => {
    renderItem({
      ...base,
      channel_binding: { channel: "telegram", chat_id: "c-9" },
    });
    const chip = screen.getByText(/via telegram/i);
    expect(chip).toBeInTheDocument();
  });

  test("renders no chip for a web conversation (channel_binding null)", () => {
    renderItem({ ...base, channel_binding: null });
    expect(screen.queryByText(/via /i)).not.toBeInTheDocument();
  });

  test("renders no chip when channel_binding is absent (legacy rows)", () => {
    renderItem(base);
    expect(screen.queryByText(/via /i)).not.toBeInTheDocument();
  });
});
