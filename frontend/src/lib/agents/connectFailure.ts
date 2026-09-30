// src/lib/agents/connectFailure.ts — the last failed Connect of each agent, for its Overview (board 2.1.09).
//
// A Connect that fails is reported in the change dialog; once that closes, the
// agent's Overview still says why it isn't connected and offers Try again.
// The reason lives only in this window's memory: it is what this session saw
// fail, not a state the daemon keeps, and it is cleared by the next Connect
// that succeeds (or a disconnect, which is a fresh start).
import { useSyncExternalStore } from "react";

const failures = new Map<string, string>();
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

export function recordConnectFailure(uid: string, reason: string): void {
  failures.set(uid, reason);
  emit();
}

export function clearConnectFailure(uid: string): void {
  if (failures.delete(uid)) emit();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The translated reason the agent's last Connect failed, or null. */
export function useConnectFailure(uid: string): string | null {
  return useSyncExternalStore(
    subscribe,
    () => failures.get(uid) ?? null,
    () => null,
  );
}
