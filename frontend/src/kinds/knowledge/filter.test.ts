// frontend/src/kinds/knowledge/filter.test.ts
//
// The lanes' filter is name-only and client-side: it matches a file's title or
// its on-disk basename, case-insensitively, and an empty box matches
// everything. It never looks at a document's body — that is retrieval, and
// retrieval belongs to the agents' `coffer__search`, not this page.

import { describe, expect, test } from "vitest";
import { matchesFilter } from "./filter";

describe("matchesFilter", () => {
  test("an empty (or whitespace) filter matches everything", () => {
    expect(matchesFilter("", "Deploys", "/a/deploys.md")).toBe(true);
    expect(matchesFilter("   ", "Deploys", "/a/deploys.md")).toBe(true);
  });

  test("matches the title case-insensitively as a substring", () => {
    expect(matchesFilter("plo", "Deploys", null)).toBe(true);
    expect(matchesFilter("DEPLOY", "Deploys", null)).toBe(true);
    expect(matchesFilter("runbook", "Deploys", null)).toBe(false);
  });

  test("matches the on-disk basename, not the rest of the path", () => {
    expect(matchesFilter("tabs-f1", "untitled", "/abs/notes/tabs-f1.md")).toBe(true);
    // A directory name in the path must not drag every file in it into the list.
    expect(matchesFilter("notes", "untitled", "/abs/notes/tabs-f1.md")).toBe(false);
  });

  test("tolerates a missing path", () => {
    expect(matchesFilter("x", "title", undefined)).toBe(false);
  });
});
