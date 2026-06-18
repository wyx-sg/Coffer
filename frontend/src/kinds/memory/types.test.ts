// frontend/src/kinds/memory/types.test.ts
//
// Unit tests for the memory wire-type helpers. `projectDirName` backs the
// human-readable project identity (spec 007 FR-017a): a per-project store is
// shown by its root directory's basename instead of the opaque project-<ULID>.

import { describe, expect, test } from "vitest";
import { projectDirName } from "./types";

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
