// components/chat/MessageBubble.test.tsx
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render as rtlRender, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { MessageBubble } from "./MessageBubble";
import { acceptance } from "@/test/acceptance";
import type { ContentBlock, Message } from "@/lib/api/chat";
import { contentBlock } from "@/lib/chat/contentBlock";

// A reply's recorded files and the working folder are read through the API; none here.
vi.mock("@/lib/api/chat", () => ({
  chatApi: {
    listReplyFiles: vi.fn().mockResolvedValue([]),
    getAgentConfig: vi.fn().mockResolvedValue({ model: null, effort: null, cwd: null }),
  },
}));

const render = (ui: ReactElement) =>
  rtlRender(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);

const makeAssistant = (overrides: Partial<Message>): Message => ({
  id: "m-1",
  conversation_id: "c-1",
  seq: 1,
  role: "assistant",
  content: [contentBlock({ type: "text", text: "Hello" })],
  status: "complete",
  prompt_tokens: null,
  completion_tokens: null,
  model_id: null,
  finished_at: null,
  created_at: "2026-01-01T00:00:00Z",
  ...overrides,
});

const makeUser = (overrides: Partial<Message>): Message => ({
  id: "u-1",
  conversation_id: "c-1",
  seq: 0,
  role: "user",
  content: [contentBlock({ type: "text", text: "hi" })],
  status: "complete",
  prompt_tokens: null,
  completion_tokens: null,
  model_id: null,
  finished_at: null,
  created_at: "2026-01-01T00:00:00Z",
  ...overrides,
});

describe("MessageBubble", () => {
  describe("the reply header names its state", () => {
    const header = (message: Message) => {
      const { container } = render(
        <MessageBubble message={message} agentKey="claude_code" agentName="Claude Code" />,
      );
      return container.querySelector("time")?.textContent ?? "";
    };
    const at = (iso: string) => {
      const d = new Date(iso);
      const p = (n: number) => String(n).padStart(2, "0");
      return `${p(d.getHours())}:${p(d.getMinutes())}`;
    };
    const CREATED = "2026-01-01T10:14:00Z";

    test("a finished reply shows its clock time and how long it took", () => {
      expect(
        header(makeAssistant({ created_at: CREATED, finished_at: "2026-01-01T10:14:42Z" })),
      ).toBe(`${at(CREATED)} · 42s`);
    });

    test("a long reply reads minutes and padded seconds", () => {
      expect(
        header(makeAssistant({ created_at: CREATED, finished_at: "2026-01-01T10:15:08Z" })),
      ).toBe(`${at(CREATED)} · 1m 08s`);
    });

    test("a stopped reply says after how long", () => {
      expect(
        header(
          makeAssistant({
            status: "stopped",
            created_at: CREATED,
            finished_at: "2026-01-01T10:14:12Z",
          }),
        ),
      ).toBe(`${at(CREATED)} · Stopped after 12s`);
    });

    test("a failed reply says after how long", () => {
      expect(
        header(
          makeAssistant({
            status: "failed",
            created_at: CREATED,
            finished_at: "2026-01-01T10:14:38Z",
          }),
        ),
      ).toBe(`${at(CREATED)} · Failed after 38s`);
    });

    test("a reply still streaming reads Working with a running timer", () => {
      expect(
        header(makeAssistant({ status: "streaming", created_at: new Date().toISOString() })),
      ).toMatch(/· Working · \d+s$/);
    });

    test("a pending question reads Waiting for you", () => {
      const { container } = render(
        <MessageBubble
          message={makeAssistant({ status: "streaming", created_at: CREATED })}
          agentKey="claude_code"
          waiting
        />,
      );
      expect(container.querySelector("time")).toHaveTextContent("Waiting for you");
    });
  });

  describe("the end of a reply", () => {
    test("a finished reply offers Copy reply with its text blocks, and the token line", async () => {
      const writeText = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, { clipboard: { writeText } });
      render(
        <MessageBubble
          message={makeAssistant({
            content: [
              contentBlock({ type: "text", text: "first" }),
              contentBlock({ type: "tool_use", tool_use_id: "t", tool_name: "Grep" }),
              contentBlock({ type: "tool_result", tool_use_id: "t", output: {} }),
              contentBlock({ type: "text", text: "second" }),
            ],
            prompt_tokens: 18234,
            completion_tokens: 1400,
          })}
        />,
      );
      expect(screen.getByText("18.2k in · 1.4k out")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Copy reply" }));
      expect(writeText).toHaveBeenCalledWith("first\n\nsecond");
      await screen.findByRole("button", { name: "Copy reply" });
      await waitFor(() => expect(document.querySelector("svg.lucide-check")).not.toBeNull());
    });

    test("a reply still running has neither Copy reply nor tokens", () => {
      render(<MessageBubble message={makeAssistant({ status: "streaming" })} />);
      expect(screen.queryByRole("button", { name: "Copy reply" })).not.toBeInTheDocument();
    });

    test("files changed sit after the text and before the token line; an estimated row opens nothing", () => {
      const onOpenFile = vi.fn();
      render(
        <MessageBubble
          message={makeAssistant({
            content: [
              contentBlock({ type: "text", text: "Done." }),
              contentBlock({
                type: "tool_use",
                tool_use_id: "w",
                tool_name: "Write",
                tool_input: { file_path: "src/a.py", content: "x\ny\n" },
              }),
              contentBlock({ type: "tool_result", tool_use_id: "w", output: {} }),
            ],
            prompt_tokens: 100,
            completion_tokens: 10,
          })}
          onOpenFile={onOpenFile}
        />,
      );
      const title = screen.getByText("Files changed");
      expect(title.textContent).toBe("Files changed");
      const card = screen.getByRole("region", { name: "Files changed" });
      expect(within(card).getByText("src/a.py")).toBeInTheDocument();
      expect(within(card).queryByRole("button")).not.toBeInTheDocument();
      expect(onOpenFile).not.toHaveBeenCalled();
      const tokens = screen.getByText("100 in · 10 out");
      expect(screen.getByText("Done.").compareDocumentPosition(title)).toBe(
        Node.DOCUMENT_POSITION_FOLLOWING,
      );
      expect(title.compareDocumentPosition(tokens)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    });
  });

  describe("a stopped reply", () => {
    const withTool = (name: string, finished = false): ContentBlock[] => [
      contentBlock({ type: "text", text: "Working on it" }),
      contentBlock({ type: "tool_use", tool_use_id: "t", tool_name: name, tool_input: {} }),
      ...(finished ? [contentBlock({ type: "tool_result", tool_use_id: "t", output: {} })] : []),
    ];

    test("says Stopped by you. and marks the cut-off call Stopped, not Running", () => {
      render(
        <MessageBubble message={makeAssistant({ status: "stopped", content: withTool("Grep") })} />,
      );
      expect(screen.getByText("Stopped by you.")).toBeInTheDocument();
      expect(screen.getByText("Stopped")).toBeInTheDocument();
      expect(screen.queryByText("Running")).not.toBeInTheDocument();
    });

    acceptance("chat", "a stopped reply says it was stopped", () => {
      render(
        <MessageBubble message={makeAssistant({ status: "stopped", content: withTool("Edit") })} />,
      );
      expect(
        screen.getByText("Stopped by you. The edit was not finished; send a message to continue."),
      ).toBeInTheDocument();
    });

    test("a shell tool still running adds that the command was not finished", () => {
      render(
        <MessageBubble message={makeAssistant({ status: "stopped", content: withTool("Bash") })} />,
      );
      expect(
        screen.getByText(
          "Stopped by you. The command was not finished; send a message to continue.",
        ),
      ).toBeInTheDocument();
    });

    test("a call that had finished adds nothing", () => {
      render(
        <MessageBubble
          message={makeAssistant({ status: "stopped", content: withTool("Edit", true) })}
        />,
      );
      expect(screen.getByText("Stopped by you.")).toBeInTheDocument();
    });

    test("the live turn the user just stopped says so before its row lands", () => {
      render(
        <MessageBubble
          live={{ blocks: withTool("Bash"), streaming: false, interrupted: true }}
          agentKey="claude_code"
        />,
      );
      expect(screen.getByText(/The command was not finished/)).toBeInTheDocument();
    });
  });

  describe("tool call status", () => {
    test("a running call is muted text with no warning colour", () => {
      render(
        <MessageBubble
          live={{
            blocks: [contentBlock({ type: "tool_use", tool_use_id: "t", tool_name: "Grep" })],
            streaming: true,
          }}
        />,
      );
      expect(screen.getByText("Running")).toHaveClass("text-text-muted");
    });

    test("after a lost stream a call with no result reads Unknown", () => {
      render(
        <MessageBubble
          live={{
            blocks: [contentBlock({ type: "tool_use", tool_use_id: "t", tool_name: "Grep" })],
            streaming: true,
          }}
          bannerState="lost"
          banner={<p>lost banner</p>}
        />,
      );
      expect(screen.getByText("Unknown")).toBeInTheDocument();
      expect(screen.queryByText(/thinking/i)).not.toBeInTheDocument();
      expect(screen.getByText("lost banner")).toBeInTheDocument();
    });
  });

  test("a not-delivered mark is a quiet warning line with no help control", () => {
    render(<MessageBubble message={makeUser({})} undeliveredTo="SeaTalk" />);
    expect(screen.getByText("Not delivered to SeaTalk yet · will retry")).toHaveClass(
      "text-warning",
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
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
            contentBlock({ type: "text", text: "look" }),
            contentBlock({ type: "attachment", filename: "photo.jpg", mime: "image/jpeg" }),
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
        message={makeUser({
          content: [contentBlock({ type: "attachment", filename: null, mime: null })],
        })}
      />,
    );
    expect(screen.getByText("Attachment")).toBeInTheDocument();
  });

  test("bubbles size to their content, capped by the column and not only by a number", () => {
    const { container } = render(<MessageBubble message={makeUser({})} />);
    const bubble = container.querySelector(".rounded-xl") as HTMLElement;
    expect(bubble.className).toContain("w-fit");
    // 540px OR the column, whichever is smaller. A flat cap was fine while the
    // thread owned the window; beside a context panel the column is narrower
    // than 540px, and an oversized child of an `items-end` column overflows
    // the START edge — so a long message slid left, under the sidebar, with
    // its first characters cut off.
    expect(bubble.className).toContain("max-w-[min(540px,100%)]");
  });

  describe("an assistant turn's text and tool calls render in the order the turn emitted them", () => {
    const orderedBlocks: ContentBlock[] = [
      contentBlock({ type: "text", text: "BEFORE" }),
      contentBlock({
        type: "tool_use",
        tool_use_id: "tu-1",
        tool_name: "read_file",
        tool_input: {},
      }),
      contentBlock({
        type: "tool_result",
        tool_use_id: "tu-1",
        tool_name: "read_file",
        output: {},
      }),
      contentBlock({ type: "text", text: "AFTER" }),
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
      expect(screen.getAllByRole("button", { name: /toggle tool call/i })).toHaveLength(1);
      expect(screen.getByText(/done/i)).toBeInTheDocument();
    });

    test("the live bubble of a turn still streaming", () => {
      const { container } = render(
        <MessageBubble live={{ blocks: orderedBlocks, streaming: true }} />,
      );
      expect(renderedOrder(container)).toEqual(["BEFORE", "card", "AFTER"]);
      expect(screen.getAllByRole("button", { name: /toggle tool call/i })).toHaveLength(1);
    });
  });
});

describe("MessageBubble tool-call folding", () => {
  const calls = (n: number, withResults = true): ContentBlock[] =>
    Array.from({ length: n }, (_, i) => [
      contentBlock({
        type: "tool_use",
        tool_use_id: `t${i}`,
        tool_name: "shell",
        tool_input: { command: `ls ${i}` },
      }),
      ...(withResults
        ? [contentBlock({ type: "tool_result", tool_use_id: `t${i}`, output: { ok: true } })]
        : []),
    ]).flat();

  test("two calls stay as cards", () => {
    render(<MessageBubble message={makeAssistant({ content: calls(2) })} />);
    expect(screen.queryByTestId("tool-call-group")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /toggle tool call/i })).toHaveLength(2);
  });

  test("three or more fold into one collapsed row that expands on click", () => {
    render(<MessageBubble message={makeAssistant({ content: calls(4) })} />);
    const toggle = screen.getByRole("button", { name: /ran 4 tool calls/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: /toggle tool call/i })).not.toBeInTheDocument();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByRole("button", { name: /toggle tool call/i })).toHaveLength(4);
  });

  test("a group with a call still running is open", () => {
    render(
      <MessageBubble message={makeAssistant({ status: "streaming", content: calls(3, false) })} />,
    );
    expect(screen.getByRole("button", { name: /ran 3 tool calls/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  test("a group with a failed call is open and flags it", () => {
    const content = calls(3);
    content[1] = contentBlock({ type: "tool_result", tool_use_id: "t0", error: "boom" });
    render(<MessageBubble message={makeAssistant({ content })} />);
    expect(screen.getByRole("button", { name: /ran 3 tool calls/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByText("1 failed")).toBeInTheDocument();
  });
});
