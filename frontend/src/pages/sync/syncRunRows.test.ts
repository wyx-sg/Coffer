import { describe, expect, test } from "vitest";

import type { RunRecord } from "@/lib/api/sync";
import { collapseRepeats, isQuiet, groupSpan } from "./syncRunRows";
import { heldRoundId } from "./syncRowActions";
import { acceptance } from "@/test/acceptance";

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

describe("collapseRepeats", () => {
  test("consecutive quiet rounds become one row, bar the newest", () => {
    const rows = collapseRepeats([run({ id: 5 }), run({ id: 4 }), run({ id: 3 })]);
    // The newest round is the present, not the history: it stands alone so a
    // reader sees the state the vault is actually in, and so the row that may
    // carry Undo or an answer is never hidden inside a summary.
    expect(rows.map((r) => r.kind)).toEqual(["run", "group"]);
    expect(rows[1].kind === "group" && rows[1].runs.map((r) => r.id)).toEqual([4, 3]);
  });

  test("a stretch of identical failures folds — the news is the same news", () => {
    // The shape this was written for: an expired credential is ten rows of
    // "failed" by morning, burying every round that said anything else.
    const rows = collapseRepeats([
      run({ id: 9, status: "failed", error: "git fetch failed" }),
      run({ id: 8, status: "failed", error: "git fetch failed" }),
      run({ id: 7, status: "failed", error: "git fetch failed" }),
      run({ id: 6, status: "ok", published: { ...NO_COUNTS, added: 1 } }),
    ]);
    expect(rows.map((r) => r.kind)).toEqual(["run", "group", "run"]);
    expect(rows[1].kind === "group" && rows[1].status).toBe("failed");
    expect(rows[1].kind === "group" && rows[1].runs.map((r) => r.id)).toEqual([8, 7]);
  });

  acceptance(
    "vault-sync",
    "repeated failures fold into one row and the newest round stands alone",
    () => {
      const published = { ...NO_COUNTS, added: 1, changes: [{ path: "a.md", status: "added" }] };
      const rows = collapseRepeats([
        run({ id: 9, status: "failed", error: "git fetch failed" }),
        run({ id: 8, status: "failed", error: "git fetch failed" }),
        run({ id: 7, status: "failed", error: "git fetch failed" }),
        run({ id: 6, status: "ok", published } as Partial<RunRecord> & { id: number }),
      ]);
      // The newest failure stands alone; the two before it are one row of two;
      // the round that published is its own row.
      expect(rows.map((r) => r.kind)).toEqual(["run", "group", "run"]);
      expect(rows[0].kind === "run" && rows[0].run.id).toBe(9);
      expect(rows[1].kind === "group" && rows[1].status).toBe("failed");
      expect(rows[1].kind === "group" && groupSpan(rows[1].runs).count).toBe(2);
      expect(rows[1].kind === "group" && rows[1].runs.map((r) => r.id)).toEqual([8, 7]);
      expect(rows[2].kind === "run" && rows[2].run.id).toBe(6);

      // Held rounds fold by outcome the same way beneath a newer round.
      const held = collapseRepeats([
        run({ id: 4, status: "ok" }),
        run({ id: 3, status: "awaiting_confirmation" }),
        run({ id: 2, status: "awaiting_confirmation" }),
      ]);
      expect(held.map((r) => r.kind)).toEqual(["run", "group"]);
      expect(held[1].kind === "group" && held[1].status).toBe("awaiting_confirmation");
      expect(held[1].kind === "group" && held[1].runs.map((r) => r.id)).toEqual([3, 2]);
    },
  );

  test("a hold re-raised every hour folds too", () => {
    const rows = collapseRepeats([
      run({ id: 4, status: "ok" }),
      run({ id: 3, status: "awaiting_confirmation" }),
      run({ id: 2, status: "awaiting_confirmation" }),
      run({ id: 1, status: "awaiting_confirmation" }),
    ]);
    expect(rows.map((r) => r.kind)).toEqual(["run", "group"]);
    expect(rows[1].kind === "group" && rows[1].runs).toHaveLength(3);
  });

  test("rounds that changed something never fold, however many in a row", () => {
    // `+3 ~1 −0` twice is two facts, not one printed twice.
    const busy = { ...NO_COUNTS, added: 3 };
    const rows = collapseRepeats([
      run({ id: 4, status: "ok", published: busy }),
      run({ id: 3, status: "ok", published: busy }),
      run({ id: 2, status: "ok", published: busy }),
    ]);
    expect(rows.map((r) => r.kind)).toEqual(["run", "run", "run"]);
  });

  test("unlike outcomes never fold together", () => {
    const rows = collapseRepeats([
      run({ id: 4, status: "ok" }),
      run({ id: 3, status: "failed", error: "x" }),
      run({ id: 2 }),
      run({ id: 1, status: "failed", error: "x" }),
    ]);
    expect(rows.map((r) => r.kind)).toEqual(["run", "run", "run", "run"]);
  });

  test("a lone quiet round stays a round — a group of one reads worse", () => {
    const rows = collapseRepeats([run({ id: 3, status: "ok" }), run({ id: 2 }), run({ id: 1, status: "ok" })]);
    expect(rows.map((r) => r.kind)).toEqual(["run", "run", "run"]);
  });

  test("a round that did something breaks the fold in two", () => {
    // This is the whole point of folding ADJACENT rounds only: the busy round
    // in the middle must not be swallowed, and the two quiet stretches around
    // it are two different stretches.
    const rows = collapseRepeats([
      run({ id: 6 }),
      run({ id: 5 }),
      run({ id: 4, status: "ok", published: { ...NO_COUNTS, added: 3 } }),
      run({ id: 3 }),
      run({ id: 2 }),
    ]);
    expect(rows.map((r) => r.kind)).toEqual(["run", "run", "run", "group"]);
    expect(rows[3].kind === "group" && rows[3].runs.map((r) => r.id)).toEqual([3, 2]);
  });

  test("every round survives the fold — nothing is dropped", () => {
    const runs = [run({ id: 4 }), run({ id: 3 }), run({ id: 2, status: "ok" }), run({ id: 1 })];
    const seen = collapseRepeats(runs).flatMap((r) =>
      r.kind === "run" ? [r.run.id] : r.runs.map((x) => x.id),
    );
    expect(seen).toEqual([4, 3, 2, 1]);
  });

  test("row ids are unique and stable", () => {
    const rows = collapseRepeats([run({ id: 3 }), run({ id: 2 }), run({ id: 1, status: "ok" })]);
    const ids = rows.map((r) => r.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(collapseRepeats([run({ id: 3 }), run({ id: 2 }), run({ id: 1, status: "ok" })])
      .map((r) => r.id)).toEqual(ids);
  });

  test("an empty history folds to nothing", () => {
    expect(collapseRepeats([])).toEqual([]);
  });
});

describe("groupSpan", () => {
  test("spans from the oldest member's start to the newest member's finish", () => {
    // The list is newest-first, so the span's ends come from opposite ends of it.
    const span = groupSpan([run({ id: 3 }), run({ id: 2 }), run({ id: 1 })]);
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
