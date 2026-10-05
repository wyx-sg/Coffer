// frontend/src/lib/knowledge/lineDiff.test.ts — the line diff skill and custom-tool reviews draw.
import { describe, expect, test } from "vitest";

import { diffLines } from "./lineDiff";

describe("diffLines", () => {
  test("aligns unchanged lines and marks what only one side has", () => {
    const rows = diffLines("a\nb\nc", "a\nB\nc\nd");
    expect(rows.map((r) => `${r.kind}:${r.text}`)).toEqual([
      "context:a",
      "remove:b",
      "add:B",
      "context:c",
      "add:d",
    ]);
    expect(rows[3]).toMatchObject({ oldNo: 3, newNo: 3 });
  });

  test("identical texts are all context", () => {
    expect(diffLines("x\ny", "x\ny").every((r) => r.kind === "context")).toBe(true);
  });
});
