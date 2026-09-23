// What the sidebar's Sync dot is keyed on.
//
// The marker is the whole design: it decides whether "I have seen this" keeps
// holding after the next hourly round, and getting it wrong turns the dot
// into either a nag or a thing that only ever appears once.
import { describe, expect, test } from "vitest";
import { attentionMarker } from "./useSyncAttention";
import type { ConvergeRound } from "@/lib/api/sync";

const NO_COUNTS = { added: 0, modified: 0, deleted: 0, changes: [] };

function round(over: Partial<ConvergeRound> = {}): ConvergeRound {
  return {
    status: "ok",
    join: null,
    applied: NO_COUNTS,
    published: NO_COUNTS,
    commit: null,
    conflicts: [],
    agent_resolved: [],
    failures: [],
    locked_refs: [],
    pending: null,
    error: null,
    ...over,
  } as ConvergeRound;
}

describe("attentionMarker", () => {
  test("a round that ended fine has nothing to see", () => {
    expect(attentionMarker(round())).toBeNull();
    expect(attentionMarker(round({ status: "no_change" }))).toBeNull();
    expect(attentionMarker(null)).toBeNull();
    expect(attentionMarker(undefined)).toBeNull();
  });

  test("every status the CLI exits non-zero on raises the dot", () => {
    for (const status of ["conflict", "awaiting_confirmation", "push_failed", "failed"] as const) {
      expect(attentionMarker(round({ status }))).not.toBeNull();
    }
  });

  test("the same problem an hour later is the same marker", () => {
    // The point of the whole thing. A timer re-raises one broken credential
    // every hour; a marker that called each repeat news would put the dot
    // back over a problem the user read at nine.
    const first = attentionMarker(round({ status: "failed", error: "git fetch failed: no auth" }));
    const second = attentionMarker(round({ status: "failed", error: "git fetch failed: no auth" }));
    expect(second).toBe(first);
  });

  test("a different problem asks again", () => {
    const auth = attentionMarker(round({ status: "failed", error: "git fetch failed: no auth" }));
    const disk = attentionMarker(round({ status: "failed", error: "git push failed: no space" }));
    expect(disk).not.toBe(auth);
  });

  test("a hold that changed direction or breaches asks again", () => {
    const publish = attentionMarker(
      round({
        status: "awaiting_confirmation",
        pending: {
          direction: "publish",
          breaches: [{ area: "resources", deleted: 28, total: 28 }],
        },
      } as Partial<ConvergeRound>),
    );
    const apply = attentionMarker(
      round({
        status: "awaiting_confirmation",
        pending: { direction: "apply", breaches: [{ area: "resources", deleted: 28, total: 28 }] },
      } as Partial<ConvergeRound>),
    );
    const worse = attentionMarker(
      round({
        status: "awaiting_confirmation",
        pending: {
          direction: "publish",
          breaches: [{ area: "resources", deleted: 40, total: 40 }],
        },
      } as Partial<ConvergeRound>),
    );
    expect(apply).not.toBe(publish);
    expect(worse).not.toBe(publish);
  });

  test("the marker stays small whatever the payload is", () => {
    // `pending.paths` is hundreds of entries on a real breach, and this goes
    // into localStorage.
    const marker = attentionMarker(
      round({
        status: "awaiting_confirmation",
        pending: {
          direction: "publish",
          breaches: [{ area: "resources", deleted: 28, total: 28 }],
          paths: Array.from({ length: 500 }, (_, i) => `resources/thing-${i}.yaml`),
        },
      } as Partial<ConvergeRound>),
    );
    expect(marker!.length).toBeLessThan(200);
  });
});
