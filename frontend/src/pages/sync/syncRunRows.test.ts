import { describe, expect, test } from "vitest";

import type { RunRecord } from "@/lib/api/sync";
import { collapseQuietRounds, heldRoundId, isQuiet, quietSpan } from "./syncRunRows";

const NO_COUNTS = { added: 0, modified: 0, deleted: 0, changes: [] };

function run(over: Partial<RunRecord> & { id: number }): RunRecord {
  return {
    status: "no_change",
    join: null,
    applied: NO_COUNTS,
    published: NO_COUNTS,
    commit: "abc1234",
    conflicts: [],
    agent_resolved: [],
    failures: [],
    locked_refs: [],
    pending: null,
    error: null,
    started_at: `2026-09-16T0${over.id}:00:00Z`,
    finished_at: `2026-09-16T0${over.id}:00:05Z`,
    ...over,
  } as RunRecord;
}

describe("isQuiet", () => {
  test("a round that changed nothing and reported nothing is quiet", () => {
    expect(isQuiet(run({ id: 1 }))).toBe(true);
  });

  // Each of these ends `no_change` and still has something a reader wants a
  // row for — which is why the test is not `status === "no_change"`.
  test.each([
    ["a join", { join: "new" as const }],
    ["a failure", { failures: [{ path: "resources/a.yaml", reason: "boom" }] }],
    ["a locked credential ref", { locked_refs: ["github.TOKEN"] }],
    ["an agent-resolved conflict", { agent_resolved: ["knowledge/a.md"] }],
    ["an error", { error: "remote unreachable" }],
  ])("a no_change round with %s is not quiet", (_label, over) => {
    expect(isQuiet(run({ id: 1, ...(over as Partial<RunRecord>) }))).toBe(false);
  });

  test("a round that applied something is not quiet whatever its status", () => {
    const applied = { added: 1, modified: 0, deleted: 0, changes: [{ path: "a", status: "added" }] };
    expect(isQuiet(run({ id: 1, applied } as Partial<RunRecord> & { id: number }))).toBe(false);
  });
});

describe("collapseQuietRounds", () => {
  test("consecutive quiet rounds become one row", () => {
    const rows = collapseQuietRounds([run({ id: 5 }), run({ id: 4 }), run({ id: 3 })]);
    expect(rows).toHaveLength(1);
    expect(rows[0].kind).toBe("quiet");
    expect(rows[0].kind === "quiet" && rows[0].runs.map((r) => r.id)).toEqual([5, 4, 3]);
  });

  test("a lone quiet round stays a round — a group of one reads worse", () => {
    const rows = collapseQuietRounds([run({ id: 2, status: "ok" }), run({ id: 1 })]);
    expect(rows.map((r) => r.kind)).toEqual(["run", "run"]);
  });

  test("a round that did something breaks the fold in two", () => {
    // This is the whole point of folding ADJACENT rounds only: the busy round
    // in the middle must not be swallowed, and the two quiet stretches around
    // it are two different stretches.
    const rows = collapseQuietRounds([
      run({ id: 6 }),
      run({ id: 5 }),
      run({ id: 4, status: "ok", published: { ...NO_COUNTS, added: 3 } }),
      run({ id: 3 }),
      run({ id: 2 }),
    ]);
    expect(rows.map((r) => r.kind)).toEqual(["quiet", "run", "quiet"]);
    expect(rows[0].kind === "quiet" && rows[0].runs.map((r) => r.id)).toEqual([6, 5]);
    expect(rows[2].kind === "quiet" && rows[2].runs.map((r) => r.id)).toEqual([3, 2]);
  });

  test("every round survives the fold — nothing is dropped", () => {
    const runs = [run({ id: 4 }), run({ id: 3 }), run({ id: 2, status: "ok" }), run({ id: 1 })];
    const seen = collapseQuietRounds(runs).flatMap((r) =>
      r.kind === "run" ? [r.run.id] : r.runs.map((x) => x.id),
    );
    expect(seen).toEqual([4, 3, 2, 1]);
  });

  test("row ids are unique and stable", () => {
    const rows = collapseQuietRounds([run({ id: 3 }), run({ id: 2 }), run({ id: 1, status: "ok" })]);
    const ids = rows.map((r) => r.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(collapseQuietRounds([run({ id: 3 }), run({ id: 2 }), run({ id: 1, status: "ok" })])
      .map((r) => r.id)).toEqual(ids);
  });

  test("an empty history folds to nothing", () => {
    expect(collapseQuietRounds([])).toEqual([]);
  });
});

describe("quietSpan", () => {
  test("spans from the oldest member's start to the newest member's finish", () => {
    // The list is newest-first, so the span's ends come from opposite ends of it.
    const span = quietSpan([run({ id: 3 }), run({ id: 2 }), run({ id: 1 })]);
    expect(span).toEqual({
      from: "2026-09-16T01:00:00Z",
      to: "2026-09-16T03:00:05Z",
      count: 3,
    });
  });
});

describe("heldRoundId", () => {
  // `POST /sync/confirm` acts on the vault's current pending state, not on a
  // round named in the request. These two tests are the difference between an
  // actionable row and a button that lies.
  test("the newest round carries the actions while the vault is waiting", () => {
    const runs = [run({ id: 9, status: "awaiting_confirmation" }), run({ id: 8 })];
    expect(heldRoundId(runs, true)).toBe(9);
  });

  test("a round that WAS held carries nothing once the vault is no longer waiting", () => {
    // Exactly the state this machine was in: two rows still reading
    // `awaiting_confirmation`, both already answered, the vault at rest.
    const runs = [
      run({ id: 9, status: "awaiting_confirmation" }),
      run({ id: 8, status: "awaiting_confirmation" }),
    ];
    expect(heldRoundId(runs, false)).toBeNull();
  });

  test("only the NEWEST round is offered, never an older held one", () => {
    const runs = [run({ id: 9, status: "ok" }), run({ id: 8, status: "awaiting_confirmation" })];
    expect(heldRoundId(runs, true)).toBeNull();
  });

  test("an empty history offers nothing", () => {
    expect(heldRoundId([], true)).toBeNull();
  });
});
