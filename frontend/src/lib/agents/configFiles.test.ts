// src/lib/agents/configFiles.test.ts — the file-name helper.
import { describe, expect, test } from "vitest";

import { baseName } from "./configFiles";

describe("baseName", () => {
  test("keeps the last segment of a path", () => {
    expect(baseName("/home/u/.claude/settings.json")).toBe("settings.json");
    expect(baseName("/home/u/.claude/agents/")).toBe("agents");
  });
});
