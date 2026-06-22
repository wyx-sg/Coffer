// frontend/src/kinds/memory/MemoryFactTree.test.tsx
//
// The fact tree lists each fact by its `title` (falling back to a body slice).
// The "edited" actor badge was removed in the unified-format pass, so a
// user-authored fact must render no such badge.
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryFactTree } from "./MemoryFactTree";
import type { FactOut } from "./api";

const fact = (over: Partial<FactOut>): FactOut => ({
  id: "f1",
  store_name: "global",
  scope: "global",
  title: "tabs",
  description: "",
  text: "uses tabs",
  actor: "user",
  created_at: "2026-06-22T00:00:00Z",
  updated_at: "2026-06-22T00:00:00Z",
  ...over,
});

describe("MemoryFactTree", () => {
  test("renders facts by their title", () => {
    render(
      <MemoryFactTree
        facts={{ facts: [fact({})], total: 1 }}
        selectedId={null}
        isLoading={false}
        total={1}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText("tabs")).toBeInTheDocument();
  });

  test("does not render an 'edited' actor badge for user facts", () => {
    render(
      <MemoryFactTree
        facts={{ facts: [fact({ actor: "user" })], total: 1 }}
        selectedId={null}
        isLoading={false}
        total={1}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.queryByText(/edited/i)).toBeNull();
  });
});
