// frontend/src/lib/knowledge/titleHeading.test.ts — the reader shows one title, never two.
import { describe, expect, test } from "vitest";

import { splitTitleHeading } from "@/lib/knowledge/titleHeading";

describe("splitTitleHeading", () => {
  test("a body opening with the title's own heading drops it", () => {
    expect(splitTitleHeading("# Gateway\n\nText.\n", "Gateway")).toEqual({
      title: "Gateway",
      body: "Text.\n",
    });
  });

  test("a leading heading that differs from the title is shown in its place", () => {
    expect(
      splitTitleHeading("\n# Consent — read layer, no database\n\nText.\n", "Consent — read layer"),
    ).toEqual({ title: "Consent — read layer, no database", body: "Text.\n" });
  });

  test("a body that does not open with a level-1 heading keeps the title", () => {
    expect(splitTitleHeading("Intro.\n\n# Later\n", "Doc")).toEqual({
      title: "Doc",
      body: "Intro.\n\n# Later\n",
    });
    expect(splitTitleHeading("## Section\n\nText.\n", "Doc").title).toBe("Doc");
  });
});
