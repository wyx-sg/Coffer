// src/lib/hooks/useDaemonEvents.ts — follow the daemon's change feed and invalidate what each event names.
//
// A page that shows live state mounts this instead of polling (the
// convergence target in .agents/frontend.md §9): each `change` envelope is an
// invalidation hint naming a kind and a uid, so the hook invalidates the
// query keys that kind is read through, and the page's own hooks refetch
// through the typed endpoints. `resync` — the daemon could not replay what was
// missed — invalidates everything. A page with more to do on an event (the
// Activity page refreshing its newest records) passes a listener.
import { useEffect, useRef, useState } from "react";
import { useQueryClient, type QueryClient } from "@tanstack/react-query";

import { followDaemonEvents, type StreamMessage } from "@/lib/events/eventStream";
import { attentionKey, ownListKeysForKind, resourcesKey } from "@/lib/api/queryKeys";

/** The query keys one envelope's kind is read through. */
function invalidateFor(qc: QueryClient, message: StreamMessage): void {
  if (message.type === "resync") {
    void qc.invalidateQueries();
    return;
  }
  if (message.type !== "change") return;
  const { kind } = message.change;
  if (kind === "attention") {
    void qc.invalidateQueries({ queryKey: attentionKey });
    return;
  }
  void qc.invalidateQueries({ queryKey: resourcesKey });
  for (const own of ownListKeysForKind(kind)) {
    void qc.invalidateQueries({ queryKey: own });
  }
}

interface Options {
  /** Called for every message after the cache has been invalidated. */
  onMessage?: (message: StreamMessage) => void;
  /** False keeps the stream closed (e.g. a page in a test, or switched off). */
  enabled?: boolean;
}

// Whether the last stream was open. A page that mounts after another (every
// navigation) starts from this, so "Live" does not flash to "not live" for
// the moment its own connection takes to open; a `closed` message clears it.
let lastLive = false;

/**
 * Subscribe while mounted. Returns whether the stream is open right now, which
 * a page shows as its "Live" mark.
 */
export function useDaemonEvents({ onMessage, enabled = true }: Options = {}): { live: boolean } {
  const qc = useQueryClient();
  const [live, setLive] = useState(lastLive);
  const listener = useRef(onMessage);
  listener.current = onMessage;

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    void followDaemonEvents((message) => {
      if (message.type === "open") {
        lastLive = true;
        setLive(true);
      } else if (message.type === "closed") {
        lastLive = false;
        setLive(false);
      }
      invalidateFor(qc, message);
      listener.current?.(message);
    }, controller.signal);
    return () => {
      controller.abort();
    };
  }, [qc, enabled]);

  return { live };
}
