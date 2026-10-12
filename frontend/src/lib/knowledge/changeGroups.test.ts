// frontend/src/lib/knowledge/changeGroups.test.ts — how the Change log groups its rows.
import { describe, expect, test } from "vitest";

import { change } from "@/components/knowledge/knowledgeTestData";

import { groupChanges, groupDocuments } from "./changeGroups";

const at = (minutes: number) => new Date(Date.UTC(2026, 9, 12, 12, minutes)).toISOString();
const disk = (version: string, minutes: number, path: string) =>
  change({
    version,
    writer: "disk",
    operation: "edit",
    time: at(minutes),
    documents: [{ path, status: "modified", added: 1, removed: 1 }],
  });

describe("groupChanges", () => {
  test("edits on disk within ten minutes of the one before are one entry", () => {
    const groups = groupChanges([
      disk("c", 30, "a.md"),
      disk("b", 22, "b.md"),
      disk("a", 13, "a.md"),
      disk("z", 0, "c.md"),
    ]);
    expect(groups.map((g) => (g.kind === "disk" ? g.changes.map((c) => c.version) : []))).toEqual([
      ["c", "b", "a"],
      ["z"],
    ]);
  });

  test("any other change breaks a run and stands alone", () => {
    const tidy = change({ version: "t", writer: "agent", operation: "tidy", time: at(20) });
    const groups = groupChanges([disk("b", 25, "a.md"), tidy, disk("a", 15, "a.md")]);
    expect(groups.map((g) => g.kind)).toEqual(["disk", "one", "disk"]);
  });
});

describe("groupDocuments", () => {
  test("lists each file once with its lines summed", () => {
    expect(
      groupDocuments([disk("b", 2, "a.md"), disk("a", 1, "a.md"), disk("z", 0, "b.md")]),
    ).toEqual([
      { path: "a.md", added: 2, removed: 2 },
      { path: "b.md", added: 1, removed: 1 },
    ]);
  });
});
