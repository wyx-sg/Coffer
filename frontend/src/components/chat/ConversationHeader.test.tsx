import { useState } from "react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { TooltipProvider } from "@/components/ui/tooltip";
import { TitleBarSlotContext } from "@/components/shell/titleBarSlot";
import type { ChannelMirror } from "@/lib/api/chat";
import { makeBinding, makeConversation } from "@/test/conversationFixtures";
import { ConversationHeader } from "./ConversationHeader";

const mirror = vi.hoisted(() => ({ value: null as ChannelMirror | null }));
vi.mock("@/lib/hooks/useConversations", () => ({
  useChannelMirror: () => ({ mirror: mirror.value, notDeliveredTo: () => undefined }),
}));

const handlers = { onRename: vi.fn(), onArchive: vi.fn(), onDelete: vi.fn() };

beforeEach(() => {
  vi.clearAllMocks();
  mirror.value = null;
});

/** The desktop title bar: a slot element the strip leaves, in a context. */
function InDesktopBar({ children }: { children: React.ReactNode }) {
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  return (
    <TooltipProvider>
      <div data-testid="slot" ref={setSlot} />
      <TitleBarSlotContext.Provider value={slot}>
        {slot ? children : null}
      </TitleBarSlotContext.Provider>
    </TooltipProvider>
  );
}

describe("ConversationHeader", () => {
  test("in the desktop shell the title row is portalled into the title bar's slot", () => {
    render(
      <InDesktopBar>
        <ConversationHeader conversation={makeConversation()} archived={false} {...handlers} />
      </InDesktopBar>,
    );
    const slot = screen.getByTestId("slot");
    expect(within(slot).getByRole("heading", { name: "Test Conv" })).toBeInTheDocument();
    expect(within(slot).getByRole("button", { name: "More actions" })).toBeInTheDocument();
    expect(screen.queryByTestId("content-title-bar")).not.toBeInTheDocument();
  });

  test("in a browser the same row is a 44px bar at the top of the content", () => {
    render(
      <TooltipProvider>
        <ConversationHeader conversation={makeConversation()} archived={false} {...handlers} />
      </TooltipProvider>,
    );
    const bar = screen.getByTestId("content-title-bar");
    expect(bar).toHaveClass("h-11");
    expect(within(bar).getByRole("heading", { name: "Test Conv" })).toBeInTheDocument();
    expect(within(bar).getByRole("button", { name: "More actions" })).toBeInTheDocument();
  });

  test("a channel conversation shows its source beside the title; a Coffer one shows none", () => {
    const { rerender } = render(
      <TooltipProvider>
        <ConversationHeader conversation={makeConversation()} archived={false} {...handlers} />
      </TooltipProvider>,
    );
    expect(screen.queryByTestId("conversation-source")).not.toBeInTheDocument();
    rerender(
      <TooltipProvider>
        <ConversationHeader
          conversation={makeConversation({
            channel_binding: makeBinding({
              place: {
                chat_kind: "group",
                thread: true,
                parallel_mark: null,
                chat_name: "coffer-dev",
              },
            }),
          })}
          archived={false}
          {...handlers}
        />
      </TooltipProvider>,
    );
    expect(screen.getByTestId("conversation-source")).toHaveTextContent(
      "SeaTalk · coffer-dev › thread",
    );
    expect(screen.queryByText("Replies stay in Coffer")).not.toBeInTheDocument();
  });

  test("when replies cannot go back to the chat it says so, with the reason one tap away", () => {
    mirror.value = {
      deliverable: false,
      reason: "group_main",
      platform: "seatalk",
      target: "SeaTalk · coffer-dev",
    } as ChannelMirror;
    render(
      <TooltipProvider>
        <ConversationHeader
          conversation={makeConversation({ channel_binding: makeBinding() })}
          archived={false}
          {...handlers}
        />
      </TooltipProvider>,
    );
    expect(screen.getByText("Replies stay in Coffer")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /more info/i })).toBeInTheDocument();
  });

  test("the menu offers Rename, Archive and Delete…; an archived one has no Archive", () => {
    const { unmount } = render(
      <TooltipProvider>
        <ConversationHeader conversation={makeConversation()} archived={false} {...handlers} />
      </TooltipProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "More actions" }));
    expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual([
      "Rename",
      "Archive",
      "Delete…",
    ]);
    unmount();
    render(
      <TooltipProvider>
        <ConversationHeader conversation={makeConversation()} archived {...handlers} />
      </TooltipProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "More actions" }));
    expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual([
      "Rename",
      "Delete…",
    ]);
  });

  test("Rename turns the title into an input; Enter saves, Esc cancels", () => {
    render(
      <TooltipProvider>
        <ConversationHeader conversation={makeConversation()} archived={false} {...handlers} />
      </TooltipProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "More actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Rename" }));
    const input = screen.getByRole("textbox", { name: "Conversation title" });
    expect(screen.getByText("Enter to save · Esc to cancel")).toBeInTheDocument();
    fireEvent.change(input, { target: { value: "  Renamed  " } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(handlers.onRename).toHaveBeenCalledWith("Renamed");

    fireEvent.click(screen.getByRole("button", { name: "Test Conv" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Conversation title" }), {
      target: { value: "Other" },
    });
    fireEvent.keyDown(screen.getByRole("textbox", { name: "Conversation title" }), {
      key: "Escape",
    });
    expect(handlers.onRename).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("textbox", { name: "Conversation title" })).not.toBeInTheDocument();
  });

  test("startRenaming opens with the title being edited", () => {
    render(
      <TooltipProvider>
        <ConversationHeader
          conversation={makeConversation()}
          archived={false}
          startRenaming
          {...handlers}
        />
      </TooltipProvider>,
    );
    expect(screen.getByRole("textbox", { name: "Conversation title" })).toHaveValue("Test Conv");
  });
});
