// frontend/src/kinds/channel/channelBinding.test.ts
//
// The two rules the row cell and the detail card share (spec channels, "Where
// a channel runs"): which of the four things a binding is, and what a picker
// may bind to. Both are tested here rather than only through the components,
// because the cases that matter are the ones a rendered surface makes hardest
// to set up — a vault with no registry, and a binding nobody claims.
import { describe, expect, test } from "vitest";

import { bindingState, machineOptions } from "./channelBinding";
import type { Machine } from "@/lib/api/sync";

const HERE = "machine-here";
const THERE = "machine-there";

function machine(id: string, name: string, isSelf = false): Machine {
  return {
    machine_id: id,
    name,
    os: "darwin",
    hostname: name,
    coffer_version: "0.5.0",
    last_converged_on: null,
    key_matches: true,
    agents: [],
    is_self: isSelf,
  };
}

const REGISTRY = [machine(HERE, "Laptop", true), machine(THERE, "Desktop")];
const KNOWN = REGISTRY.map((m) => m.machine_id);

describe("bindingState", () => {
  test("no binding is unbound, whatever the registry says", () => {
    expect(bindingState(null, { selfId: HERE, known: KNOWN })).toBe("unbound");
  });

  test("the daemon's runs_here outranks comparing ids here", () => {
    // A vault that has never converged has no registry and may have no id to
    // compare against, and the daemon still knows the channel is its to run.
    expect(bindingState("anything", { selfId: null, known: [], runsHere: true })).toBe("self");
  });

  test("without a status, this machine's id decides", () => {
    expect(bindingState(HERE, { selfId: HERE, known: KNOWN })).toBe("self");
    expect(bindingState(THERE, { selfId: HERE, known: KNOWN })).toBe("other");
  });

  test("a binding nobody claims is its own state, not 'somewhere else'", () => {
    // "Somewhere else" is fine; this one runs NOWHERE and only a rebind fixes
    // it, so the two must never collapse into one reading.
    expect(bindingState("machine-gone", { selfId: HERE, known: KNOWN, runsHere: false })).toBe(
      "unknown",
    );
  });
});

describe("machineOptions", () => {
  test("offers the registry as it stands", () => {
    expect(machineOptions(REGISTRY, HERE, HERE).map((o) => [o.id, o.name, o.isSelf])).toEqual([
      [HERE, "Laptop", true],
      [THERE, "Desktop", false],
    ]);
  });

  test("offers this machine even with an empty registry", () => {
    // The single-machine install: it has never converged, so it has no
    // registry at all, and an empty pick-list would leave it unable to bind.
    expect(machineOptions([], HERE, null)).toEqual([
      { id: HERE, name: "", isSelf: true, known: true },
    ]);
  });

  test("keeps an unclaimed binding in the list, marked as unknown", () => {
    // Dropping it would leave the trigger blank — or worse, showing whichever
    // machine sorts first, which is not what the channel says.
    const options = machineOptions(REGISTRY, HERE, "machine-gone");
    expect(options.at(-1)).toEqual({ id: "machine-gone", name: "", isSelf: false, known: false });
  });

  test("adds nothing when the registry already carries both", () => {
    expect(machineOptions(REGISTRY, HERE, THERE)).toHaveLength(2);
  });
});
