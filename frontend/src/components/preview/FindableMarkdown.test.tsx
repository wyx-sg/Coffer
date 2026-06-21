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
});
