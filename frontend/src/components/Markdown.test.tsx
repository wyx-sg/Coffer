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
    expect(code.className).toContain("text-sm");
  });
});
