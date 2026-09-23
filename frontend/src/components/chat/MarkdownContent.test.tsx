import { afterEach, describe, expect, test, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import { MarkdownContent } from "./MarkdownContent";
import { MessageBubble } from "./MessageBubble";

describe("MarkdownContent code-block copy", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  test("copies the block's text to the clipboard and confirms for 1.5 s", async () => {
    // Fake timers (still advancing real time) so the confirmation's timeout is
    // ours to fire.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    render(<MarkdownContent content={"```js\nconst x = 1;\n```"} />);

    fireEvent.click(screen.getByRole("button", { name: /^copy$/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("const x = 1;\n"));
    expect(await screen.findByRole("status")).toHaveTextContent(/copied/i);

    act(() => {
      vi.advanceTimersByTime(1500);
    });
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  test("inline code gets no copy button", () => {
    render(<MarkdownContent content="use `foo()`" />);
    expect(screen.queryByRole("button", { name: /copy/i })).not.toBeInTheDocument();
  });
});

describe("MarkdownContent", () => {
  test("renders bold/italic markup as real elements, not raw characters", () => {
    const { container } = render(<MarkdownContent content="This is **bold** and *italic*." />);
    expect(container.querySelector("strong")?.textContent).toBe("bold");
    expect(container.querySelector("em")?.textContent).toBe("italic");
    expect(container.textContent).not.toContain("**");
  });

  test("keeps single newlines as line breaks (remark-breaks)", () => {
    // Agent output (e.g. the `/usage` report) lays facts out one per line with a
    // single newline. CommonMark collapses those into spaces; remark-breaks must
    // turn them into <br> so the lines stay visually separate.
    const { container } = render(<MarkdownContent content={"line one\nline two\nline three"} />);
    expect(container.querySelectorAll("br").length).toBeGreaterThanOrEqual(2);
    // Still one paragraph — the lines are joined by <br>, not split into many <p>.
    expect(container.querySelectorAll("p")).toHaveLength(1);
  });

  test("renders a bullet list as <li> items", () => {
    const { container } = render(<MarkdownContent content={"- one\n- two"} />);
    const items = container.querySelectorAll("li");
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toBe("one");
  });

  test("renders a fenced code block with syntax-highlight classes", () => {
    const md = "```js\nconst x = 1;\n```";
    const { container } = render(<MarkdownContent content={md} />);
    const code = container.querySelector("pre code");
    expect(code).not.toBeNull();
    // rehype-highlight tags highlighted code with the hljs class.
    expect(code?.className).toContain("hljs");
  });

  test("renders inline code distinct from a code block", () => {
    const { container } = render(<MarkdownContent content="use the `foo()` call" />);
    const inline = container.querySelector("code");
    expect(inline?.textContent).toBe("foo()");
    expect(inline?.closest("pre")).toBeNull();
  });

  test("renders a GFM table (remark-gfm enabled)", () => {
    const md = "| a | b |\n| - | - |\n| 1 | 2 |";
    const { container } = render(<MarkdownContent content={md} />);
    expect(container.querySelector("table")).not.toBeNull();
    expect(container.querySelectorAll("td")).toHaveLength(2);
  });

  test("links open safely in a new tab", () => {
    render(<MarkdownContent content="[site](https://example.com)" />);
    const link = screen.getByRole("link", { name: "site" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });
});

acceptance("chat", "assistant text keeps its line breaks and every code block copies", () => {
  const reply = [
    "first fact",
    "second fact",
    "",
    "| name | size |",
    "| --- | --- |",
    "| a.txt | 3 |",
    "",
    "```sh",
    "ls -la",
    "```",
    "",
    "```py",
    "print(1)",
    "```",
  ].join("\n");
  const { container } = render(
    <MessageBubble
      message={{
        id: "m-1",
        conversation_id: "c-1",
        seq: 1,
        role: "assistant",
        status: "complete",
        created_at: "2026-01-01T00:00:00Z",
        content: [{ type: "text", text: reply }],
      }}
    />,
  );

  const firstParagraph = container.querySelector("p")!;
  expect(firstParagraph.querySelector("br")).not.toBeNull();
  expect(firstParagraph.textContent).toContain("first fact");
  expect(firstParagraph.textContent).toContain("second fact");
  expect(container.querySelector("table")).not.toBeNull();
  expect(container.querySelectorAll("td")[0].textContent).toBe("a.txt");
  expect(container.querySelectorAll("pre")).toHaveLength(2);
  expect(screen.getAllByRole("button", { name: /^copy$/i })).toHaveLength(2);
});
