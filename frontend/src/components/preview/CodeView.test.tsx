// src/components/preview/CodeView.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { CodeView } from "./CodeView";

describe("CodeView", () => {
  test("renders the file content read-only", () => {
    // Syntax highlighting splits the line across token spans, so assert on the
    // editor's concatenated text rather than a single node.
    const { container } = render(
      <CodeView value={'model = "gpt-5.5"'} filename="config.toml" ariaLabel="Config" />,
    );
    expect(container.querySelector(".cm-editor")).toBeTruthy();
    expect(container.querySelector(".cm-content")?.textContent).toContain('model = "gpt-5.5"');
  });

  test("Cmd/Ctrl+F opens the find widget", () => {
    const { container } = render(<CodeView value="hello world" filename="a.txt" />);
    expect(screen.queryByRole("search")).not.toBeInTheDocument();
    fireEvent.keyDown(container.firstChild as HTMLElement, { key: "f", ctrlKey: true });
    const widget = screen.getByRole("search");
    expect(within(widget).getByRole("textbox")).toBeInTheDocument();
  });
});
