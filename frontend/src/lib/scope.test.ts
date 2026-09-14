// frontend/src/lib/scope.test.ts
//
// The two-axis scope helpers, mirroring backend/coffer/domain/scope.py. The
// axis-precedence rule is the one with teeth: the API reports the machine axis
// first, and a UI that reported the agent axis instead would send the user
// looking for the wrong thing.
import { describe, expect, test } from "vitest";

import { excludedAxis, sameScope } from "./scope";

const HERE = "a3f21c9e4b7d2610";
const THERE = "bb11cc22dd33ee44";
const here = { machineId: HERE, agents: ["claude", "codex"] };

describe("sameScope", () => {
  test("null equals only null", () => {
    expect(sameScope(null, null)).toBe(true);
    expect(sameScope(null, { agents: [], machines: null })).toBe(false);
  });

  test("order within an axis does not matter", () => {
    expect(
      sameScope({ agents: ["a", "b"], machines: null }, { agents: ["b", "a"], machines: null }),
    ).toBe(true);
  });

  test("an unrestricted axis is not an empty one", () => {
    expect(sameScope({ agents: null, machines: null }, { agents: [], machines: null })).toBe(false);
  });

  test("the machine axis is compared too", () => {
    expect(sameScope({ agents: null, machines: [HERE] }, { agents: null, machines: [THERE] })).toBe(
      false,
    );
  });
});

describe("excludedAxis", () => {
  test("an unscoped resource is active everywhere", () => {
    expect(excludedAxis(null, here)).toBeNull();
  });

  test("a machine axis naming this machine excludes nothing", () => {
    expect(excludedAxis({ agents: null, machines: [HERE] }, here)).toBeNull();
  });

  test("a machine axis naming another machine excludes on the machine axis", () => {
    expect(excludedAxis({ agents: null, machines: [THERE] }, here)).toBe("machine");
  });

  test("an agent axis naming nobody registered here excludes on the agent axis", () => {
    expect(excludedAxis({ agents: ["ghost"], machines: null }, here)).toBe("agent");
  });

  test("an empty agent axis is dormant even before agents have loaded", () => {
    expect(excludedAxis({ agents: [], machines: null }, { machineId: HERE, agents: [] })).toBe(
      "agent",
    );
  });

  test("the machine axis is reported in preference to the agent axis", () => {
    expect(excludedAxis({ agents: ["ghost"], machines: [THERE] }, here)).toBe("machine");
  });

  test("an unknown local machine id yields no verdict rather than a wrong one", () => {
    expect(excludedAxis({ agents: null, machines: [THERE] }, { machineId: null, agents: [] })).toBe(
      null,
    );
  });

  test("an agent list still in flight yields no verdict", () => {
    expect(
      excludedAxis({ agents: ["claude"], machines: null }, { machineId: HERE, agents: [] }),
    ).toBeNull();
  });
});
