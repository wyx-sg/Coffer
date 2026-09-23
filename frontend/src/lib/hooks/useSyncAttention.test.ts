// What the sidebar's Sync dot is keyed on.
//
// The marker is the whole design: it decides whether "I have seen this" keeps
// holding after the next hourly round, and getting it wrong turns the dot
// into either a nag or a thing that only ever appears once.
import { describe, expect, test } from "vitest";
import { attentionMarker, syncStatusMarker } from "./useSyncAttention";
import type { ConvergeRound, SyncStatus } from "@/lib/api/sync";
import { acceptance } from "@/test/acceptance";

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
    for (const status of [
      "conflict",
      "awaiting_confirmation",
      "push_failed",
      "failed",
      "awaiting_join",
    ] as const) {
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

function status(enabled: boolean | null, last: Partial<ConvergeRound> | null): SyncStatus {
  return {
    configured: enabled !== null,
    remote:
      enabled === null
        ? null
        : {
            url: "https://example.invalid/vault.git",
            branch: "main",
            credential_ref: null,
            include_credentials: false,
            interval_seconds: 3600,
            enabled,
            worktree_path: "/tmp/sync",
          },
    last_run: last === null ? null : round(last),
    machine_id: "m-1",
    machine_id_is_derived: false,
    joined: true,
    not_applicable: [],
  };
}

describe("syncStatusMarker", () => {
  acceptance("vault-sync", "a machine that has not joined says so everywhere", () => {
    // Every round converges nothing until someone adopts, so the Sync entry
    // carries the dot exactly as it does for a held round.
    const marker = syncStatusMarker(status(true, { status: "awaiting_join" }));
    expect(marker).not.toBeNull();
    expect(marker!.startsWith("awaiting_join|")).toBe(true);
  });

  acceptance("vault-sync", "a paused remote runs no round and asks for nothing", () => {
    // Pausing records no round, so `last_run` still holds the hold it was
    // paused on — and the dot must not keep asking about it.
    const held = { status: "awaiting_confirmation" } as Partial<ConvergeRound>;
    expect(syncStatusMarker(status(true, held))).not.toBeNull();
    expect(syncStatusMarker(status(false, held))).toBeNull();
    expect(syncStatusMarker(status(false, { status: "awaiting_join" }))).toBeNull();
  });

  test("no remote and no status have nothing to see", () => {
    expect(syncStatusMarker(status(null, null))).toBeNull();
    expect(syncStatusMarker(undefined)).toBeNull();
  });
});
