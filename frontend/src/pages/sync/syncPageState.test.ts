// frontend/src/pages/sync/syncPageState.test.ts
//
// One state for the whole page, in the order a person needs it: a running
// round first, a paused remote over what it would raise, a stop over a
// problem, what waits to push over what the last round pulled.
import { describe, expect, test } from "vitest";
import type { TFunction } from "i18next";
import i18next from "@/i18n";

import { primaryAction, syncState } from "./syncPageState";
import { intervalPhrase, remoteHost } from "./syncTime";
import { makeRound, makeStatus } from "./syncTestKit";

const t = i18next.t.bind(i18next) as TFunction;
const problem = (kind: "unreachable" | "push_failed" | "cloud_folder") => ({
  kind,
  message: "",
  secret_ref: null,
  since: null,
  handoff: null,
  plaintext: [],
});
const waiting = [
  {
    version: "v",
    time: "",
    writer: "user",
    summary: "",
    changes: [{ path: "a", status: "added" as const }],
  },
];

describe("syncState", () => {
  test("not configured or not joined is set-up, whatever else holds", () => {
    expect(syncState(makeStatus({ configured: false, remote: null })).kind).toBe("setup");
    expect(syncState(makeStatus({ joined: false, conflicts: 2 })).kind).toBe("setup");
  });

  test("the order of what outranks what", () => {
    const base = makeStatus({ conflicts: 1, problem: problem("unreachable"), waiting });
    expect(syncState(base, true).kind).toBe("syncing");
    expect(syncState({ ...base, remote: { ...base.remote!, enabled: false } }).kind).toBe("paused");
    expect(syncState(base).kind).toBe("conflicts");
    expect(syncState({ ...base, conflicts: 0, held: 3 })).toMatchObject({ kind: "held", count: 3 });
    expect(syncState({ ...base, conflicts: 0 }).kind).toBe("unreachable");
    expect(syncState({ ...base, conflicts: 0, problem: null })).toMatchObject({
      kind: "to_push",
      count: 1,
    });
    expect(
      syncState(makeStatus({ last_round: makeRound({ status: "pulled", pulled_files: 3 }) })),
    ).toMatchObject({ kind: "pulled", count: 3 });
    expect(syncState(makeStatus()).kind).toBe("in_sync");
  });

  test("the header's action per state", () => {
    expect(primaryAction("unreachable").label).toBe("tryAgain");
    expect(primaryAction("auth_failed").label).toBe("tryAgain");
    expect(primaryAction("push_failed")).toEqual({ label: "syncNow", disabled: false });
    expect(primaryAction("syncing")).toEqual({ label: "syncing", disabled: true });
    expect(primaryAction("conflicts").disabled).toBe(true);
  });
});

describe("syncTime", () => {
  test("interval phrases and remote hosts", () => {
    expect(intervalPhrase(3600, t)).toBe("every hour");
    expect(intervalPhrase(7200, t)).toBe("every 2 hours");
    expect(intervalPhrase(300, t)).toBe("every 5 minutes");
    expect(remoteHost("git@github.com:yuxing/coffer-vault.git")).toBe("github.com");
    expect(remoteHost("https://gitlab.example.com/me/vault.git")).toBe("gitlab.example.com");
  });
});
