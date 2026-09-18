// frontend/src/components/chat/ConversationListItem.test.tsx
// Plain unit test (no acceptance marker): a channel-bound conversation shows a
// "via {channel}" chip derived from channel_binding (ADR
// chat-single-owner-live-mirror).
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ConversationListItem } from "./ConversationListItem";
import type { Conversation } from "@/lib/api/chat";

const base: Conversation = {
  id: "1",
  agent_key: "builtin",
  title: "Deploy plan",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function renderItem(
  conversation: Conversation,
  handlers: Partial<{ onSelect: () => void; onRename: (t: string) => void }> = {},
) {
  render(
    <ul>
      <ConversationListItem
        conversation={conversation}
        isActive={false}
        onSelect={handlers.onSelect ?? vi.fn()}
        onRename={handlers.onRename ?? vi.fn()}
        onDelete={vi.fn()}
        onArchive={vi.fn()}
      />
    </ul>,
  );
}

describe("ConversationListItem structure", () => {
  test("is a list item whose title is a button; the actions are separate buttons", () => {
    const onSelect = vi.fn();
    renderItem(base, { onSelect });
    const item = screen.getByRole("listitem");
    expect(item.getAttribute("role")).toBeNull();
    expect(item.getAttribute("aria-selected")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Deploy plan" }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    for (const name of [/rename/i, /archive/i, /delete/i]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
  });

  test("renaming offers labelled Save and Cancel controls", () => {
    const onRename = vi.fn();
    renderItem(base, { onRename });
    fireEvent.click(screen.getByRole("button", { name: /rename/i }));
    const input = screen.getByRole("textbox", { name: /rename conversation/i });
    fireEvent.change(input, { target: { value: "New title" } });
    expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(onRename).toHaveBeenCalledWith("New title");
  });
});

describe("ConversationListItem channel badge", () => {
  test("renders a via-channel chip naming the channel, not its uid", () => {
    renderItem({
      ...base,
      // The binding stores the channel's uid; the name beside it is resolved
      // when the conversation is read. The chip is for a person, so it is the
      // name that has to appear — and the uid that must not.
      channel_binding: { channel_uid: "ch-4b12", channel: "telegram", chat_id: "c-9" },
    });
    expect(screen.getByText(/via telegram/i)).toBeInTheDocument();
    expect(screen.queryByText(/ch-4b12/)).toBeNull();
  });

  test("falls back to the uid once the channel is gone", () => {
    // A deleted channel leaves the binding standing with no name to resolve.
    // The conversation really did arrive over a channel, so the chip says the
    // only thing left that is true rather than going blank.
    renderItem({
      ...base,
      channel_binding: { channel_uid: "ch-4b12", channel: null, chat_id: "c-9" },
    });
    expect(screen.getByText(/via ch-4b12/i)).toBeInTheDocument();
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
