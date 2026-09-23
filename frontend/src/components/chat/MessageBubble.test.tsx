// components/chat/MessageBubble.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { MessageBubble } from "./MessageBubble";
import { acceptance } from "@/test/acceptance";
import type { ContentBlock, Message } from "@/lib/api/chat";

const makeAssistant = (overrides: Partial<Message>): Message => ({
  id: "m-1",
  conversation_id: "c-1",
  seq: 1,
  role: "assistant",
  content: [{ type: "text", text: "Hello" }],
  status: "complete",
  created_at: "2026-01-01T00:00:00Z",
  ...overrides,
});

const makeUser = (overrides: Partial<Message>): Message => ({
  id: "u-1",
  conversation_id: "c-1",
  seq: 0,
  role: "user",
  content: [{ type: "text", text: "hi" }],
  status: "complete",
  created_at: "2026-01-01T00:00:00Z",
  ...overrides,
});

describe("MessageBubble", () => {
  test("shows a notice for a failed assistant message", () => {
    render(<MessageBubble message={makeAssistant({ status: "failed" })} />);
    expect(screen.getByText(/did not complete/i)).toBeInTheDocument();
  });

  test("does not show the failed notice for a complete message", () => {
    render(<MessageBubble message={makeAssistant({ status: "complete" })} />);
    expect(screen.queryByText(/did not complete/i)).not.toBeInTheDocument();
  });

  test("renders per-message token usage when present", () => {
    render(<MessageBubble message={makeAssistant({ prompt_tokens: 12, completion_tokens: 34 })} />);
    expect(screen.getByText(/12 in/)).toBeInTheDocument();
    expect(screen.getByText(/34 out/)).toBeInTheDocument();
  });

  test("omits token usage when the message has none", () => {
    render(<MessageBubble message={makeAssistant({})} />);
    expect(screen.queryByText(/ in ·/)).not.toBeInTheDocument();
  });

  test("renders a thinking indicator for a persisted streaming placeholder", () => {
    // The backend writes an empty assistant row with status='streaming' at
    // turn start; on a reload mid-turn it must render as in-progress, not as
    // a blank bubble.
    render(<MessageBubble message={makeAssistant({ status: "streaming", content: [] })} />);
    expect(screen.getByText(/thinking/i)).toBeInTheDocument();
  });

  test("renders an attachment chip for a user message with an attachment block", () => {
    // Spec channels "Persist inbound attachments as references": a channel-media attachment
    // reference shows as a compact chip on the user bubble (filename · mime), never a path.
    render(
      <MessageBubble
        message={makeUser({
          content: [
            { type: "text", text: "look" },
            { type: "attachment", filename: "photo.jpg", mime: "image/jpeg" },
          ],
        })}
      />,
    );
    expect(screen.getByText("photo.jpg")).toBeInTheDocument();
    expect(screen.getByText(/image\/jpeg/)).toBeInTheDocument();
  });

  test("an attachment without a filename gets a translated label", () => {
    render(
      <MessageBubble
        message={makeUser({ content: [{ type: "attachment", filename: null, mime: null }] })}
      />,
    );
    expect(screen.getByText("Attachment")).toBeInTheDocument();
  });

  test("bubbles size to their content, capped by the column and not only by a number", () => {
    const { container } = render(<MessageBubble message={makeUser({})} />);
    const bubble = container.querySelector(".rounded-xl") as HTMLElement;
    expect(bubble.className).toContain("w-fit");
    // 48rem OR the column, whichever is smaller. A flat cap was fine while the
    // thread owned the window; beside a context panel the column is narrower
    // than 48rem, and an oversized child of an `items-end` column overflows
    // the START edge — so a long message slid left, under the sidebar, with
    // its first characters cut off.
    expect(bubble.className).toContain("max-w-[min(48rem,100%)]");
  });

  describe("an assistant turn's text and tool calls render in the order the turn emitted them", () => {
    const orderedBlocks: ContentBlock[] = [
      { type: "text", text: "BEFORE" },
      { type: "tool_use", tool_use_id: "tu-1", tool_name: "read_file", tool_input: {} },
      { type: "tool_result", tool_use_id: "tu-1", tool_name: "read_file", output: {} },
      { type: "text", text: "AFTER" },
    ];

    function renderedOrder(container: HTMLElement): string[] {
      const before = screen.getByText("BEFORE");
      const card = screen.getByRole("button", { name: /read_file/ });
      const after = screen.getByText("AFTER");
      const nodes = [before, card, after];
      expect(container.textContent).not.toContain("BEFOREAFTER");
      return [...nodes]
        .sort((a, b) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1))
        .map((n) => (n === before ? "BEFORE" : n === after ? "AFTER" : "card"));
    }

    acceptance("chat", "a tool call renders as a card between the text around it", () => {
      const { container } = render(
        <MessageBubble message={makeAssistant({ content: orderedBlocks })} />,
      );
      expect(renderedOrder(container)).toEqual(["BEFORE", "card", "AFTER"]);
      // The result still pairs with its call: one card, marked done.
      expect(screen.getAllByRole("button")).toHaveLength(1);
      expect(screen.getByText(/done/i)).toBeInTheDocument();
    });

    test("the live bubble of a turn still streaming", () => {
      const { container } = render(
        <MessageBubble live={{ blocks: orderedBlocks, streaming: true }} />,
      );
      expect(renderedOrder(container)).toEqual(["BEFORE", "card", "AFTER"]);
      expect(screen.getAllByRole("button")).toHaveLength(1);
    });
  });
});
