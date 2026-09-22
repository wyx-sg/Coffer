// frontend/src/components/channel/channelBinding.test.ts
//
// The rule that is the channel's own (spec channels, "Where a channel runs"):
// the daemon's `runs_here` outranks anything this code could work out for
// itself. The four states and the pick-list they share with the curation owner
// are tested in `src/lib/machineBinding.test.ts`; what is left here is only
// what `runs_here` changes, plus proof that it does not change the rest.
import { describe, expect, test } from "vitest";

import { bindingState } from "./channelBinding";

const HERE = "machine-here";
const THERE = "machine-there";
const KNOWN = [HERE, THERE];

describe("bindingState", () => {
  test("the daemon's runs_here outranks comparing ids here", () => {
    // A vault that has never converged has no registry and may have no id to
    // compare against, and the daemon still knows the channel is its to run.
    expect(bindingState("anything", { selfId: null, known: [], runsHere: true })).toBe("self");
  });

  test("without a status, this machine's id decides", () => {
    expect(bindingState(HERE, { selfId: HERE, known: KNOWN })).toBe("self");
    expect(bindingState(THERE, { selfId: HERE, known: KNOWN })).toBe("other");
  });

  test("no binding is unbound even when the daemon says it runs here", () => {
    // Nothing to run: "unbound" is the channel's fail-closed state and no
    // status may talk it into looking healthy.
    expect(bindingState(null, { selfId: HERE, known: KNOWN, runsHere: true })).toBe("unbound");
  });

  test("a binding nobody claims is its own state, not 'somewhere else'", () => {
    // "Somewhere else" is fine; this one runs NOWHERE and only a rebind fixes
    // it, so the two must never collapse into one reading.
    expect(bindingState("machine-gone", { selfId: HERE, known: KNOWN, runsHere: false })).toBe(
      "unknown",
    );
  });

  test("a daemon that says no still lets the registry answer where it runs", () => {
    // runs_here: false is only "not mine"; which machine it IS bound to is
    // still the registry's to answer.
    expect(bindingState(THERE, { selfId: HERE, known: KNOWN, runsHere: false })).toBe("other");
  });
});
