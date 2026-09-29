// src/lib/agents/configFiles.test.ts — the JSON draft check and the file-name helper.
import { describe, expect, test } from "vitest";

import { baseName, checkJson } from "./configFiles";

describe("checkJson", () => {
  test("a draft that parses is valid", () => {
    expect(checkJson('{"a": 1}')).toEqual({ ok: true });
  });

  test("a missing comma is placed on its line and column", () => {
    const draft = '{\n  "a": 1\n  "b": 2\n}';
    const result = checkJson(draft);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.line).toBe(3);
      expect(result.column).toBeGreaterThan(0);
    }
  });

  test("an empty draft is invalid at its end", () => {
    expect(checkJson("")).toEqual({ ok: false, line: 1, column: 1 });
  });
});

describe("baseName", () => {
  test("keeps the last segment of a path", () => {
    expect(baseName("/home/u/.claude/settings.json")).toBe("settings.json");
    expect(baseName("/home/u/.claude/agents/")).toBe("agents");
  });
});
