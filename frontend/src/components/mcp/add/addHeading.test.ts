// The Add dialog's heading on a partly-added review: "Rename" only for a name clash.
import { describe, expect, test } from "vitest";

import { headingOf } from "./addHeading";

// Echo the key and its interpolated tail so the test sees which one was chosen.
const t = ((key: string, o?: Record<string, unknown>) =>
  key === "mcp.add.partialSub" ? String(o?.tail) : key) as never;

const created = new Map([["ok", "u1"]]);

describe("headingOf (partly added review)", () => {
  test("a name clash asks for a rename", () => {
    const h = headingOf(t, "en", { kind: "review" }, created, [
      { name: "dup", message: "taken", nameTaken: true },
    ]);
    expect(h.sub).toBe("mcp.add.renameTail");
  });

  test("any other refusal points at the card instead of asking for a rename", () => {
    const h = headingOf(t, "en", { kind: "review" }, created, [
      { name: "bad", message: "no", nameTaken: false },
    ]);
    expect(h.sub).toBe("mcp.add.failedTail");
  });
});
