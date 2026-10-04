import { describe, expect, test } from "vitest";

import type { SyncRound } from "@/lib/api/sync";
import { collapseRepeats, groupSpan, isQuiet } from "./syncRunRows";
import { canRollBack } from "./syncRowActions";
import { makeRound } from "./syncTestKit";
import { acceptance } from "@/test/acceptance";

const ADDED = [{ path: "knowledge/a.md", status: "added" as const }];

function run(over: Partial<SyncRound> & { id: number | null }): SyncRound {
  return makeRound({
    started_at: `2026-09-16T0${over.id}:00:00Z`,
    finished_at: `2026-09-16T0${over.id}:00:05Z`,
    ...over,
  });
}

const ids = (rows: ReturnType<typeof collapseRepeats>, at: number) => {
  const row = rows[at];
  return row.kind === "group" ? row.runs.map((r) => r.id) : [row.run.id];
};

describe("isQuiet", () => {
  test("a round that found nothing to do and said nothing is quiet", () => {
    expect(isQuiet(run({ id: 1 }))).toBe(true);
  });

  test.each([
    ["a pulled commit", { pulled: [{ version: "abc", time: "t", machine: "m", files: 1 }] }],
    ["an applied file", { applied: ADDED }],
    ["a pushed file", { pushed: ADDED }],
    ["a detail", { detail: "fetch was slow" }],
  ])("a nothing_to_do round with %s is not quiet", (_label, over) => {
    expect(isQuiet(run({ ...(over as Partial<SyncRound>), id: 1 }))).toBe(false);
  });
});

describe("collapseRepeats", () => {
  test("consecutive quiet rounds become one row, bar the newest", () => {
    const rows = collapseRepeats([run({ id: 5 }), run({ id: 4 }), run({ id: 3 })]);
    // The newest round is the present: it stands alone so a reader sees the
    // state the vault is actually in.
    expect(rows.map((r) => r.kind)).toEqual(["run", "group"]);
    expect(ids(rows, 1)).toEqual([4, 3]);
  });

  acceptance(
    "vault-sync",
    "repeated failures fold into one row and the newest round stands alone",
    () => {
      const rows = collapseRepeats([
        run({ id: 9, status: "auth_failed", detail: "HTTP 403" }),
        run({ id: 8, status: "auth_failed", detail: "HTTP 403" }),
        run({ id: 7, status: "auth_failed", detail: "HTTP 403" }),
        run({ id: 6, status: "pushed", pushed: ADDED, pushed_files: 1 }),
      ]);
      expect(rows.map((r) => r.kind)).toEqual(["run", "group", "run"]);
      expect(ids(rows, 0)).toEqual([9]);
      expect(rows[1].kind === "group" && rows[1].status).toBe("auth_failed");
      expect(rows[1].kind === "group" && groupSpan(rows[1].runs).count).toBe(2);
      expect(ids(rows, 1)).toEqual([8, 7]);
      expect(ids(rows, 2)).toEqual([6]);

      // Held rounds fold by outcome the same way beneath a newer round.
      const held = collapseRepeats([
        run({ id: 4, status: "pulled" }),
        run({ id: 3, status: "held" }),
        run({ id: 2, status: "held" }),
      ]);
      expect(held.map((r) => r.kind)).toEqual(["run", "group"]);
      expect(ids(held, 1)).toEqual([3, 2]);
    },
  );

  test("rounds that moved files never fold, however many in a row", () => {
    const rows = collapseRepeats([
      run({ id: 4, status: "pulled", applied: ADDED }),
      run({ id: 3, status: "pulled", applied: ADDED }),
      run({ id: 2, status: "pulled", applied: ADDED }),
    ]);
    expect(rows.map((r) => r.kind)).toEqual(["run", "run", "run"]);
  });

  test("unlike outcomes never fold together", () => {
    const rows = collapseRepeats([
      run({ id: 4, status: "pushed" }),
      run({ id: 3, status: "failed", detail: "x" }),
      run({ id: 2 }),
      run({ id: 1, status: "failed", detail: "x" }),
    ]);
    expect(rows.map((r) => r.kind)).toEqual(["run", "run", "run", "run"]);
  });

  test("a round that did something breaks the fold in two", () => {
    const rows = collapseRepeats([
      run({ id: 6 }),
      run({ id: 5 }),
      run({ id: 4, status: "pushed", pushed: ADDED }),
      run({ id: 3 }),
      run({ id: 2 }),
    ]);
    expect(rows.map((r) => r.kind)).toEqual(["run", "run", "run", "group"]);
    expect(ids(rows, 3)).toEqual([3, 2]);
  });

  test("every round survives the fold, and row ids are unique", () => {
    const runs = [run({ id: 4 }), run({ id: 3 }), run({ id: 2, status: "pulled" }), run({ id: 1 })];
    const rows = collapseRepeats(runs);
    expect(rows.flatMap((_, i) => ids(rows, i))).toEqual([4, 3, 2, 1]);
    const keys = rows.map((r) => r.id);
    expect(new Set(keys).size).toBe(keys.length);
  });

  test("an empty history folds to nothing", () => {
    expect(collapseRepeats([])).toEqual([]);
  });
});

describe("groupSpan", () => {
  test("spans from the oldest member's start to the newest member's finish", () => {
    const span = groupSpan([run({ id: 3 }), run({ id: 2 }), run({ id: 1 })]);
    expect(span).toEqual({ from: "2026-09-16T01:00:00Z", to: "2026-09-16T03:00:05Z", count: 3 });
  });
});

describe("canRollBack", () => {
  test("a stored round with a snapshot that changed files here can be rolled back", () => {
    expect(canRollBack(run({ id: 1, snapshot: "sync/pre/1", applied: ADDED }))).toBe(true);
  });

  test.each([
    ["no snapshot", { snapshot: null, applied: ADDED }],
    ["nothing applied here", { snapshot: "sync/pre/1", applied: [] }],
    ["no stored id", { id: null, snapshot: "sync/pre/1", applied: ADDED }],
  ])("a round with %s cannot", (_label, over) => {
    expect(canRollBack(run({ id: 1, ...(over as Partial<SyncRound>) } as SyncRound))).toBe(false);
  });
});
