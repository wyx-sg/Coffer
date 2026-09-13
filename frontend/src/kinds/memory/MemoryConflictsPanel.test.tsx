// frontend/src/kinds/memory/MemoryConflictsPanel.test.tsx
//
// Conflicts as pairs to settle (spec memory User Story 4 / FR-033): a
// model's proposal is visibly distinct ("Proposed") from a decision the
// developer already made, and picking a side calls the `settle` override.
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { MemoryConflictsPanel } from "./MemoryConflictsPanel";
import type { FactSummaryOut, OverrideOut } from "./types";

const setOverrideMutate = vi.fn();
vi.mock("./useMemory", () => ({
  useSetOverride: vi.fn(() => ({ mutate: setOverrideMutate, isPending: false })),
}));

function fact(overrides: Partial<FactSummaryOut>): FactSummaryOut {
  return {
    key: overrides.key ?? "key",
    slug: overrides.slug ?? "slug",
    partition: "coffer",
    title: "title",
    description: "description",
    type: "project",
    status: "active",
    superseded_by: "",
    conflicts_with: [],
    proposed: false,
    hidden: false,
    pinned: false,
    ...overrides,
  };
}

const FACT_A = fact({
  key: "a",
  slug: "a",
  title: "The chat page shipped",
  conflicts_with: ["b"],
  proposed: true,
});
const FACT_B = fact({
  key: "b",
  slug: "b",
  title: "The chat page was removed",
  conflicts_with: ["a"],
  proposed: true,
});

describe("MemoryConflictsPanel", () => {
  test("renders an unsettled pair side by side", () => {
    render(<MemoryConflictsPanel facts={[FACT_A, FACT_B]} overrides={[]} />);
    expect(screen.getByTestId("memory-conflict-pair-a-b")).toBeInTheDocument();
    expect(screen.getByText("The chat page shipped")).toBeInTheDocument();
    expect(screen.getByText("The chat page was removed")).toBeInTheDocument();
  });

  test("settling a conflict calls the override endpoint with the chosen fact key", () => {
    render(<MemoryConflictsPanel facts={[FACT_A, FACT_B]} overrides={[]} />);

    const pair = within(screen.getByTestId("memory-conflict-pair-a-b"));
    const buttons = pair.getAllByRole("button", { name: /keep this one/i });
    fireEvent.click(buttons[1]); // keep the second side (FACT_B)

    expect(setOverrideMutate).toHaveBeenCalledWith({
      factKey: "a",
      patch: { conflict_choice: "b" },
    });
  });

  test("a pair already settled by an override is not shown again", () => {
    const overrides: OverrideOut[] = [
      { fact_key: "a", hidden: false, pinned: false, superseded_by: "", conflict_choice: "b" },
    ];
    const { container } = render(
      <MemoryConflictsPanel facts={[FACT_A, FACT_B]} overrides={overrides} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
