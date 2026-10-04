// frontend/src/components/skills/textDiff.test.ts — two texts as a change preview's diff, and a diff read backwards.
import { describe, expect, test } from "vitest";

import { reverseDiffLines } from "./reverseDiff";
import { textChangeItem, textDiff } from "./textDiff";

const lines = (n: number, edit?: [number, string]) =>
  Array.from({ length: n }, (_, i) => (edit && i + 1 === edit[0] ? edit[1] : `line ${i + 1}`)).join(
    "\n",
  );

describe("textDiff", () => {
  test("keeps three lines of context around an edit under one hunk header", () => {
    const d = textDiff(lines(20), lines(20, [10, "line ten, edited"]));
    expect(d.added).toBe(1);
    expect(d.removed).toBe(1);
    const hunks = d.lines.filter((l) => l.kind === "hunk");
    expect(hunks).toHaveLength(1);
    expect(hunks[0].text).toBe("@@ −7,7 +7,7 @@");
    // 3 context, the pair, 3 context — the rest of the file is not shown.
    expect(d.lines.filter((l) => l.kind === "context")).toHaveLength(6);
    expect(d.lines.find((l) => l.kind === "remove")).toMatchObject({ text: "line 10", oldNo: 10 });
    expect(d.lines.find((l) => l.kind === "add")).toMatchObject({
      text: "line ten, edited",
      newNo: 10,
    });
  });

  test("two edits far apart are two hunks", () => {
    const after = lines(30, [3, "a"]).split("\n");
    after[25] = "b";
    const d = textDiff(lines(30), after.join("\n"));
    expect(d.lines.filter((l) => l.kind === "hunk")).toHaveLength(2);
  });

  test("identical texts have no lines", () => {
    expect(textDiff("a\nb", "a\nb")).toEqual({ lines: [], added: 0, removed: 0 });
  });

  test("a text change becomes a Coffer item with its counts", () => {
    const item = textChangeItem("f", "demo/SKILL.md", "a", "b");
    expect(item).toMatchObject({ agentType: "coffer", op: "modify", added: 1, removed: 1 });
  });
});

describe("reverseDiffLines", () => {
  test("swaps added and removed lines, their numbers and the hunk's ranges", () => {
    const back = reverseDiffLines([
      { kind: "hunk", text: "@@ -12,4 +12,5 @@ Workflow" },
      { kind: "context", text: "keep", oldNo: 12, newNo: 12 },
      { kind: "remove", text: "gone", oldNo: 13 },
      { kind: "add", text: "new", newNo: 13 },
    ]);
    expect(back).toEqual([
      { kind: "hunk", text: "@@ −12,5 +12,4 @@ Workflow" },
      { kind: "context", text: "keep", oldNo: 12, newNo: 12 },
      { kind: "add", text: "gone", oldNo: undefined, newNo: 13 },
      { kind: "remove", text: "new", oldNo: 13, newNo: undefined },
    ]);
  });
});
