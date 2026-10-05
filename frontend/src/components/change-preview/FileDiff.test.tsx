// src/components/change-preview/FileDiff.test.tsx — the one diff renderer: a long changed line wraps
// at a word with a ↳ on its continuation rows instead of being cut off.
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import { wrapLine } from "@/lib/diff/wrapLine";
import type { ChangeItem } from "@/lib/changePreview/changeCounts";
import { FileDiff } from "./FileDiff";

const LONG = "word ".repeat(40).trim();

const ITEM: ChangeItem = {
  id: "c1",
  agentType: "coffer",
  path: "skills/pdf/SKILL.md",
  op: "modify",
  added: 1,
  removed: 0,
  diff: [
    { kind: "hunk", text: "@@ −1,1 +1,2 @@" },
    { kind: "context", text: "# PDF", oldNo: 1, newNo: 1 },
    { kind: "add", text: LONG, newNo: 2 },
  ],
};

describe("FileDiff", () => {
  acceptance("web-ui", "a long changed line wraps instead of being cut off", () => {
    render(<FileDiff item={ITEM} />);

    const rows = Array.from(document.querySelectorAll('[data-line="add"]'));
    expect(rows.length).toBeGreaterThan(1);
    // The first row carries the line number and the sign; the rest are continuations.
    expect(rows[0]).not.toHaveAttribute("data-continuation");
    expect(rows[0]).toHaveTextContent("2");
    expect(rows[0]).toHaveTextContent("+");
    for (const row of rows.slice(1)) {
      expect(row).toHaveAttribute("data-continuation", "true");
      expect(row).toHaveTextContent("↳");
    }
    // Nothing was cut off: the pieces read back as the whole line.
    const text = rows.map((r) => r.lastElementChild?.textContent?.trim() ?? "").join(" ");
    expect(text).toBe(LONG);
    expect(screen.getByText("skills/pdf/SKILL.md")).toBeInTheDocument();
  });

  test("wrapLine breaks at a word with an indented continuation", () => {
    const rows = wrapLine(LONG, 40);
    expect(rows.length).toBeGreaterThan(1);
    expect(rows.every((r) => r.length <= 40)).toBe(true);
    expect(rows[1].startsWith("  ")).toBe(true);
    expect(rows.map((r) => r.trim()).join(" ")).toBe(LONG);
    expect(wrapLine("short")).toEqual(["short"]);
  });
});
