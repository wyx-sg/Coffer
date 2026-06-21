import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";

import { MarkdownContent } from "./MarkdownContent";

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
