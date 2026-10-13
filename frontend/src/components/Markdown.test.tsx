// frontend/src/components/Markdown.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";

import { Markdown } from "./Markdown";

describe("Markdown", () => {
  test("demotes headings one level so a document never adds a second h1", () => {
    render(<Markdown>{"# Title\n\n## Section\n\n###### Deep"}</Markdown>);
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Title");
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent("Section");
    expect(screen.getByRole("heading", { level: 6 })).toHaveTextContent("Deep");
  });

  test("inline code stays on the type scale", () => {
    render(<Markdown>{"use `coffer daemon start`"}</Markdown>);
    const code = screen.getByText("coffer daemon start");
    expect(code.tagName).toBe("CODE");
    expect(code.className).toContain("text-xs");
  });

  describe("allowHtml", () => {
    const html = [
      "<!-- skynet-confluence-storage:v1 &lt;ac:macro/&gt; -->",
      '<table><tr><th rowspan="2">Head</th><td colspan="3">Wide</td></tr></table>',
      "",
      "<details open><summary>Fold</summary>Inside</details>",
      "",
      '<script>alert(1)</script><style>p{}</style><iframe src="https://x.example"></iframe>',
      '<object data="x"></object><embed src="x"><form action="/x"><input name="q"></form>',
      '<img src="pic.png" alt="Pic" onerror="alert(1)"><a href="https://ok.example" onclick="alert(1)">ok</a>',
      '<a href="javascript:alert(1)">bad</a>',
    ].join("\n");

    test("renders tables with spans and folds, and drops whatever could run", () => {
      const { container } = render(<Markdown allowHtml>{html}</Markdown>);
      expect(screen.getByText("Head")).toHaveAttribute("rowspan", "2");
      expect(screen.getByText("Wide")).toHaveAttribute("colspan", "3");
      expect(screen.getByText("Fold").tagName).toBe("SUMMARY");
      expect(screen.getByText("Fold").closest("details")).toHaveAttribute("open");
      for (const tag of ["script", "style", "iframe", "object", "embed", "form"]) {
        expect(container.querySelector(tag)).toBeNull();
      }
      expect(container.innerHTML).not.toMatch(/\son[a-z]+=/i);
      expect(container.innerHTML).not.toContain("javascript:");
      expect(container.textContent).not.toContain("skynet-confluence-storage");
      expect(screen.getByRole("img", { name: "Pic" })).toHaveAttribute("src", "pic.png");
      expect(screen.getByRole("link", { name: "ok" })).toHaveAttribute(
        "href",
        "https://ok.example",
      );
    });

    test("is off by default: HTML stays text, as in chat", () => {
      const { container } = render(<Markdown>{"<b>bold</b> and <script>x</script>"}</Markdown>);
      expect(container.querySelector("b")).toBeNull();
      expect(container.querySelector("script")).toBeNull();
      expect(container.textContent).toContain("<b>bold</b>");
    });
  });
});
