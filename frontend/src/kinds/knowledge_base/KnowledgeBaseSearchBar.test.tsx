// frontend/src/kinds/knowledge_base/KnowledgeBaseSearchBar.test.tsx
//
// Focused component tests for the retrieval bar. External retrieval is "one
// query → one answer": a shared SearchInput (magnifier + clear) + Search button.
// Running a search filters the document tree to the hits and opens the top match
// highlighted (handled by the page) — the bar no longer renders its own results.

import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { KnowledgeBaseSearchBar } from "./KnowledgeBaseSearchBar";

function renderBar() {
  const onSearch = vi.fn();
  const onQueryChange = vi.fn();
  render(
    <KnowledgeBaseSearchBar
      query="needle"
      error={null}
      isPending={false}
      onQueryChange={onQueryChange}
      onSearch={onSearch}
    />,
  );
  return { onSearch, onQueryChange };
}

describe("KnowledgeBaseSearchBar", () => {
  test("renders a Search button and no mode picker", () => {
    renderBar();
    expect(screen.getByRole("button", { name: /^search$/i })).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  test("uses the shared SearchInput (clear button shows once there is text)", () => {
    renderBar();
    expect(screen.getByRole("button", { name: /^clear$/i })).toBeInTheDocument();
  });

  test("clicking Search triggers onSearch", () => {
    const { onSearch } = renderBar();
    fireEvent.click(screen.getByRole("button", { name: /^search$/i }));
    expect(onSearch).toHaveBeenCalled();
  });

  test("Enter in the box triggers onSearch", () => {
    const { onSearch } = renderBar();
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" });
    expect(onSearch).toHaveBeenCalled();
  });

  test("does not render an inline results list (results drive the tree now)", () => {
    renderBar();
    expect(screen.queryByText(/no matches/i)).not.toBeInTheDocument();
  });
});
