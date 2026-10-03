// src/components/shell/daemonConnection.ts — where the shell's connection to the daemon stands: ok, reconnecting or offline.
//
// Board 1.1.04 (Global states — behaviour), "Daemon connection": the status
// probe polls every 30s; on a failure it retries at 1, 2, 4 and 8s. For the
// first 10s of failures the page stays, under a "Reconnecting…" bar, dimmed
// and inert; after that the full offline state replaces it. On recovery the
// bar goes, every query refetches and a toast says so.
//
// The one status poll (`useDaemonStatus`) stays the source of truth. The shell
// mounts `useDaemonConnectionDriver` once (Layout): it schedules the retries
// and publishes the phase here; every other reader — the footer, the bar, the
// offline state — calls `useDaemonConnection`, so all of them agree on the
// same phase at the same moment without a second timer.
import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/errors";
import { useDaemonStatus } from "@/lib/hooks/useDaemon";

type ConnectionPhase = "ok" | "reconnecting" | "offline";

export interface DaemonConnection {
  phase: ConnectionPhase;
  /** The retry attempt under way while failing (1-based), 0 when ok. */
  attempt: number;
  /** When the next retry runs (ms since the epoch), while failing. */
  nextRetryAt: number | null;
  /** The last time the daemon answered, if it ever has. */
  lastReplyAt: number | null;
  /** The daemon answers but has no token for this page yet: it is starting. */
  starting: boolean;
  /** A driver is mounted. Without one (a surface rendered on its own, as in a
   *  test) nothing schedules retries, so a failing probe reads as offline. */
  driven: boolean;
}

/** Seconds between retries after a failure; the last repeats. */
const BACKOFF_S = [1, 2, 4, 8] as const;
/** After the backoff runs out, retry at the probe's normal pace. */
const STEADY_S = 30;
/** How long the page stays up under the reconnecting bar. */
const RECONNECT_GRACE_MS = 10_000;
/** A starting daemon (desktop cold start) gets longer before "offline". */
const STARTING_GRACE_MS = 30_000;

const IDLE: DaemonConnection = {
  phase: "ok",
  attempt: 0,
  nextRetryAt: null,
  lastReplyAt: null,
  starting: false,
  driven: false,
};

let state: DaemonConnection = IDLE;
const listeners = new Set<() => void>();

function publish(next: DaemonConnection): void {
  state = next;
  listeners.forEach((cb) => cb());
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

/** Read the shell's connection phase (any component, no timers of its own). */
export function useDaemonConnection(): DaemonConnection {
  return useSyncExternalStore(
    subscribe,
    () => state,
    () => IDLE,
  );
}

/** Tests only: forget what an earlier render published. */
export function resetDaemonConnection(): void {
  publish(IDLE);
}

function isStartingError(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.code === "DAEMON_NOT_READY" || error.code === "UNAUTHENTICATED")
  );
}

interface Driver {
  connection: DaemonConnection;
  /** Probe again now (the bar's Retry now, the offline state's Retry). */
  retryNow: () => void;
}

/**
 * Mount once, in the shell. Schedules the retries while the probe fails and
 * publishes the phase; `onRecovered` runs once when a failing daemon answers
 * again (after every query was asked to refetch).
 */
export function useDaemonConnectionDriver(onRecovered?: () => void): Driver {
  const qc = useQueryClient();
  const status = useDaemonStatus();
  const failingSince = useRef<number | null>(null);
  const attempt = useRef(0);
  const recovered = useRef(onRecovered);
  recovered.current = onRecovered;
  const { refetch } = status;
  const failing = status.isError;
  const starting = failing && isStartingError(status.error);
  // One tick per failed answer, so each failure schedules the next retry.
  const failureTick = failing ? status.errorUpdatedAt : 0;
  const lastReplyAt = status.dataUpdatedAt > 0 ? status.dataUpdatedAt : null;

  useEffect(() => {
    if (!failing) {
      if (failingSince.current !== null) {
        failingSince.current = null;
        attempt.current = 0;
        void qc.invalidateQueries();
        recovered.current?.();
      }
      publish({ ...IDLE, lastReplyAt, driven: true });
      return;
    }
    const now = Date.now();
    failingSince.current ??= now;
    attempt.current += 1;
    const n = attempt.current;
    const delayS = n <= BACKOFF_S.length ? BACKOFF_S[n - 1] : STEADY_S;
    const grace = starting ? STARTING_GRACE_MS : RECONNECT_GRACE_MS;
    const offlineAt = failingSince.current + grace;
    const nextRetryAt = now + delayS * 1000;
    const phaseAt = (t: number): ConnectionPhase => (t >= offlineAt ? "offline" : "reconnecting");
    publish({ phase: phaseAt(now), attempt: n, nextRetryAt, lastReplyAt, starting, driven: true });
    const retry = setTimeout(() => void refetch(), delayS * 1000);
    // Flip to offline at the end of the grace period even if no answer lands.
    const flip =
      now < offlineAt
        ? setTimeout(() => publish({ ...state, phase: "offline" }), offlineAt - now)
        : undefined;
    return () => {
      clearTimeout(retry);
      if (flip) clearTimeout(flip);
    };
  }, [failing, failureTick, starting, lastReplyAt, refetch, qc]);

  // Unmounted, nothing drives the phase any more.
  useEffect(() => () => publish(IDLE), []);

  const retryNow = useCallback(() => void refetch(), [refetch]);
  return { connection: useDaemonConnection(), retryNow };
}
