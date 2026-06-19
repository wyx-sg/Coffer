// frontend/src/components/knowledge/KnowledgeList.test.tsx
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { KnowledgeList } from "./KnowledgeList";
import type { KnowledgeItem } from "@/lib/api/knowledge";

const ITEMS: KnowledgeItem[] = [
  {
    ref: "note:g:f1",
    type: "note",
    scopeId: "g",
    title: "a fact",
    preview: "a preference",
    updatedAt: "t",
    storeName: "global",
    factId: "f1",
  },
  {
    ref: "doc:kb1:d1",
    type: "document",
    scopeId: "g",
    title: "a doc",
    preview: "",
    updatedAt: "t",
    kbName: "kb1",
    documentId: "d1",
    locked: true,
  },
];

describe("KnowledgeList", () => {
  test("lists notes and documents together, each type-tagged", () => {
    render(<KnowledgeList items={ITEMS} onSelect={() => {}} />);
    expect(screen.getByText("a fact")).toBeInTheDocument();
    expect(screen.getByText("a doc")).toBeInTheDocument();
    expect(screen.getByText("Note")).toBeInTheDocument();
    expect(screen.getByText("Document")).toBeInTheDocument();
    // A document's source column shows its KB name.
    expect(screen.getByText("kb1")).toBeInTheDocument();
  });

  test("opens the item on row click", () => {
    const onSelect = vi.fn();
    render(<KnowledgeList items={ITEMS} onSelect={onSelect} />);
    fireEvent.click(screen.getByText("a doc"));
    expect(onSelect).toHaveBeenCalledWith(ITEMS[1]);
  });

  test("filters the list by the free-text search", () => {
    render(<KnowledgeList items={ITEMS} onSelect={() => {}} />);
    const search = screen.getByPlaceholderText(/search notes and documents/i);
    fireEvent.change(search, { target: { value: "doc" } });
    expect(screen.queryByText("a fact")).not.toBeInTheDocument();
    expect(screen.getByText("a doc")).toBeInTheDocument();
  });
});
