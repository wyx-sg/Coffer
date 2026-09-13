// frontend/src/kinds/memory/MemoryFactCard.test.tsx
//
// One fact: shows where it came from (ADR aggregate-agent-memory-never-write-it
// — "everything here is derived ... show its origins"), and exposes the
// hide/pin/supersede overrides (spec memory FR-040).
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { MemoryFactCard } from "./MemoryFactCard";
import type { FactOut, FactSummaryOut } from "./types";

const setOverrideMutate = vi.fn();
const clearOverrideMutate = vi.fn();

vi.mock("./useMemory", () => ({
  useMemoryFact: vi.fn(),
  useSetOverride: vi.fn(() => ({ mutate: setOverrideMutate, isPending: false })),
  useClearOverride: vi.fn(() => ({ mutate: clearOverrideMutate, isPending: false })),
}));

const { useMemoryFact } = await import("./useMemory");
const factDetailMock = vi.mocked(useMemoryFact);

const FACT: FactSummaryOut = {
  key: "claude_code:coffer:worktree-rule",
  slug: "worktree-rule",
  partition: "coffer",
  title: "Develop in a worktree",
  description: "This repository must be developed in a git worktree.",
  type: "project",
  status: "active",
  superseded_by: "",
  conflicts_with: [],
  proposed: false,
  hidden: false,
  pinned: false,
};

const FACT_DETAIL: FactOut = {
  ...FACT,
  body: "Always develop in a git worktree — multiple parallel sessions share the repo.",
  origins: [
    {
      agent: "claude_code",
      native_path: "/Users/dev/.claude/projects/coffer/memory/worktree-rule.md",
      anchor: "worktree-rule",
      captured_at: "2026-09-10T08:00:00Z",
      source_written_at: "2026-09-09T12:00:00Z",
    },
  ],
};

describe("MemoryFactCard", () => {
  test("shows its origins once expanded", () => {
    factDetailMock.mockReturnValue({
      data: FACT_DETAIL,
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof useMemoryFact>);

    render(<MemoryFactCard fact={FACT} override={undefined} partition="coffer" candidates={[]} />);

    fireEvent.click(screen.getByRole("button", { name: /show origins/i }));

    expect(screen.getByText(/multiple parallel sessions share the repo/i)).toBeInTheDocument();
    expect(screen.getByText("claude_code")).toBeInTheDocument();
    expect(
      screen.getByText("/Users/dev/.claude/projects/coffer/memory/worktree-rule.md"),
    ).toBeInTheDocument();
  });

  test("hiding a fact calls the override endpoint with hidden: true", () => {
    factDetailMock.mockReturnValue({
      data: undefined,
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof useMemoryFact>);

    render(<MemoryFactCard fact={FACT} override={undefined} partition="coffer" candidates={[]} />);

    fireEvent.click(screen.getByRole("button", { name: /^hide$/i }));

    expect(setOverrideMutate).toHaveBeenCalledWith({
      factKey: FACT.key,
      patch: { hidden: true },
    });
  });

  test("an already-hidden fact offers Unhide, clearing the override", () => {
    factDetailMock.mockReturnValue({
      data: undefined,
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof useMemoryFact>);

    render(
      <MemoryFactCard
        fact={{ ...FACT, hidden: true }}
        override={{
          fact_key: FACT.key,
          hidden: true,
          pinned: false,
          superseded_by: "",
          conflict_choice: "",
        }}
        partition="coffer"
        candidates={[]}
      />,
    );

    expect(screen.getByText(/hidden/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /unhide/i }));

    expect(clearOverrideMutate).toHaveBeenCalledWith({ factKey: FACT.key, field: "hidden" });
  });
});
