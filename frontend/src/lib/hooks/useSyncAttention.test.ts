// What the sidebar's Sync dot is keyed on.
//
// The marker is the whole design: it decides whether "I have seen this" keeps
// holding after the next hourly round, and getting it wrong turns the dot
// into either a nag or a thing that only ever appears once.
import { describe, expect, test } from "vitest";
import { attentionMarker, syncStatusMarker } from "./useSyncAttention";
import type { SyncStatus } from "@/lib/api/sync";
import { makeRound, makeStatus } from "@/pages/sync/syncTestKit";
import { acceptance } from "@/test/acceptance";

describe("attentionMarker", () => {
  test("a round that ended fine has nothing to see", () => {
    expect(attentionMarker(makeRound())).toBeNull();
    expect(attentionMarker(makeRound({ status: "pulled_and_pushed" }))).toBeNull();
    expect(attentionMarker(null)).toBeNull();
    expect(attentionMarker(undefined)).toBeNull();
  });

  test("every status that leaves the vault needing a person raises the dot", () => {
    for (const status of [
      "stopped",
      "held",
      "waiting_on_edit",
      "join_required",
      "auth_failed",
      "push_failed",
      "failed",
    ] as const) {
      expect(attentionMarker(makeRound({ status }))).not.toBeNull();
    }
  });

  test("the same problem a round later is the same marker", () => {
    // A timer re-raises one broken secret every pass; a marker that
    // called each repeat news would put the dot back over a problem the user
    // has already read.
    const first = attentionMarker(makeRound({ id: 1, status: "auth_failed", detail: "HTTP 403" }));
    const second = attentionMarker(makeRound({ id: 2, status: "auth_failed", detail: "HTTP 403" }));
    expect(second).toBe(first);
  });

  test("a different problem asks again", () => {
    const auth = attentionMarker(makeRound({ status: "auth_failed", detail: "HTTP 403" }));
    const push = attentionMarker(makeRound({ status: "push_failed", detail: "rejected" }));
    expect(push).not.toBe(auth);
    const two = attentionMarker(makeRound({ status: "stopped", conflicts: 2 }));
    const three = attentionMarker(makeRound({ status: "stopped", conflicts: 3 }));
    expect(three).not.toBe(two);
  });
});

function status(enabled: boolean | null, over: Partial<SyncStatus> = {}): SyncStatus {
  const base = makeStatus(over);
  if (enabled === null) return { ...base, configured: false, remote: null };
  return { ...base, remote: { ...base.remote!, enabled } };
}

describe("syncStatusMarker", () => {
  acceptance("vault-sync", "a machine that has not joined says so everywhere", () => {
    // Every round moves nothing until the machine joins, so the Sync entry
    // carries the dot exactly as it does for a held round.
    const marker = syncStatusMarker(status(true, { joined: false }));
    expect(marker).not.toBeNull();
    expect(marker!.startsWith("join_required")).toBe(true);
  });

  acceptance("vault-sync", "a paused remote runs no round and asks for nothing", () => {
    // Pausing runs no round, so the last one still holds what it was paused
    // on — and the dot must not keep asking about it.
    const held = { held: 12, last_round: makeRound({ status: "held", held: 12 }) };
    expect(syncStatusMarker(status(true, held))).not.toBeNull();
    expect(syncStatusMarker(status(false, held))).toBeNull();
    expect(syncStatusMarker(status(false, { joined: false }))).toBeNull();
  });

  test("a problem, a stop and a join's open files each raise it", () => {
    expect(syncStatusMarker(status(true))).toBeNull();
    expect(
      syncStatusMarker(
        status(true, {
          problem: {
            kind: "unreachable",
            message: "no route",
            secret_ref: null,
            since: null,
            handoff: null,
          },
        }),
      ),
    ).not.toBeNull();
    expect(syncStatusMarker(status(true, { conflicts: 1 }))).not.toBeNull();
    expect(syncStatusMarker(status(true, { join_choices: 2 }))).not.toBeNull();
  });

  test("no remote and no status have nothing to see", () => {
    expect(syncStatusMarker(status(null))).toBeNull();
    expect(syncStatusMarker(undefined)).toBeNull();
  });
});
