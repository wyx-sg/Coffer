// components/chat/SourceBadge.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import i18n from "@/i18n";

import { TooltipProvider } from "@/components/ui/tooltip";
import { makeBinding, makeConversation } from "@/test/conversationFixtures";
import { sourceText } from "@/lib/conversations/sourceText";
import { SourceBadge } from "./SourceBadge";

const t = i18n.getFixedT("en");
const place = (p: Partial<NonNullable<ReturnType<typeof makeBinding>["place"]>>) => ({
  chat_kind: "direct" as const,
  thread: false,
  parallel_mark: null,
  chat_name: null,
  ...p,
});
const text = (binding: Parameters<typeof makeBinding>[0] | null) =>
  sourceText(
    t,
    makeConversation({ channel_binding: binding === null ? null : makeBinding(binding) }),
  );

describe("sourceText", () => {
  test("Coffer for a conversation opened in Coffer", () => {
    expect(text(null)).toBe("Coffer");
  });

  test("a direct chat, its parallel thread and a thread in it", () => {
    expect(text({ place: place({}) })).toBe("SeaTalk · DM");
    expect(text({ place: place({ parallel_mark: "🧵#2 deploy check", thread: true }) })).toBe(
      "SeaTalk · DM · 🧵#2",
    );
    expect(text({ place: place({ thread: true }) })).toBe("SeaTalk · DM › thread");
  });

  test("a group, its thread — a topic on Telegram — and a group without a known name", () => {
    expect(text({ place: place({ chat_kind: "group", chat_name: "coffer-dev" }) })).toBe(
      "SeaTalk · coffer-dev",
    );
    expect(
      text({ place: place({ chat_kind: "group", chat_name: "coffer-dev", thread: true }) }),
    ).toBe("SeaTalk · coffer-dev › thread");
    expect(text({ platform: "telegram", place: place({ chat_kind: "group", thread: true }) })).toBe(
      "Telegram · Group › topic",
    );
  });

  test("the channel's name when the chat is not known, its uid once the channel is gone", () => {
    expect(text({ platform: "telegram", channel: "Personal", place: null })).toBe(
      "Telegram · Personal",
    );
    expect(text({ platform: null, channel: null, channel_uid: "ch-9", place: null })).toBe(
      "Channel · ch-9",
    );
  });
});

describe("SourceBadge", () => {
  test("marks the platform beside the text", () => {
    render(
      <TooltipProvider>
        <SourceBadge conversation={makeConversation({ channel_binding: makeBinding() })} />
      </TooltipProvider>,
    );
    expect(document.querySelector('[data-platform="seatalk"] img')).not.toBeNull();
    expect(screen.getByText("SeaTalk · DM")).toBeInTheDocument();
  });
});
