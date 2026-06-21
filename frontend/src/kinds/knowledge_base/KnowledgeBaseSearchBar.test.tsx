// frontend/src/kinds/knowledge_base/KnowledgeBaseSearchBar.test.tsx
//
// Focused component tests for the retrieval bar. External retrieval is "one
// query → one answer": ONE input + Search button, ranked passages only — no
// mode picker, no grep, no fallback hint. Clicking a passage opens its document
// via onSelectDocument.

import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { KnowledgeBaseSearchBar } from "./KnowledgeBaseSearchBar";
import type { SearchResponse } from "./api";

function renderBar(searchResult: SearchResponse | null, onSelectDocument = vi.fn()) {
  render(
    <KnowledgeBaseSearchBar
      query="needle"
      searchResult={searchResult}
      error={null}
      isPending={false}
      onQueryChange={vi.fn()}
      onSearch={vi.fn()}
      onSelectDocument={onSelectDocument}
    />,
  );
  return onSelectDocument;
}

describe("KnowledgeBaseSearchBar", () => {
  test("renders a single input + Search button (no mode picker)", () => {
    renderBar(null);
    expect(screen.getByRole("button", { name: /^search$/i })).toBeInTheDocument();
    // No mode dropdown anymore.
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  test("a passage renders a clickable button that opens the document", () => {
    const onSelectDocument = renderBar({
      passages: [
        { text: "matched needle here", document_id: "d1", title: "a.md", score: 0.7, position: 0 },
      ],
    });

    const hit = screen.getByRole("button", { name: /matched needle here/ });
    fireEvent.click(hit);
    expect(onSelectDocument).toHaveBeenCalledWith("d1");
  });

  test("an empty passage set shows the no-matches line", () => {
    renderBar({ passages: [] });
    expect(screen.getByText(/no matches/i)).toBeInTheDocument();
  });
});
