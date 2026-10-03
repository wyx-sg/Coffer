// frontend/src/lib/reach/useReachWrites.ts
//
// The write half of ONE resource's reach control: what each choice sends, in
// what order, and how the popover hears about it. Reach saves on every change,
// so a user can tick three agents faster than three round trips; this runs
// the writes strictly in order (each is a whole-value PUT, so the last one
// wins and leaves the stored scope as the panel shows it) and reports one
// state for the whole burst.
//
//   Off          POST .../disable                       (the scope is left alone)
//   All agents   POST .../enable if needed, PUT scope null
//   Chosen       POST .../enable if needed, PUT {agents: [...]}
//
// Nothing refetches while the panel is open: a refetch re-sorts the list the
// popover is anchored to. The writes mark the lists stale and `flush` (called
// when the popover closes) refreshes them once. Until the new props arrive the
// hook hands back the value it just wrote (`value`) so the trigger never
// flickers back to the old reach.
//
// A failed write is NOT a toast: it stays in the popover as `failure`, on the
// row of the agent just ticked, with a retry that resends exactly that write.
// The scope API answers one whole PUT — there is no per-agent delivery verdict
// in it — so the failing agent is the one the user just ticked.
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { agentsKey, ownListKeysForKind, resourceScopeKey, resourcesKey } from "@/lib/api/queryKeys";
import { resourcesApi } from "@/lib/api/resources";
import type { Scope } from "@/lib/api/scope";
import { DeliveryError, putScopeChecked } from "@/lib/reach/deliveryFailure";
import type { ReachFailure } from "@/lib/reach/reachState";
import { sameScope } from "@/lib/scope";

/** How the last write is going: the popover footer's right-hand side. */
export type SaveState = "idle" | "applying" | "saved";

/** A resource's reach as written: the two fields that make it up. */
export interface ReachValue {
  enabled: boolean;
  scope: Scope | null;
}

/** How long "✓ Saved" stays on screen. */
const SAVED_MS = 2000;

export function useReachWrites(kind: string, uid: string, enabled: boolean, scope: Scope | null) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const tail = useRef<Promise<void>>(Promise.resolve());
  const pending = useRef(0);
  const dirty = useRef(false);
  const wantFlush = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  // What the server holds so far (advances as writes land) and what the user
  // has asked for so far (advances as writes are queued).
  const stored = useRef<ReachValue>({ enabled, scope });
  const intent = useRef<ReachValue>({ enabled, scope });
  const [state, setState] = useState<SaveState>("idle");
  const [failure, setFailure] = useState<ReachFailure | null>(null);
  const [value, setValue] = useState<ReachValue | null>(null);

  // New props while nothing is in flight are the truth again.
  const propKey = JSON.stringify([enabled, scope]);
  useEffect(() => {
    if (pending.current > 0) return;
    stored.current = { enabled, scope };
    intent.current = { enabled, scope };
    setValue(null);
    // `propKey` stands in for the two values: `scope` is a fresh object on
    // every list refetch even when it names the same agents.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [propKey]);
  useEffect(() => () => clearTimeout(timer.current), []);

  const tryFlush = useCallback(() => {
    if (!wantFlush.current || !dirty.current || pending.current > 0) return;
    wantFlush.current = false;
    dirty.current = false;
    void qc.invalidateQueries({ queryKey: resourceScopeKey(uid) });
    void qc.invalidateQueries({ queryKey: agentsKey });
    void qc.invalidateQueries({ queryKey: resourcesKey });
    for (const own of ownListKeysForKind(kind)) void qc.invalidateQueries({ queryKey: own });
  }, [qc, uid, kind]);

  const submit = useCallback(
    (next: ReachValue, write: () => Promise<void>, changed: string | null) => {
      clearTimeout(timer.current);
      intent.current = next;
      setFailure(null);
      setValue(next);
      setState("applying");
      pending.current += 1;
      tail.current = tail.current.then(async () => {
        let failed: unknown;
        let ok = true;
        try {
          await write();
          dirty.current = true;
        } catch (error) {
          ok = false;
          failed = error;
          if (error instanceof DeliveryError) dirty.current = true;
        }
        pending.current -= 1;
        // A later write in the queue supersedes this one and reports for both.
        if (pending.current > 0) return;
        if (ok) {
          setState("saved");
          timer.current = setTimeout(() => setState("idle"), SAVED_MS);
        } else {
          intent.current = stored.current;
          setValue(stored.current);
          setState("idle");
          // A saved scope that one agent could not take: the row of that agent
          // fails, and Retry sends the scope again (nothing else changed).
          const undelivered = failed instanceof DeliveryError ? failed : null;
          setFailure({
            uid: undelivered ? undelivered.agentUid : changed,
            message: translateApiError(t, failed),
            retry: undelivered
              ? () => submit(next, () => putScopeChecked(uid, next.scope), undelivered.agentUid)
              : () => submit(next, write, changed),
          });
        }
        tryFlush();
      });
    },
    [t, tryFlush, uid],
  );

  const enableIfNeeded = async () => {
    if (stored.current.enabled) return;
    await resourcesApi.enable(uid);
    stored.current = { ...stored.current, enabled: true };
  };

  const putScope = async (next: Scope | null) => {
    if (sameScope(stored.current.scope, next)) return;
    try {
      await putScopeChecked(uid, next);
    } catch (error) {
      // Saved even when one agent could not take it; any other failure saved nothing.
      if (error instanceof DeliveryError) stored.current = { ...stored.current, scope: next };
      throw error;
    }
    stored.current = { ...stored.current, scope: next };
  };

  const disable = useCallback(
    () =>
      submit(
        { ...intent.current, enabled: false },
        async () => {
          await resourcesApi.disable(uid);
          stored.current = { ...stored.current, enabled: false };
        },
        null,
      ),
    [submit, uid],
  );

  const everywhere = () =>
    submit(
      { enabled: true, scope: null },
      async () => {
        await enableIfNeeded();
        await putScope(null);
      },
      null,
    );

  const restricted = (next: Scope, changed: string | null = null) =>
    submit(
      { enabled: true, scope: next },
      async () => {
        await enableIfNeeded();
        await putScope(next);
      },
      changed,
    );

  /** Refreshes the lists once the writes have landed — call it when the panel closes. */
  const flush = useCallback(() => {
    wantFlush.current = true;
    tryFlush();
  }, [tryFlush]);

  return { state, failure, value, disable, everywhere, restricted, flush };
}
