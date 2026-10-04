// frontend/src/pages/sync/syncRemoteForm.acceptance.test.ts
//
// Saving the remote again from the Sync page's form (spec vault-sync "Pause a
// configured remote without forgetting it").
import { describe, expect } from "vitest";

import type { SyncRemote } from "@/lib/api/sync";
import { acceptance } from "@/test/acceptance";

import { EMPTY_FORM, formFromRemote, toRemoteInput } from "./syncRemoteForm";

const stored: SyncRemote = {
  url: "https://gitlab.com/me/vault.git",
  branch: "vault",
  secret_ref: "sync/gitlab-token",
  username: "oauth2",
  include_secret: true,
  interval_seconds: 900,
  enabled: false,
};

describe("saving a stored remote again", () => {
  acceptance("vault-sync", "reconfiguring a paused remote keeps it paused", () => {
    const form = { ...formFromRemote(stored), intervalSeconds: 600 };
    const sent = toRemoteInput(form, stored);
    expect(sent.interval_seconds).toBe(600);
    expect(sent.enabled).toBe(false);

    const first = toRemoteInput({ ...EMPTY_FORM, url: stored.url }, null);
    expect(first.enabled).toBe(true);
    expect(first.branch).toBe("main");
    expect(first.username).toBe("coffer");
    expect(first.include_secret).toBe(false);
  });

  acceptance("vault-sync", "reconfiguring a remote changes only what it names", () => {
    const sent = toRemoteInput({ ...formFromRemote(stored), intervalSeconds: 600 }, stored);
    expect(sent).toEqual({ ...stored, interval_seconds: 600 });

    const off = toRemoteInput({ ...formFromRemote(stored), includeSecret: false }, stored);
    expect(off).toEqual({ ...stored, include_secret: false });
  });
});
