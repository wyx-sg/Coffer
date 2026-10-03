import { describe, expect, it } from "vitest";

import { specDiff } from "./specDiff";

describe("specDiff", () => {
  it("numbers both sides from where the new text starts and counts the changes", () => {
    const diff = specDiff('a\n"required": ["id"]\nc', 'a\n"required": ["id", "x"]\nc', 412);
    expect(diff.added).toBe(1);
    expect(diff.removed).toBe(1);
    expect(diff.lines[0]).toEqual({ kind: "hunk", text: "@@ -412,3 +412,3 @@" });
    const removed = diff.lines.find((l) => l.kind === "remove");
    expect(removed).toMatchObject({ oldNo: 413, newNo: undefined });
    expect(diff.lines.find((l) => l.kind === "add")).toMatchObject({ newNo: 413 });
  });

  it("keeps three lines of context around a change and drops the rest", () => {
    const old = Array.from({ length: 20 }, (_, i) => `l${i}`).join("\n");
    const next = old.replace("l10", "changed");
    const shown = specDiff(old, next, 1).lines.filter((l) => l.kind !== "hunk");
    expect(shown).toHaveLength(3 + 2 + 3);
  });

  it("has no hunk when nothing changed", () => {
    expect(specDiff("a", "a", 1).lines).toEqual([]);
  });
});
