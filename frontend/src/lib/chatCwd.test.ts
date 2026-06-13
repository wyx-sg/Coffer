import { afterEach, describe, expect, it } from "vitest";

import { getRecentCwds, lastCwd, pushRecentCwd } from "./chatCwd";

afterEach(() => localStorage.clear());

describe("chatCwd", () => {
  it("starts empty", () => {
    expect(getRecentCwds()).toEqual([]);
    expect(lastCwd()).toBeNull();
  });

  it("records the most-recently-used directory first", () => {
    pushRecentCwd("/a");
    pushRecentCwd("/b");
    expect(getRecentCwds()).toEqual(["/b", "/a"]);
    expect(lastCwd()).toBe("/b");
  });

  it("de-duplicates by moving an existing path to the front", () => {
    pushRecentCwd("/a");
    pushRecentCwd("/b");
    pushRecentCwd("/a");
    expect(getRecentCwds()).toEqual(["/a", "/b"]);
  });

  it("ignores blank paths and trims", () => {
    pushRecentCwd("  ");
    pushRecentCwd("  /work  ");
    expect(getRecentCwds()).toEqual(["/work"]);
  });

  it("caps the list length", () => {
    for (let i = 0; i < 12; i++) pushRecentCwd(`/dir-${i}`);
    expect(getRecentCwds().length).toBe(8);
    expect(getRecentCwds()[0]).toBe("/dir-11");
  });
});
