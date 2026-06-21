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

  test("find reports the match count over the whole document", () => {
    // Match counting reads the full doc (not the virtualized viewport), so it is
    // reliable in jsdom even when CodeMirror only renders the first lines.
    const { container } = render(
      <CodeView value={"alpha beta alpha gamma alpha"} filename="a.txt" />,
    );
    fireEvent.keyDown(container.firstChild as HTMLElement, { key: "f", ctrlKey: true });
    fireEvent.change(screen.getByPlaceholderText(/find/i), { target: { value: "alpha" } });
    expect(screen.getByText("1/3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(screen.getByText("2/3")).toBeInTheDocument();
  });

  test("re-applies an open search when the file content changes", () => {
    // Switching files reuses the same CodeView instance; an open find must
    // re-count against the new content instead of going stale.
    const { container, rerender } = render(<CodeView value={"alpha alpha"} filename="a.txt" />);
    fireEvent.keyDown(container.firstChild as HTMLElement, { key: "f", ctrlKey: true });
    fireEvent.change(screen.getByPlaceholderText(/find/i), { target: { value: "alpha" } });
    expect(screen.getByText("1/2")).toBeInTheDocument();
    rerender(<CodeView value={"alpha beta alpha gamma alpha"} filename="b.txt" />);
    expect(screen.getByText("1/3")).toBeInTheDocument();
  });

  test("Escape closes the find widget", () => {
    const { container } = render(<CodeView value="hello" filename="a.txt" />);
    fireEvent.keyDown(container.firstChild as HTMLElement, { key: "f", ctrlKey: true });
    expect(screen.getByRole("search")).toBeInTheDocument();
    fireEvent.keyDown(screen.getByPlaceholderText(/find/i), { key: "Escape" });
    expect(screen.queryByRole("search")).not.toBeInTheDocument();
  });
});
