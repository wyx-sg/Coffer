// frontend/src/kinds/knowledge/KnowledgeSearchBar.test.tsx
//
// Focused component tests for the one retrieval bar both lanes share. External
// retrieval is "one query → one answer": a shared SearchInput (magnifier +
// clear) plus an action button whose label the lane supplies ("Recall" for
// entries, "Search" for documents). Running it filters the lane's tree to the
// hits and opens the top match highlighted (handled by the lane) — the bar
// never renders its own results.

import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { KnowledgeSearchBar } from "./KnowledgeSearchBar";

function renderBar() {
  const onSearch = vi.fn();
  const onQueryChange = vi.fn();
  render(
    <KnowledgeSearchBar
      query="needle"
      error={null}
      isPending={false}
      onQueryChange={onQueryChange}
      onSearch={onSearch}
      placeholder="Search this scope's documents…"
      actionLabel="Search"
    />,
  );
  return { onSearch, onQueryChange };
}

describe("KnowledgeSearchBar", () => {
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
