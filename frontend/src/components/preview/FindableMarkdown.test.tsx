// src/components/preview/FindableMarkdown.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { FindableMarkdown } from "./FindableMarkdown";

const SOURCE = "# Title\n\nsome alpha and more alpha text";

describe("FindableMarkdown", () => {
  test("renders the markdown content", () => {
    render(<FindableMarkdown>{SOURCE}</FindableMarkdown>);
    expect(screen.getByRole("heading", { name: "Title" })).toBeInTheDocument();
  });

  test("constrains the rendered body to a centered reading max-width", () => {
    const { container } = render(<FindableMarkdown>{SOURCE}</FindableMarkdown>);
    // Content sits inside a centered max-width wrapper so long lines don't
    // stretch edge-to-edge on wide screens.
    const wrapper = container.querySelector(".max-w-3xl");
    expect(wrapper).not.toBeNull();
    expect(wrapper).toHaveClass("mx-auto");
    expect(wrapper).toContainElement(screen.getByRole("heading", { name: "Title" }));
  });

  test("Cmd/Ctrl+F opens find and counts matches in the rendered text", () => {
    const { container } = render(<FindableMarkdown>{SOURCE}</FindableMarkdown>);
    const region = container.querySelector("[tabindex]") as HTMLElement;
    fireEvent.keyDown(region, { key: "f", ctrlKey: true });
    fireEvent.change(screen.getByPlaceholderText(/find/i), { target: { value: "alpha" } });
    expect(screen.getByText("1/2")).toBeInTheDocument();
  });

  test("a query with no matches reports no matches", () => {
    const { container } = render(<FindableMarkdown>{SOURCE}</FindableMarkdown>);
    const region = container.querySelector("[tabindex]") as HTMLElement;
    fireEvent.keyDown(region, { key: "f", ctrlKey: true });
    fireEvent.change(screen.getByPlaceholderText(/find/i), { target: { value: "zzz" } });
    expect(screen.getByText(/no matches/i)).toBeInTheDocument();
  });

  test("does not open find when no initialQuery is given", () => {
    render(<FindableMarkdown>{SOURCE}</FindableMarkdown>);
    expect(screen.queryByPlaceholderText(/find/i)).not.toBeInTheDocument();
  });

  test("seeds find from initialQuery and highlights matches on mount", () => {
    render(<FindableMarkdown initialQuery="alpha">{SOURCE}</FindableMarkdown>);
    expect(screen.getByPlaceholderText(/find/i)).toHaveValue("alpha");
    expect(screen.getByText("1/2")).toBeInTheDocument();
  });

  test("re-seeds when initialQuery changes to a new term", () => {
    const { rerender } = render(<FindableMarkdown initialQuery="alpha">{SOURCE}</FindableMarkdown>);
    rerender(<FindableMarkdown initialQuery="Title">{SOURCE}</FindableMarkdown>);
    expect(screen.getByPlaceholderText(/find/i)).toHaveValue("Title");
    expect(screen.getByText("1/1")).toBeInTheDocument();
  });

  test("a file's frontmatter is shown as metadata above the body, not as body text", () => {
    const { container } = render(
      <FindableMarkdown>
        {"---\ntitle: Build with uv\norigins:\n  - claude_code\n  - codex\n---\n# Heading\n\nbody"}
      </FindableMarkdown>,
    );
    const meta = screen.getByTestId("markdown-frontmatter");
    expect(meta.tagName).toBe("DL");
    expect(meta).toHaveTextContent("title");
    expect(meta).toHaveTextContent("Build with uv");
    expect(meta).toHaveTextContent("claude_code");
    // The fences did not become a rule, and the keys are not in a paragraph or
    // a bullet list of the rendered body.
    expect(container.querySelector("hr")).toBeNull();
    const heading = screen.getByRole("heading", { name: "Heading" });
    expect(meta.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    for (const p of container.querySelectorAll("p")) {
      expect(p.textContent).not.toMatch(/title:|origins:/);
    }
  });

  test("the front matter is a key / value grid: mono keys in a 96 column, wrapping values, a hairline below", () => {
    render(<FindableMarkdown>{"---\nname: s\ndescription: d\n---\n# H"}</FindableMarkdown>);
    const meta = screen.getByTestId("markdown-frontmatter");
    expect(meta).toHaveClass("grid-cols-[96px_minmax(0,1fr)]", "border-b");
    expect(screen.getByText("name")).toHaveClass("font-mono", "text-text-subtle");
    expect(screen.getByText("d")).toHaveClass("break-words");
  });

  test("frontmatter splitting can be turned off for text that is not a file", () => {
    render(<FindableMarkdown frontmatter={false}>{"---\ntitle: T\n---\nbody"}</FindableMarkdown>);
    expect(screen.queryByTestId("markdown-frontmatter")).toBeNull();
  });

  test("closes find when initialQuery becomes empty", () => {
    const { rerender } = render(<FindableMarkdown initialQuery="alpha">{SOURCE}</FindableMarkdown>);
    expect(screen.getByPlaceholderText(/find/i)).toBeInTheDocument();
    rerender(<FindableMarkdown initialQuery="">{SOURCE}</FindableMarkdown>);
    expect(screen.queryByPlaceholderText(/find/i)).not.toBeInTheDocument();
  });
});
