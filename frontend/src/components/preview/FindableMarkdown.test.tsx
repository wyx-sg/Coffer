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

  test("closes find when initialQuery becomes empty", () => {
    const { rerender } = render(<FindableMarkdown initialQuery="alpha">{SOURCE}</FindableMarkdown>);
    expect(screen.getByPlaceholderText(/find/i)).toBeInTheDocument();
    rerender(<FindableMarkdown initialQuery="">{SOURCE}</FindableMarkdown>);
    expect(screen.queryByPlaceholderText(/find/i)).not.toBeInTheDocument();
  });
});
