// frontend/src/lib/knowledge/lineDiff.test.ts — the two diff readers the Knowledge page renders.
import { describe, expect, test } from "vitest";

import { diffLines } from "./lineDiff";
import { parseUnifiedDiff } from "./unifiedDiff";

describe("diffLines", () => {
  test("aligns unchanged lines and marks what only one side has", () => {
    const rows = diffLines("a\nb\nc", "a\nB\nc\nd");
    expect(rows.map((r) => `${r.kind}:${r.text}`)).toEqual([
      "context:a",
      "del:b",
      "add:B",
      "context:c",
      "add:d",
    ]);
    expect(rows[3]).toMatchObject({ oldLine: 3, newLine: 3 });
  });

  test("identical texts are all context", () => {
    expect(diffLines("x\ny", "x\ny").every((r) => r.kind === "context")).toBe(true);
  });
});

describe("parseUnifiedDiff", () => {
  test("drops git headers, numbers both sides and keeps hunk headers", () => {
    const rows = parseUnifiedDiff(
      [
        "diff --git a/d.md b/d.md",
        "index 1..2 100644",
        "--- a/d.md",
        "+++ b/d.md",
        "@@ -6,3 +6,4 @@ ## Startup",
        " ## Startup",
        "-old line",
        "+new line",
        "+another",
        "\\ No newline at end of file",
      ].join("\n"),
    );
    expect(rows[0].kind).toBe("hunk");
    expect(rows.slice(1)).toEqual([
      { kind: "context", text: "## Startup", oldLine: 6, newLine: 6 },
      { kind: "del", text: "old line", oldLine: 7 },
      { kind: "add", text: "new line", newLine: 7 },
      { kind: "add", text: "another", newLine: 8 },
    ]);
  });

  test("an empty diff has no rows", () => {
    expect(parseUnifiedDiff("")).toEqual([]);
  });
});
