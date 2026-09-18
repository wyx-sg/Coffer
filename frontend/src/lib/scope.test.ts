// frontend/src/lib/scope.test.ts
//
// The scope helpers, mirroring backend/coffer/domain/scope.py. The rule with
// teeth is the evidence one: a verdict of "reaches nobody here" is drawn on the
// UI as a warning, so drawing it off an agent list that has not loaded yet
// would warn about a resource that is perfectly fine.
//
// Both sides of every comparison here are agent UIDS — what a scope stores and
// what an agent resource carries. The fixtures spell uids that are nothing like
// the names those agents go by on purpose: a fixture whose uid IS its name
// would let a helper comparing the wrong field pass every test in this file.
import { describe, expect, test } from "vitest";

import { isDormantHere, sameScope } from "./scope";

/** Two agents registered on this machine, as their uids. They answer to
 *  "claude" and "codex", which is what the user reads — and which nothing in
 *  this module ever looks at. */
const CLAUDE = "u-agent-7f21";
const CODEX = "u-agent-be04";
const GHOST = "u-agent-0000";

const here = [CLAUDE, CODEX];

describe("sameScope", () => {
  test("null equals only null", () => {
    expect(sameScope(null, null)).toBe(true);
    expect(sameScope(null, { agents: [] })).toBe(false);
  });

  test("order does not matter", () => {
    expect(sameScope({ agents: [CLAUDE, CODEX] }, { agents: [CODEX, CLAUDE] })).toBe(true);
  });

  test("an unrestricted list is not an empty one", () => {
    expect(sameScope({ agents: null }, { agents: [] })).toBe(false);
  });

  test("different agents are a different scope", () => {
    expect(sameScope({ agents: [CLAUDE] }, { agents: [CODEX] })).toBe(false);
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
    expect(isDormantHere({ agents: [CLAUDE] }, here)).toBe(false);
  });

  test("a scope naming nobody registered here is dormant", () => {
    expect(isDormantHere({ agents: [GHOST] }, here)).toBe(true);
  });

  test("an empty list is dormant even before agents have loaded", () => {
    expect(isDormantHere({ agents: [] }, [])).toBe(true);
  });

  test("an agent list still in flight yields no verdict", () => {
    expect(isDormantHere({ agents: [CLAUDE] }, [])).toBe(false);
  });
});
