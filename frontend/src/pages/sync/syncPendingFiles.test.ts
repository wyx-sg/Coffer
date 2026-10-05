// frontend/src/pages/sync/syncPendingFiles.test.ts — one entry per waiting file.
import { describe, expect, test } from "vitest";

import { pendingFiles } from "./syncPendingFiles";

const commit = (time: string, writer: string, path: string, status: string) => ({
  version: time,
  time,
  writer,
  summary: "",
  changes: [{ path, status: status as "added" | "modified" | "removed" }],
});

describe("pendingFiles", () => {
  test("a file in several commits is one entry with the newest writer and the net mark", () => {
    const files = pendingFiles([
      commit("3", "agent", "a.md", "modified"),
      commit("2", "user", "a.md", "modified"),
      commit("1", "user", "a.md", "added"),
      commit("2", "user", "b.md", "removed"),
      commit("1", "user", "b.md", "modified"),
      commit("1", "disk", "c.md", "modified"),
    ]);
    expect(files).toEqual([
      { path: "a.md", status: "added", writer: "agent", time: "3" },
      { path: "b.md", status: "removed", writer: "user", time: "2" },
      { path: "c.md", status: "modified", writer: "disk", time: "1" },
    ]);
  });
});
