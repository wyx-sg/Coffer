// frontend/src/pages/sync/syncTestKit.ts — wire-shaped fixtures for the Sync
// tests, typed against the generated contract so a field renamed on the
// backend fails every test that builds one, not only the one that reads it.
import { vi } from "vitest";

import type { Machine, SyncRound, SyncStatus } from "@/lib/api/sync";

export function makeRound(over: Partial<SyncRound> = {}): SyncRound {
  return {
    id: 1,
    status: "nothing_to_do",
    started_at: "2026-09-13T09:00:00Z",
    finished_at: "2026-09-13T09:00:04Z",
    trigger: "timer",
    from_commit: null,
    to_commit: null,
    snapshot: null,
    pulled: [],
    applied: [],
    pushed: [],
    with_machines: [],
    conflicts: 0,
    held: 0,
    detail: null,
    path: null,
    join: null,
    pulled_files: 0,
    pushed_files: 0,
    plaintext: [],
    folded: 0,
    ...over,
  };
}

export function makeStatus(over: Partial<SyncStatus> = {}): SyncStatus {
  return {
    configured: true,
    remote: {
      url: "https://git.example.com/me/vault.git",
      branch: "main",
      secret_ref: "sync.PUSH_TOKEN",
      include_secret: false,
      interval_seconds: 300,
      enabled: true,
    },
    machine_id: "a3f21c9e4b7d2610",
    machine_name: "Laptop",
    joined: true,
    running_since: null,
    last_round: null,
    next_round_at: null,
    machines: 1,
    areas: { knowledge_documents: 0, skills: 0, resources: 0, secrets: 0, secrets_synced: false },
    waiting: [],
    vault_path: "/Users/me/.coffer/vault",
    synchroniser: null,
    problem: null,
    conflicts: 0,
    held: 0,
    join_choices: 0,
    ahead: 0,
    behind: 0,
    vault_real_path: "/Users/me/.coffer/vault",
    default_vault_path: "/Users/me/.coffer/vault",
    ...over,
  };
}

export function makeMachine(over: Partial<Machine> = {}): Machine {
  return {
    machine_id: "machine-here",
    name: "Laptop",
    os: "darwin",
    hostname: "laptop",
    coffer_version: "0.5.0",
    last_round_at: null,
    last_round: null,
    last_converged_commit: null,
    key_fingerprint: null,
    key_matches: true,
    agents: [],
    is_self: true,
    ...over,
  };
}

/** A mutation hook's return, idle; `mutate` does nothing unless handed one. */
export function idleMutation(over: Record<string, unknown> = {}) {
  return { mutate: vi.fn(), isPending: false, error: null, reset: vi.fn(), ...over };
}
