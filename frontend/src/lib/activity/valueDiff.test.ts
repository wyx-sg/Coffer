// src/lib/activity/valueDiff.test.ts — a change's before and after as a line diff.
import { expect, test } from "vitest";

import { diffCounts, diffValues } from "./valueDiff";

test("equal values have no diff", () => {
  expect(diffValues({ a: 1 }, { a: 1 })).toEqual([]);
});

test("a changed field is a removed and an added line with context around it", () => {
  const lines = diffValues(
    { a: 1, b: 2, c: 3, d: 4, url: "https://old", e: 5, f: 6, g: 7, h: 8 },
    { a: 1, b: 2, c: 3, d: 4, url: "https://new", e: 5, f: 6, g: 7, h: 8 },
  );
  expect(lines.find((l) => l.kind === "remove")?.text).toContain("https://old");
  expect(lines.find((l) => l.kind === "add")?.text).toContain("https://new");
  expect(diffCounts(lines)).toEqual({ added: 1, removed: 1 });
  // Unchanged lines far from the change are folded into a gap.
  expect(lines.some((l) => l.kind === "gap")).toBe(true);
});

test("a value that appears shows only added lines", () => {
  const lines = diffValues(null, { a: 1 });
  expect(diffCounts(lines).added).toBeGreaterThan(0);
});
