// frontend/src/lib/scope.test.ts
//
// The scope helpers, mirroring backend/coffer/domain/scope.py. The rule with
// teeth is the evidence one: a verdict of "reaches nobody here" is drawn on the
// UI as a warning, so drawing it off an agent list that has not loaded yet
// would warn about a resource that is perfectly fine.
import { describe, expect, test } from "vitest";

import { isDormantHere, sameScope } from "./scope";

const here = ["claude", "codex"];

describe("sameScope", () => {
  test("null equals only null", () => {
    expect(sameScope(null, null)).toBe(true);
    expect(sameScope(null, { agents: [] })).toBe(false);
  });

  test("order does not matter", () => {
    expect(sameScope({ agents: ["a", "b"] }, { agents: ["b", "a"] })).toBe(true);
  });

  test("an unrestricted list is not an empty one", () => {
    expect(sameScope({ agents: null }, { agents: [] })).toBe(false);
  });

  test("different agents are a different scope", () => {
    expect(sameScope({ agents: ["claude"] }, { agents: ["codex"] })).toBe(false);
  });
});

describe("isDormantHere", () => {
  test("an unscoped resource is active", () => {
    expect(isDormantHere(null, here)).toBe(false);
  });

  test("a scope of every agent is active", () => {
    expect(isDormantHere({ agents: null }, here)).toBe(false);
  });

  test("a scope naming an agent registered here is active", () => {
    expect(isDormantHere({ agents: ["claude"] }, here)).toBe(false);
  });

  test("a scope naming nobody registered here is dormant", () => {
    expect(isDormantHere({ agents: ["ghost"] }, here)).toBe(true);
  });

  test("an empty list is dormant even before agents have loaded", () => {
    expect(isDormantHere({ agents: [] }, [])).toBe(true);
  });

  test("an agent list still in flight yields no verdict", () => {
    expect(isDormantHere({ agents: ["claude"] }, [])).toBe(false);
  });
});
