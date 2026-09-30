// components/chat/ConversationList.test.tsx
import { describe, expect, test } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { Conversation } from "@/lib/api/chat";
import { acceptance } from "@/test/acceptance";
import { makeBinding, makeConversation } from "@/test/conversationFixtures";
import { ConversationList } from "./ConversationList";

const conv = (id: string, title: string, overrides: Partial<Conversation> = {}) =>
  makeConversation({ id, title, ...overrides });

function renderList(conversations: Conversation[], activeId: string | null = null) {
  render(
    <MemoryRouter>
      <TooltipProvider>
        <ConversationList
          conversations={conversations}
          activeId={activeId}
          loading={false}
          listPath="/conversations?source=seatalk"
          hrefFor={(id) => `/conversations/${id}?source=seatalk`}
          agentNames={new Map([["claude_code", "Claude Code"]])}
          onCreate={() => {}}
        />
      </TooltipProvider>
    </MemoryRouter>,
  );
}

describe("ConversationList", () => {
  test("each row links to its conversation, keeping the list's filters", () => {
    renderList([conv("1", "OAuth notes")], "1");
    const link = screen.getByRole("link", { name: /OAuth notes/ });
    expect(link).toHaveAttribute("href", "/conversations/1?source=seatalk");
    expect(link).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /conversations/i })).toHaveAttribute(
      "href",
      "/conversations?source=seatalk",
    );
  });

  test("a running conversation says so", () => {
    renderList([conv("1", "Busy", { running: true })]);
    expect(screen.getByText("Running")).toBeInTheDocument();
  });
});

acceptance("chat", "a channel's conversation is listed beside the web's with a badge", () => {
  renderList([
    conv("web", "Started on the web"),
    conv("im", "Started on the phone", {
      channel_binding: makeBinding({
        platform: "telegram",
        channel: "Personal",
        place: null,
      }),
    }),
  ]);

  const items = screen.getAllByRole("listitem");
  expect(items).toHaveLength(2);
  const web = items.find((li) => li.textContent?.includes("Started on the web"))!;
  const im = items.find((li) => li.textContent?.includes("Started on the phone"))!;
  expect(im).toHaveTextContent("Telegram · Personal");
  expect(web).toHaveTextContent("Coffer");
  expect(web).not.toHaveTextContent("Telegram");
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
