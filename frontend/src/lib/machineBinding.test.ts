// frontend/src/lib/machineBinding.test.ts
//
// The two rules every surface that names a machine shares: which of the four
// things a stored id is, and what a picker may offer for it. Tested here
// rather than only through the components that use them, because the cases
// that matter are the ones a rendered surface makes hardest to set up — a
// vault with no registry, and a binding nobody claims.
import { describe, expect, test } from "vitest";

import { bindingState, machineOptionFor, machineOptions } from "./machineBinding";
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

  test("this machine's id decides before the registry is consulted", () => {
    expect(bindingState(HERE, { selfId: HERE, known: KNOWN })).toBe("self");
    expect(bindingState(THERE, { selfId: HERE, known: KNOWN })).toBe("other");
  });

  test("an empty registry is not a fault for this machine's own id", () => {
    // The single-machine install: it has never converged, so it has no
    // registry to be absent from, and it cannot be wrong about itself.
    expect(bindingState(HERE, { selfId: HERE, known: [] })).toBe("self");
  });

  test("an empty registry is not a fault for anyone else's id either", () => {
    // "unknown" claims that nobody claims this id. A registry with machines in
    // it can show that; an empty one has shown nothing, and there is none
    // until a remote is configured or for a moment after the tree is rebuilt.
    // Saying "runs somewhere else" from "we cannot say" is the harmless half
    // of a guess we have to make either way.
    expect(bindingState(THERE, { selfId: HERE, known: [] })).toBe("other");
    expect(bindingState("machine-gone", { selfId: HERE, known: [] })).toBe("other");
  });

  test("an id nobody claims is its own state, not 'somewhere else'", () => {
    // "Somewhere else" is fine; this one happens NOWHERE and only a rebind
    // fixes it, so the two must never collapse into one reading.
    expect(bindingState("machine-gone", { selfId: HERE, known: KNOWN })).toBe("unknown");
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
    // machine sorts first, which is not what the binding says.
    const options = machineOptions(REGISTRY, HERE, "machine-gone");
    expect(options.at(-1)).toEqual({ id: "machine-gone", name: "", isSelf: false, known: false });
  });

  test("adds nothing when the registry already carries both", () => {
    expect(machineOptions(REGISTRY, HERE, THERE)).toHaveLength(2);
  });
});

describe("machineOptionFor", () => {
  test("resolves a stored id to the registry entry that claims it", () => {
    expect(machineOptionFor(REGISTRY, HERE, THERE)).toEqual({
      id: THERE,
      name: "Desktop",
      isSelf: false,
      known: true,
    });
  });

  test("marks this machine as this machine on a vault with no registry", () => {
    // A surface that only reports the binding must resolve it exactly as the
    // picker would, or the two read differently on the same vault.
    expect(machineOptionFor([], HERE, HERE)).toEqual({
      id: HERE,
      name: "",
      isSelf: true,
      known: true,
    });
  });

  test("reports an id nobody claims as unknown rather than inventing a name", () => {
    expect(machineOptionFor(REGISTRY, HERE, "machine-gone")).toEqual({
      id: "machine-gone",
      name: "",
      isSelf: false,
      known: false,
    });
  });
});
