import { describe, expect, test } from "vitest";

import { parseUnifiedDiff } from "./unifiedDiff";

describe("parseUnifiedDiff", () => {
  test("numbers context, added and removed rows from the hunk header", () => {
    const diff = [
      "--- a/x.py",
      "+++ b/x.py",
      "@@ -140,3 +140,3 @@ class WsClient",
      " keep",
      "-old",
      "+new",
      " tail",
      "",
    ].join("\n");
    const [hunk] = parseUnifiedDiff(diff);
    expect(hunk.header).toBe("@@ -140,3 +140,3 @@ class WsClient");
    expect(hunk.rows).toEqual([
      { kind: "context", oldNo: 140, newNo: 140, text: "keep" },
      { kind: "del", oldNo: 141, newNo: null, text: "old" },
      { kind: "add", oldNo: null, newNo: 141, text: "new" },
      { kind: "context", oldNo: 142, newNo: 142, text: "tail" },
    ]);
  });

  test("reads several hunks", () => {
    const diff = ["@@ -1,1 +1,2 @@", " a", "+b", "@@ -9,1 +10,1 @@", "-c", "+d"].join("\n");
    const hunks = parseUnifiedDiff(diff);
    expect(hunks).toHaveLength(2);
    expect(hunks[1].rows[0]).toMatchObject({ kind: "del", oldNo: 9 });
    expect(hunks[1].rows[1]).toMatchObject({ kind: "add", newNo: 10 });
  });

  test("drops the no-newline marker and keeps an empty context line", () => {
    const diff = ["@@ -1,2 +1,2 @@", " ", "-a", "\\ No newline at end of file", "+b"].join("\n");
    const [hunk] = parseUnifiedDiff(diff);
    expect(hunk.rows.map((r) => r.kind)).toEqual(["context", "del", "add"]);
  });

  test("a new file is all added rows", () => {
    const [hunk] = parseUnifiedDiff("--- /dev/null\n+++ b/n.py\n@@ -0,0 +1,2 @@\n+a\n+b\n");
    expect(hunk.rows).toEqual([
      { kind: "add", oldNo: null, newNo: 1, text: "a" },
      { kind: "add", oldNo: null, newNo: 2, text: "b" },
    ]);
  });

  test("concatenated diffs of one path give their hunks in order", () => {
    const diff = [
      "--- a/f",
      "+++ b/f",
      "@@ -1,1 +1,1 @@",
      "-a",
      "+b",
      "--- a/f",
      "+++ b/f",
      "@@ -1,1 +1,1 @@",
      "-b",
      "+c",
    ].join("\n");
    const hunks = parseUnifiedDiff(diff);
    expect(hunks).toHaveLength(2);
    expect(hunks[1].rows.map((r) => r.text)).toEqual(["b", "c"]);
  });

  test("a removed line that looks like a file header is still a row", () => {
    const [hunk] = parseUnifiedDiff("@@ -1,2 +1,1 @@\n--- not a header\n x");
    expect(hunk.rows[0]).toEqual({ kind: "del", oldNo: 1, newNo: null, text: "-- not a header" });
  });
});
