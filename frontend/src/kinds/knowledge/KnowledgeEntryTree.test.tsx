// frontend/src/kinds/knowledge/KnowledgeEntryTree.test.tsx
//
// The entry tree lists each entry by its `title` (falling back to a body slice).
// The "edited" actor badge was removed in the unified-format pass, so a
// user-authored entry must render no such badge.
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { KnowledgeEntryTree } from "./KnowledgeEntryTree";
import type { EntryOut } from "./api";

const entry = (over: Partial<EntryOut>): EntryOut => ({
  id: "f1",
  scope_name: "global",
  scope: "global",
  title: "tabs",
  description: "",
  text: "uses tabs",
  actor: "user",
  created_at: "2026-06-22T00:00:00Z",
  updated_at: "2026-06-22T00:00:00Z",
  ...over,
});

describe("KnowledgeEntryTree", () => {
  test("renders entries by their title", () => {
    render(
      <KnowledgeEntryTree
        entries={{ entries: [entry({})], total: 1 }}
        selectedId={null}
        isLoading={false}
        total={1}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText("tabs")).toBeInTheDocument();
  });

  test("does not render an 'edited' actor badge for user entries", () => {
    render(
      <KnowledgeEntryTree
        entries={{ entries: [entry({ actor: "user" })], total: 1 }}
        selectedId={null}
        isLoading={false}
        total={1}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.queryByText(/edited/i)).toBeNull();
  });
});
