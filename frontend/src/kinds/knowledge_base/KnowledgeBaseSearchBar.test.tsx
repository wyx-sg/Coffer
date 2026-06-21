// frontend/src/kinds/knowledge_base/KnowledgeBaseSearchBar.test.tsx
//
// Focused component tests for the unified retrieval bar's grep results. Grep
// hits carry the matched file path (`docs/<doc-id>.md`); clicking a hit must
// open that document via onSelectDocument — mirroring keyword/vector results.
// Malformed paths (no `docs/` prefix, no `.md` suffix, or empty id) must render
// as plain, non-clickable text rather than a broken/empty-id click.

import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { KnowledgeBaseSearchBar } from "./KnowledgeBaseSearchBar";
import type { GrepResponse } from "./api";

function renderBar(grepResult: GrepResponse, onSelectDocument = vi.fn()) {
  render(
    <KnowledgeBaseSearchBar
      query="needle"
      mode="grep"
      searchResult={null}
      grepResult={grepResult}
      error={null}
      isPending={false}
      onQueryChange={vi.fn()}
      onModeChange={vi.fn()}
      onSearch={vi.fn()}
      onSelectDocument={onSelectDocument}
    />,
  );
  return onSelectDocument;
}

describe("KnowledgeBaseSearchBar grep results", () => {
  test("a valid grep hit renders a clickable button that opens the document", () => {
    const onSelectDocument = renderBar({
      hits: [{ path: "docs/d1.md", line_number: 7, line: "matched needle here" }],
      truncated: false,
    });

    const hit = screen.getByRole("button", { name: /matched needle here/ });
    fireEvent.click(hit);
    expect(onSelectDocument).toHaveBeenCalledWith("d1");
  });

  test("a malformed path (no docs/ prefix or .md suffix) renders non-clickable plain text", () => {
    const onSelectDocument = renderBar({
      hits: [{ path: "weird", line_number: 1, line: "no path prefix" }],
      truncated: false,
    });

    expect(screen.getByText("no path prefix")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /no path prefix/ })).not.toBeInTheDocument();
    expect(onSelectDocument).not.toHaveBeenCalled();
  });

  test("an empty doc id (docs/.md) renders non-clickable plain text", () => {
    const onSelectDocument = renderBar({
      hits: [{ path: "docs/.md", line_number: 2, line: "empty id" }],
      truncated: false,
    });

    expect(screen.getByText("empty id")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /empty id/ })).not.toBeInTheDocument();
    expect(onSelectDocument).not.toHaveBeenCalled();
  });
});
