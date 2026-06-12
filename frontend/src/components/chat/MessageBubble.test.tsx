// components/chat/MessageBubble.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { MessageBubble } from "./MessageBubble";
import type { Message } from "@/lib/api/chat";

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
    render(
      <MessageBubble
        message={makeAssistant({ prompt_tokens: 12, completion_tokens: 34 })}
      />,
    );
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
});
