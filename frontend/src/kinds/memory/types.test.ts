// frontend/src/kinds/memory/types.test.ts
//
// Unit tests for the memory wire-type helpers. `projectDirName` backs the
// human-readable project identity (spec 007 FR-017a): a per-project store is
// shown by its root directory's basename instead of the opaque project-<ULID>.

import { describe, expect, test } from "vitest";
import { projectDirName, storeDisplayName } from "./types";

describe("projectDirName", () => {
  test("returns the basename of a POSIX path", () => {
    expect(projectDirName("/Users/me/code/coffer")).toBe("coffer");
  });

  test("ignores trailing slashes", () => {
    expect(projectDirName("/Users/me/code/coffer/")).toBe("coffer");
    expect(projectDirName("/Users/me/code/coffer///")).toBe("coffer");
  });

  test("handles Windows separators", () => {
    expect(projectDirName("C:\\Users\\me\\coffer")).toBe("coffer");
    expect(projectDirName("C:\\Users\\me\\coffer\\")).toBe("coffer");
  });

  test("returns null when the root is unknown", () => {
    expect(projectDirName(null)).toBeNull();
    expect(projectDirName(undefined)).toBeNull();
    expect(projectDirName("")).toBeNull();
  });

  test("returns null for a root that is only separators", () => {
    expect(projectDirName("/")).toBeNull();
    expect(projectDirName("\\\\")).toBeNull();
  });
});

describe("storeDisplayName", () => {
  const project = { scope: "project" as const, name: "project-2K8S7KVJ0SJEZX0P0KSXWAN0KZ" };

  test("a user-set label wins over the derived basename (FR-017c)", () => {
    expect(
      storeDisplayName({ ...project, label: "My notes", project_root: "/Users/me/code/coffer" }),
    ).toBe("My notes");
  });

  test("falls back to the project_root basename when there is no label (FR-017a)", () => {
    expect(
      storeDisplayName({ ...project, label: null, project_root: "/Users/me/code/coffer" }),
    ).toBe("coffer");
    // An empty / whitespace-free label is treated as no label.
    expect(storeDisplayName({ ...project, label: "", project_root: "/Users/me/code/coffer" })).toBe(
      "coffer",
    );
  });

  test("the global store reads as its own name", () => {
    expect(
      storeDisplayName({ scope: "global", name: "global", label: null, project_root: null }),
    ).toBe("global");
  });

  test("an orphan project store (no label, no known root) returns null for a graceful placeholder", () => {
    expect(storeDisplayName({ ...project, label: null, project_root: null })).toBeNull();
    expect(storeDisplayName({ ...project, label: null })).toBeNull();
  });
});
