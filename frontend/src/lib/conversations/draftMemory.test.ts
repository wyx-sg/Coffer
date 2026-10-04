import { beforeEach, describe, expect, test } from "vitest";

import {
  MAX_RECENT_DIRS,
  defaultDraftAgent,
  readLastWorkingDir,
  readRecentWorkingDirs,
  rememberAgent,
  rememberWorkingDir,
} from "./draftMemory";

const agent = (key: string, available = true) => ({
  agent_key: key,
  display_name: key,
  available,
});

beforeEach(() => localStorage.clear());

describe("recent folders", () => {
  test("most recent first, distinct, capped", () => {
    for (let i = 0; i < MAX_RECENT_DIRS + 3; i += 1) rememberWorkingDir(`/d/${i}`);
    rememberWorkingDir("/d/5");
    const dirs = readRecentWorkingDirs();
    expect(dirs).toHaveLength(MAX_RECENT_DIRS);
    expect(dirs[0]).toBe("/d/5");
    expect(new Set(dirs).size).toBe(dirs.length);
    expect(readLastWorkingDir()).toBe("/d/5");
  });

  test("Coffer's workspace becomes the default but is not listed", () => {
    rememberWorkingDir("/d/1");
    rememberWorkingDir(null);
    expect(readLastWorkingDir()).toBeNull();
    expect(readRecentWorkingDirs()).toEqual(["/d/1"]);
  });

  test("blocked or corrupt storage leaves the defaults", () => {
    localStorage.setItem("coffer.conversations.recentWorkingDirs", "{not json");
    expect(readRecentWorkingDirs()).toEqual([]);
  });
});

describe("defaultDraftAgent", () => {
  test("the last agent used while it can still run, else the first that can", () => {
    const agents = [agent("claude_code"), agent("codex")];
    expect(defaultDraftAgent(agents)).toBe("claude_code");
    rememberAgent("codex");
    expect(defaultDraftAgent(agents)).toBe("codex");
    expect(defaultDraftAgent([agent("claude_code"), agent("codex", false)])).toBe("claude_code");
    expect(defaultDraftAgent([agent("codex", false)])).toBe("");
  });
});
